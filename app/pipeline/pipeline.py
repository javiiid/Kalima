# ============================================================
# app/pipeline/pipeline.py
# ============================================================
"""
Main translation pipeline for KALIMA.

Responsibilities
----------------
- Process EPUB files
- Process PDF files
- Create and resume translation jobs
- Manage translation state
- Save translation progress
- Reassemble translated EPUB files
- Create translated PDF files
- Handle Ctrl+C safely
- Clean temporary files after successful processing
"""

import json
import os
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.jobs.state import (
    load_job_state,
    save_chunks,
    save_translations,
    ensure_temp_structure,
)

from app.jobs.manager import select_resumable_job

from app.jobs.cleanup import cleanup_files

from app.translation.translator import (
    process_translations,
    load_test_translations,
)

from app.pipeline.epub_handler import EPUBHandler
from app.pipeline.epub_pipeline import reassemble_translation

from app.core.paths import (
    create_job_id,
)

from app.core.logging import log_progress
from app.core.validation import ensure_disk_space, validate_book

from app.core.exceptions import handle_interrupt

from app.output.formats import (
    EPUB_RENDERED_OUTPUTS,
    generate_epub_outputs,
    generate_outputs,
    normalize_outputs,
)
from app.output.markers import strip_markers
from app.output.segments import build_segments
from app.pipeline.quality_scorer import make_scorer


UTC = timezone.utc


# ============================================================
# HELPERS
# ============================================================

def _utc_timestamp():
    """
    Return the current UTC timestamp as a readable string.
    """
    return datetime.now(UTC).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _create_job(
    input_path,
    from_lang,
    to_lang,
    model,
):
    """
    Create a new translation job and its temporary structure.

    Returns
    -------
    tuple
        (job_id, paths)
    """

    job_id = create_job_id(
        input_path,
        from_lang,
        to_lang,
        model,
    )

    paths = ensure_temp_structure(job_id)

    return job_id, paths


def _cleanup_job(
    client,
    paths,
    input_file_id=None,
    status=None,
    debug=False,
):
    """
    Remove temporary files.

    In debug mode nothing is deleted.
    """

    if debug:
        print(
            "Debug mode enabled: "
            "temporary files will be preserved "
            "[translate]"
        )
        return

    if not paths:
        return

    file_ids = []

    if input_file_id:
        file_ids.append(input_file_id)

    if status is not None:
        output_file_id = getattr(
            status,
            "output_file_id",
            None,
        )

        if output_file_id:
            file_ids.append(output_file_id)

    job_dir = paths.get("job_dir")

    if not job_dir:
        return

    print(
        f"Cleaning up job directory: "
        f"{job_dir} [translate]"
    )

    cleanup_files(
        client,
        file_ids,
        temp_dir=job_dir,
        keep_temp=False,
    )


def _print_job_start(
    job_id,
    model,
    resumed=False,
):
    """
    Print standard job startup information.
    """

    print()

    if resumed:
        print(
            f"Resuming job: {job_id} [translate]"
        )
    else:
        print(
            f"Starting new job: {job_id} [translate]"
        )

    print(
        f"Started at: {_utc_timestamp()} UTC "
        f"[translate]"
    )

    print(
        f"Using model: {model} [translate]"
    )


# ============================================================
# EPUB PIPELINE
# ============================================================

def _translate_epub(
    client,
    input_path,
    output_path,
    from_lang,
    to_lang,
    mode,
    model,
    resume_job_id,
    debug,
    translation_prompt,
    output_formats=None,
    stop_event=None,
    on_job_started=None,
    style_preset=None,
    fallback_model=None,
    user_id=1,
    log_sink=None,
    rate_limiter=None,
):
    """
    Execute the complete EPUB translation pipeline.
    """

    # Python only permits signal handlers in the interpreter's main thread.
    # The CLI runs there, while the local web UI deliberately runs jobs in a
    # worker thread so its request handler remains responsive.
    can_manage_signals = threading.current_thread() is threading.main_thread()
    original_sigint_handler = (
        signal.getsignal(signal.SIGINT)
        if can_manage_signals
        else None
    )

    interrupted = False
    success = False

    manifest_outputs = None

    input_file_id = None
    status = None

    paths = None
    job_id = None
    existing_state = None

    all_chunks = []
    chapter_map = {}
    translations = {}

    # chunk_id -> plain text of the preceding chunks. Empty unless semantic
    # chunking is enabled; see app/pipeline/semantic_chunker.py.
    chunk_contexts = {}

    try:

        # ====================================================
        # RESUME JOB
        # ====================================================

        if mode in (
            "resume",
        ) and resume_job_id is None:

            resume_job_id = select_resumable_job(
                input_path,
                from_lang,
                to_lang,
                model,
                mode,
            )

            if resume_job_id is None:
                print(
                    "No job selected. "
                    "Translation cancelled. "
                    "[translate]"
                )
                return

        # ====================================================
        # EXISTING JOB
        # ====================================================

        if resume_job_id:

            job_id = resume_job_id

            paths = ensure_temp_structure(
                job_id
            )

            existing_state = load_job_state(
                paths
            )

            if not existing_state:

                print(
                    f"No valid state found for job "
                    f"{job_id}. [translate]"
                )

                print(
                    "Starting a new translation job. "
                    "[translate]"
                )

                job_id, paths = _create_job(
                    input_path,
                    from_lang,
                    to_lang,
                    model,
                )

                resume_job_id = None

            else:

                _print_job_start(
                    job_id,
                    model,
                    resumed=True,
                )

        # ====================================================
        # NEW JOB
        # ====================================================

        else:

            job_id, paths = _create_job(
                input_path,
                from_lang,
                to_lang,
                model,
            )

            _print_job_start(
                job_id,
                model,
                resumed=False,
            )

        # ====================================================
        # LOG
        # ====================================================

        if on_job_started:
            on_job_started(job_id, paths)

        log_progress(
            paths,
            (
                "Resuming"
                if resume_job_id
                else "Starting"
            )
            + f" translation job: {job_id}",
        )

        # ====================================================
        # SIGNAL HANDLER
        # ====================================================

        if can_manage_signals:
            signal.signal(
                signal.SIGINT,
                handle_interrupt,
            )

        # ====================================================
        # LOAD EXISTING STATE
        # ====================================================

        if resume_job_id and existing_state:

            print()
            print(
                "Resuming from previous state "
                "[translate]"
            )

            all_chunks = existing_state.get(
                "chunks",
                [],
            )

            chapter_map = existing_state.get(
                "chapter_map",
                {},
            )

            # Preceding-chunk context, keyed by chunk id. Saved with the job so a
            # resumed run gives the model the same context the first run did --
            # otherwise a resumed book would quietly translate its later chunks
            # blind, which is the whole point of the feature.
            chunk_contexts = existing_state.get(
                "chunk_contexts",
                {},
            )

            translations = existing_state.get(
                "translations",
                {},
            )

            print(
                f"Total chunks: "
                f"{len(all_chunks)} [translate]"
            )

            print(
                f"Completed translations: "
                f"{len(translations)} [translate]"
            )

        # ====================================================
        # BUILD NEW EPUB CHUNKS
        # ====================================================

        else:

            print()
            print(
                "Building EPUB chunks... "
                "[translate]"
            )

            all_chunks, chapter_map, chunk_contexts = (
                EPUBHandler.build_chunks(
                    input_path
                )
            )

            if not all_chunks:

                print(
                    "No translatable chunks were "
                    "found in the EPUB. [translate]"
                )

                return

            save_chunks(
                paths,
                all_chunks,
                chapter_map,
                chunk_contexts,
            )

            translations = {}

            print(
                f"Total chunks created: "
                f"{len(all_chunks)} [translate]"
            )

        # ====================================================
        # DETERMINE MODE
        # ====================================================

        if not mode:

            mode = "fast"

        print(
            f"Processing mode: "
            f"{mode} [translate]"
        )

        # ====================================================
        # TEST MODE
        # ====================================================

        test_translations = None

        if mode == "test":

            test_translations = (
                load_test_translations(
                    input_path
                )
            )

            if test_translations is None:

                print(
                    "No test translations found. "
                    "[translate]"
                )

                return

        # ====================================================
        # TRANSLATION
        # ====================================================

        print()
        print(
            "=" * 60
        )
        print(
            "Starting translation..."
        )
        print(
            "=" * 60
        )

        translations, input_file_id, status = (
            process_translations(
                client,
                all_chunks,
                translations,
                mode,
                from_lang,
                to_lang,
                paths,
                model=model,
                test_translations=test_translations,
                debug=debug,
                chapter_map=chapter_map,
                filetype="epub",
                translation_prompt=translation_prompt,
                stop_event=stop_event,
                style_preset=style_preset,
                chunk_contexts=chunk_contexts,
                fallback_model=fallback_model,
                user_id=int(user_id or 1),
                log_sink=log_sink,
                rate_limiter=rate_limiter,
            )
        )

        print(
            f"Final translation count: "
            f"{len(translations)} "
            f"[translate]"
        )

        # ====================================================
        # SAVE STATE
        # ====================================================

        save_translations(
            paths,
            translations,
        )

        # ====================================================
        # EMPTY TRANSLATION CHECK
        # ====================================================

        if not translations:

            print(
                "No translations available. "
                "Output file will not be created. "
                "[translate]"
            )

            return

        # ============================================================
        # EXTRA OUTPUT FORMATS
        # ============================================================

        requested_outputs = (
            normalize_outputs(output_formats)
            if output_formats
            else []
        )

        # DOCX, PDF and Markdown carry structure and media, so they are built
        # from the reassembled EPUB below. Everything else is text-only and
        # keeps using the segment writers.
        epub_rendered = [
            name
            for name in requested_outputs
            if name in EPUB_RENDERED_OUTPUTS
        ]
        text_outputs = [
            name
            for name in requested_outputs
            if name not in EPUB_RENDERED_OUTPUTS
        ]

        if output_formats:

            print()
            print(
                "Generating additional output "
                "formats... [translate]"
            )

            if text_outputs:

                output_result = generate_outputs(
                    build_segments(
                        all_chunks,
                        translations,
                        chapter_map,
                        filetype="epub",
                    ),
                    requested=text_outputs,
                    output_dir=output_path.parent,
                    base_name=output_path.stem,
                    filetype="epub",
                    title=input_path.stem,
                    to_lang=to_lang,
                    scorer=make_scorer(
                        text_outputs,
                        client=client,
                        model=model,
                        source_lang=from_lang,
                        target_lang=to_lang,
                        filetype="epub",
                        all_chunks=all_chunks,
                        translations=translations,
                        paths=paths,
                        stop_event=stop_event,
                    ),
                )

            else:

                output_result = {
                    "generated": {},
                    "skipped": {},
                    "qa_report": None,
                    "flagged": 0,
                    "quality": None,
                }

            translations = {
                chunk_id: strip_markers(value)
                for chunk_id, value
                in translations.items()
            }

            manifest_outputs = output_result

            for name, item_path in sorted(
                output_result["generated"].items()
            ):

                print(
                    f"  {name:<18}: {item_path} "
                    f"[translate]"
                )

            if output_result["flagged"]:

                print(
                    f"  QA: {output_result['flagged']} "
                    "flagged segment(s). [translate]"
                )

            if output_result.get("quality"):

                print(
                    f"  Quality: "
                    f"{output_result['quality']['flagged_count']} "
                    f"of "
                    f"{output_result['quality']['total_chunks']} "
                    f"chunks flagged "
                    f"[translate]"
                )

        # ====================================================
        # REASSEMBLE EPUB
        # ====================================================

        print()
        print(
            "Reassembling translated EPUB... "
            "[translate]"
        )

        reassemble_translation(
            input_path,
            output_path,
            chapter_map,
            translations,
        )

        print(
            f"Translated EPUB saved to: "
            f"{output_path} [translate]"
        )

        if epub_rendered:

            print()
            print(
                "Rendering EPUB-based DOCX/PDF/Markdown "
                "with images... [translate]"
            )

            epub_result = generate_epub_outputs(
                output_path,
                epub_rendered,
                output_path.parent,
                output_path.stem,
                to_lang=to_lang,
            )

            if manifest_outputs is None:

                manifest_outputs = epub_result

            else:

                manifest_outputs["generated"].update(
                    epub_result["generated"]
                )
                manifest_outputs["skipped"].update(
                    epub_result["skipped"]
                )

            for name, item_path in sorted(
                epub_result["generated"].items()
            ):

                print(
                    f"  {name:<18}: {item_path} "
                    f"[translate]"
                )

            for name, reason in sorted(
                epub_result["skipped"].items()
            ):

                print(
                    f"  {name:<18}: skipped ({reason}) "
                    f"[translate]"
                )

        success = True

    except KeyboardInterrupt:

        interrupted = True

        print()
        print(
            "=" * 60
        )
        print(
            "TRANSLATION INTERRUPTED"
        )
        print(
            "=" * 60
        )

        print(
            "Current translation state "
            "has been preserved. [translate]"
        )

        print(
            "Run again with --mode resume "
            "to continue. [translate]"
        )

        return

    finally:

        # ====================================================
        # RESTORE SIGNAL HANDLER
        # ====================================================

        if can_manage_signals:
            signal.signal(
                signal.SIGINT,
                original_sigint_handler,
            )

        # ====================================================
        # CLEANUP -- AN INTERRUPTED JOB KEEPS ITS TEMP FILES
        # ====================================================

        if interrupted:

            print(
                "Temporary files preserved "
                "for resume. [translate]"
            )

        elif success:

            _cleanup_job(
                client,
                paths,
                input_file_id,
                status,
                debug,
            )

            print()
            print(
                "Processing completed "
                "successfully. [translate]"
            )

        else:

            print()
            print(
                "Processing did not complete "
                "successfully. [translate]"
            )

            print(
                "Temporary files have been "
                "preserved for debugging/resume. "
                "[translate]"
            )

    return manifest_outputs


# ============================================================
# PDF PIPELINE
# ============================================================

def _is_rtl_language(language):
    """True when the source language reads right to left."""
    from app.output.typography import RTL_LANGUAGES

    return str(language or "").strip().upper() in RTL_LANGUAGES


def _write_job_json(path, payload):
    """Write a small job report atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def _load_page_plan(paths, input_path):
    """Return a saved per-page plan for this input, or None.

    A resumed job must not re-profile or re-OCR the book. The plan is only
    reused when it belongs to the same input and any OCR output it points at
    still exists on disk.
    """
    path = paths.get("page_plan_file")
    if not path or not Path(path).exists():
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("input") != Path(input_path).name:
        return None
    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages:
        return None

    ocr_output = payload.get("ocr_output")
    if any(entry.get("source") == "ocr" for entry in pages):
        if not ocr_output or not Path(ocr_output).exists():
            return None
    return payload


def _save_page_plan(paths, input_path, plan, ocr_output=None):
    path = paths.get("page_plan_file")
    if not path:
        return
    _write_job_json(
        path,
        {
            "input": Path(input_path).name,
            "created_at": _utc_timestamp(),
            "ocr_output": str(ocr_output) if ocr_output else None,
            "pages": plan,
        },
    )


def _write_pages_report(paths, input_path, plan, *, ocr_seconds, ocr_report):
    """Write ``pages.json`` and one summary event for the job."""
    path = paths.get("pages_report_file")
    if not path:
        return

    summary = {"text": 0, "ocr": 0, "vision": 0, "blank": 0}
    for entry in plan:
        source = entry.get("source")
        if source in summary:
            summary[source] += 1
    summary["pages"] = len(plan)
    summary["ocr_seconds"] = round(float(ocr_seconds), 2)

    _write_job_json(
        path,
        {
            "input": Path(input_path).name,
            "generated_at": _utc_timestamp(),
            "summary": summary,
            "ocr": ocr_report,
            "pages": plan,
        },
    )

    try:
        from app.core.structured_logging import get_job_logger

        get_job_logger(paths).emit(
            "pdf.pages_routed",
            "per-page PDF routing complete",
            summary=summary,
        )
    except Exception:  # noqa: BLE001
        # Reporting must never break a translation job.
        pass


def _translate_pdf(
    client,
    input_path,
    output_path,
    from_lang,
    to_lang,
    mode,
    model,
    debug,
    translation_prompt,
    output_formats=None,
    stop_event=None,
    on_job_started=None,
    style_preset=None,
    fallback_model=None,
    user_id=1,
    log_sink=None,
    rate_limiter=None,
):
    """
    Execute the PDF processing pipeline.

    Important:
    PDFHandler.transcribe_pdf() is responsible for
    extracting/OCRing the PDF.

    The extracted chunks are then sent through
    process_translations().
    """

    from app.pipeline.pdf_handler import PDFHandler, merge_page_chunks

    success = False

    manifest_outputs = None

    paths = None
    input_file_id = None
    status = None

    try:

        # ====================================================
        # CREATE JOB
        # ====================================================

        job_id, paths = _create_job(
            input_path,
            from_lang,
            to_lang,
            model,
        )

        _print_job_start(
            job_id,
            model,
            resumed=False,
        )

        if on_job_started:
            on_job_started(job_id, paths)

        # ====================================================
        # TRANSCRIBE PDF
        # ====================================================

        print()
        print(
            "=" * 60
        )
        print(
            "PDF PROCESSING"
        )
        print(
            "=" * 60
        )

        print(
            "Extracting text from PDF... "
            "[translate]"
        )

        chunk_contexts = None

        from app.core.config import get_pdf_config
        from app.pipeline import pdf_text, pdf_ocr

        pdf_cfg = get_pdf_config()

        layout_on = pdf_cfg["layout"] != "off"
        rtl = _is_rtl_language(from_lang)

        # Phase 3: the decision is per page, not per file. One scanned page no
        # longer drags a whole text book to OCR, and one figure page no longer
        # drags it to vision.
        page_plan = _load_page_plan(paths, input_path)
        source_pdf = input_path
        ocr_report = {"used": False, "ok": False, "reason": ""}
        ocr_seconds = 0.0
        profile = None

        if page_plan is None:

            profile = pdf_ocr.profile_pages(input_path)
            analysis = pdf_ocr.analyze_profile(profile)

            print(
                f"PDF profile: {analysis['kind']} "
                f"({analysis['pages_with_text']}/"
                f"{analysis['total_pages']} pages with text). "
                f"[translate]"
            )

            ocr_ready = False
            if pdf_cfg["text_fastpath"] and pdf_cfg["ocr"] != "off":
                # "auto" runs OCR only when the tools are genuinely installed;
                # "on" attempts it anyway and still degrades safely if it fails.
                if pdf_cfg["ocr"] == "auto":
                    ocr_ready = pdf_ocr.ocr_available(
                        pdf_ocr.resolve_language(from_lang),
                        work_dir=paths["job_dir"],
                    )["available"]
                else:
                    ocr_ready = True

            if not pdf_cfg["text_fastpath"]:
                # Explicit opt-out keeps the phase 2 behaviour: vision for all.
                page_plan = [
                    {
                        "page": int(item["page"]),
                        "kind": item["kind"],
                        "source": (
                            "blank" if item["kind"] == "blank" else "vision"
                        ),
                        "chars": int(item["chars"]),
                    }
                    for item in profile
                ]
            else:
                page_plan = pdf_ocr.plan_pages(
                    profile,
                    ocr_available=ocr_ready,
                    config=pdf_cfg,
                )

            ocr_pages = [
                entry["page"]
                for entry in page_plan
                if entry["source"] == "ocr"
            ]

            if ocr_pages:

                print(
                    f"Running local OCR for {len(ocr_pages)} "
                    f"page(s) (OCRmyPDF --skip-text, no API calls). "
                    f"[translate]"
                )

                started = time.monotonic()
                source_pdf, ocr_report = pdf_ocr.ensure_text_pdf(
                    input_path,
                    paths["job_dir"],
                    language=pdf_cfg["ocr_language"],
                    from_lang=from_lang,
                    timeout=pdf_cfg["ocr_timeout"],
                    profile=profile,
                    config=pdf_cfg,
                )
                ocr_seconds = time.monotonic() - started

                if ocr_report.get("ok"):

                    print(
                        f"OCR result: {ocr_report.get('reason')} "
                        f"[translate]"
                    )

                    pages_text = pdf_text.extract_pages_text_in_order(
                        source_pdf,
                        layout=layout_on,
                        rtl=rtl,
                    )
                    page_plan = pdf_ocr.apply_quality_gate(
                        page_plan,
                        pages_text,
                        config=pdf_cfg,
                    )

                else:

                    print(
                        f"OCR not usable "
                        f"({ocr_report.get('reason')}); "
                        f"keeping the vision fallback. [translate]"
                    )
                    page_plan = pdf_ocr.fallback_to_vision(
                        page_plan,
                        config=pdf_cfg,
                    )

            elif pdf_cfg["ocr"] == "off" and any(
                entry["kind"] == "scan" for entry in page_plan
            ):
                print(
                    "OCR is disabled; scanned pages use vision. "
                    "[translate]"
                )

            _save_page_plan(
                paths,
                input_path,
                page_plan,
                ocr_output=(
                    source_pdf if source_pdf != input_path else None
                ),
            )

        else:
            saved_ocr = page_plan.get("ocr_output")
            if saved_ocr:
                source_pdf = Path(saved_ocr)
            page_plan = page_plan["pages"]
            print(
                "Reusing the saved per-page plan "
                "(no re-profiling, no re-OCR). [translate]"
            )

        text_pages = [
            entry["page"] for entry in page_plan if entry["source"] == "text"
        ]
        vision_pages = [
            entry["page"] for entry in page_plan if entry["source"] == "vision"
        ]

        _write_pages_report(
            paths,
            input_path,
            page_plan,
            ocr_seconds=ocr_seconds,
            ocr_report=ocr_report,
        )

        text_chunks, text_map, text_contexts = ([], {}, {})
        if text_pages:
            print(
                f"PDF text fast path: extracting {len(text_pages)} "
                f"page(s) locally (no vision calls). [translate]"
            )
            text_chunks, text_map, text_contexts = pdf_text.build_chunks(
                source_pdf,
                layout=layout_on,
                rtl=rtl,
                pages=text_pages,
            )

        vision_chunks, vision_map = ([], {})
        if vision_pages:
            print(
                f"Vision fallback for {len(vision_pages)} "
                f"page(s). [translate]"
            )
            vision_chunks, vision_map = PDFHandler.transcribe_pdf(
                client,
                input_path,
                paths,
                dpi=150,
                batch=False,
                pages=vision_pages,
            )

        all_chunks, chapter_map, id_map = merge_page_chunks(
            (text_chunks, text_map),
            (vision_chunks, vision_map),
        )

        if text_contexts:
            chunk_contexts = {
                id_map[(0, old_id)]: text
                for old_id, text in text_contexts.items()
                if (0, old_id) in id_map
            }

        if not all_chunks:

            print(
                "No text was extracted from "
                "the PDF. [translate]"
            )

            return

        print(
            f"Extracted {len(all_chunks)} "
            f"chunks from the PDF. [translate]"
        )

        # ====================================================
        # SAVE CHUNKS
        # ====================================================

        save_chunks(
            paths,
            all_chunks,
            chapter_map,
            chunk_contexts,
        )

        # ====================================================
        # TRANSLATION
        # ====================================================

        translations = {}

        print()
        print(
            "=" * 60
        )
        print(
            "TRANSLATING PDF"
        )
        print(
            "=" * 60
        )

        if not mode:

            mode = "fast"

        translations, input_file_id, status = (
            process_translations(
                client,
                all_chunks,
                translations,
                mode,
                from_lang,
                to_lang,
                paths,
                model=model,
                debug=debug,
                chapter_map=chapter_map,
                filetype="pdf",
                translation_prompt=translation_prompt,
                stop_event=stop_event,
                style_preset=style_preset,
                fallback_model=fallback_model,
                user_id=int(user_id or 1),
                log_sink=log_sink,
                rate_limiter=rate_limiter,
            )
        )

        print(
            f"Final translation count: "
            f"{len(translations)} "
            f"[translate]"
        )

        # ====================================================
        # SAVE TRANSLATIONS
        # ====================================================

        save_translations(
            paths,
            translations,
        )

        if not translations:

            print(
                "No PDF translations available. "
                "[translate]"
            )

            return

        # ============================================================
        # EXTRA OUTPUT FORMATS
        # ============================================================

        if output_formats:

            print()
            print(
                "Generating additional output "
                "formats... [translate]"
            )

            output_result = generate_outputs(
                build_segments(
                    all_chunks,
                    translations,
                    chapter_map,
                    filetype="pdf",
                ),
                requested=output_formats,
                output_dir=output_path.parent,
                base_name=output_path.stem,
                filetype="pdf",
                title=input_path.stem,
                to_lang=to_lang,
                scorer=make_scorer(
                    output_formats,
                    client=client,
                    model=model,
                    source_lang=from_lang,
                    target_lang=to_lang,
                    filetype="pdf",
                    all_chunks=all_chunks,
                    translations=translations,
                    paths=paths,
                    stop_event=stop_event,
                ),
            )

            translations = {
                chunk_id: strip_markers(value)
                for chunk_id, value
                in translations.items()
            }

            manifest_outputs = output_result

            for name, item_path in sorted(
                output_result["generated"].items()
            ):

                print(
                    f"  {name:<18}: {item_path} "
                    f"[translate]"
                )

            if output_result["flagged"]:

                print(
                    f"  QA: {output_result['flagged']} "
                    "flagged segment(s). [translate]"
                )

            if output_result.get("quality"):

                print(
                    f"  Quality: "
                    f"{output_result['quality']['flagged_count']} "
                    f"of "
                    f"{output_result['quality']['total_chunks']} "
                    f"chunks flagged "
                    f"[translate]"
                )

        # ====================================================
        # CREATE PDF
        # ====================================================

        if mode == "pdfbilingual":

            print(
                "Creating bilingual PDF... "
                "[translate]"
            )

            PDFHandler.save_bilingual_pdf(
                input_path,
                translations,
                output_path,
                chapter_map=chapter_map,
            )

        else:

            print(
                "Creating translated PDF... "
                "[translate]"
            )

            PDFHandler.save_translated_pdf(
                translations,
                output_path,
                original_pdf_path=source_pdf,
                chapter_map=chapter_map,
            )

        print()
        print(
            f"Translated PDF saved to: "
            f"{output_path} [translate]"
        )

        print(
            f"Finished at: "
            f"{_utc_timestamp()} UTC "
            f"[translate]"
        )

        success = True

    except KeyboardInterrupt:

        print()
        print(
            "PDF translation interrupted. "
            "Temporary files were preserved. "
            "[translate]"
        )

        print(
            "Run the job again to resume if "
            "your PDF pipeline supports resume. "
            "[translate]"
        )

        return

    finally:

        if success:

            _cleanup_job(
                client,
                paths,
                input_file_id,
                status,
                debug,
            )

            print(
                "PDF processing completed "
                "successfully. [translate]"
            )

        else:

            print(
                "PDF processing did not complete "
                "successfully. Temporary files "
                "were preserved. [translate]"
            )

    return manifest_outputs


# ============================================================
# MAIN TRANSLATE FUNCTION
# ============================================================

def translate(
    client,
    input_path,
    output_path,
    from_lang="EN",
    to_lang="FA",
    mode=None,
    model=None,
    resume_job_id=None,
    debug=False,
    filetype="epub",
    translation_prompt=None,
    output_formats=None,
    stop_event=None,
    on_job_started=None,
    style_preset=None,
    fallback_model=None,
    user_id=1,
    log_sink=None,
    rate_limiter=None,
):
    """
    Main translation dispatcher.

    Parameters
    ----------
    client:
        OpenAI-compatible API client.

    input_path:
        Source EPUB/PDF path.

    output_path:
        Destination path.

    from_lang:
        Source language.

    to_lang:
        Target language.

    mode:
        Translation mode.

    model:
        Model name.

    resume_job_id:
        Existing job ID for resume.

    debug:
        Preserve temporary files.

    filetype:
        epub or pdf.

    translation_prompt:
        Custom/default translation prompt generated
        by app.translation.prompts.

    user_id:
        Owner of the job; scopes the translation memory (Phase 1).

    log_sink:
        Optional stream that receives output from translation worker threads.
        The web server passes the job's log buffer so concurrent jobs do not
        cross-wire their logs. ``None`` keeps the CLI behavior unchanged.

    rate_limiter:
        Optional shared limiter. The web server passes one instance for every
        job so two books cannot each spend the full requests-per-minute
        allowance. ``None`` builds a per-run limiter, which is what the CLI
        still wants.
    """

    # ========================================================
    # RESOLVE MODEL
    # ========================================================
    # The signature used to default to "gpt-5.6-terra", so a caller that
    # omitted `model` silently overrode the user's choice. config.yaml is now
    # the single source of truth, with DEFAULT_MODEL as the fallback.
    if model is None:
        from app.core.models import resolve_default_model
        model = resolve_default_model()

    # ========================================================
    # NORMALIZE FILETYPE
    # ========================================================

    filetype = (
        str(filetype)
        .lower()
        .lstrip(".")
    )

    input_path = Path(
        input_path
    )

    output_path = Path(
        output_path
    )

    # Validate the document and available resources before creating a job or
    # making an API request. This catches corrupt archives and disk exhaustion
    # early, while leaving resumable state untouched.
    validate_book(input_path)
    ensure_disk_space(output_path, required_bytes=max(input_path.stat().st_size * 3, 100 * 1024 * 1024))

    # ========================================================
    # VALIDATE INPUT
    # ========================================================

    if not input_path.exists():

        raise FileNotFoundError(
            f"Input file does not exist: "
            f"{input_path}"
        )

    if not input_path.is_file():

        raise ValueError(
            f"Input path is not a file: "
            f"{input_path}"
        )

    # ========================================================
    # VALIDATE FILETYPE
    # ========================================================

    if filetype not in (
        "epub",
        "pdf",
    ):

        raise ValueError(
            "Unsupported file type: "
            f"{filetype}. "
            "Only EPUB and PDF are supported."
        )

    # ========================================================
    # CREATE OUTPUT DIRECTORY
    # ========================================================

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # DEFAULT MODE
    # ========================================================

    if mode is None:

        mode = "fast"

    # ========================================================
    # PRINT PIPELINE INFORMATION
    # ========================================================

    print()
    print(
        "=" * 60
    )
    print(
        "KALIMA PIPELINE"
    )
    print(
        "=" * 60
    )

    print(
        f"Input     : {input_path}"
    )

    print(
        f"Output    : {output_path}"
    )

    print(
        f"File type : {filetype}"
    )

    print(
        f"From      : {from_lang}"
    )

    print(
        f"To        : {to_lang}"
    )

    print(
        f"Model     : {model}"
    )

    print(
        f"Mode      : {mode}"
    )

    print(
        f"Debug     : {debug}"
    )

    print(
        "=" * 60
    )

    # ========================================================
    # EPUB
    # ========================================================

    if filetype == "epub":

        # ----------------------------------------------------
        # NORMAL EPUB TRANSLATION
        # ----------------------------------------------------

        return _translate_epub(
            client=client,
            input_path=input_path,
            output_path=output_path,
            from_lang=from_lang,
            to_lang=to_lang,
            mode=mode,
            model=model,
            resume_job_id=resume_job_id,
            debug=debug,
            translation_prompt=translation_prompt,
            output_formats=output_formats,
            stop_event=stop_event,
            on_job_started=on_job_started,
            style_preset=style_preset,
            fallback_model=fallback_model,
            user_id=user_id,
            log_sink=log_sink,
            rate_limiter=rate_limiter,
        )

    # ========================================================
    # PDF
    # ========================================================

    if filetype == "pdf":

        return _translate_pdf(
            client=client,
            input_path=input_path,
            output_path=output_path,
            from_lang=from_lang,
            to_lang=to_lang,
            mode=mode,
            model=model,
            debug=debug,
            translation_prompt=translation_prompt,
            output_formats=output_formats,
            stop_event=stop_event,
            on_job_started=on_job_started,
            style_preset=style_preset,
            fallback_model=fallback_model,
            user_id=user_id,
            log_sink=log_sink,
            rate_limiter=rate_limiter,
        )

    # ========================================================
    # SAFETY FALLBACK
    # ========================================================

    raise ValueError(
        f"Unsupported file type: {filetype}"
    )
