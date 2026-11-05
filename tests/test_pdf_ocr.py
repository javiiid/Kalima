"""Tests for the OCRmyPDF pre-layer (phase 2).

The behaviour worth protecting is not "OCRmyPDF runs" -- it is that a PDF which
already has text never pays for OCR, that a scan is recognized locally before
any provider call, and that a machine without OCRmyPDF/Tesseract degrades to the
vision fallback instead of raising. The integration tests are skipped when the
tools are not installed, which is the whole point of "OCR is optional".
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.pipeline import pdf_ocr


LONG = "The cartographer unrolled the map and weighed its corners carefully. " * 4


def _pymupdf():
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # type: ignore[no-redef]
    return pymupdf


def _make_text_pdf(path: Path, pages: list[str]) -> Path:
    pymupdf = _pymupdf()
    doc = pymupdf.open()
    for body in pages:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), body, fontsize=14)
    doc.save(str(path))
    doc.close()
    return path


def _make_scanned_pdf(path: Path, tmp: Path, pages: int = 1) -> Path:
    """A PDF whose pages are raster images only -- no text layer."""
    pymupdf = _pymupdf()
    src = pymupdf.open()
    for _ in range(pages):
        page = src.new_page(width=595, height=842)
        page.insert_text((72, 100), LONG, fontsize=16)
    png = tmp / "scan_src.png"
    src[0].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(str(png))
    src.close()

    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), filename=str(png))
    doc.save(str(path))
    doc.close()
    return path


# ============================================================
# Language mapping
# ============================================================

def test_resolve_language_maps_project_codes():
    assert pdf_ocr.resolve_language("EN") == "eng"
    assert pdf_ocr.resolve_language("FA") == "fas"
    assert pdf_ocr.resolve_language("de") == "deu"
    assert pdf_ocr.resolve_language(None) == pdf_ocr.DEFAULT_OCR_LANGUAGE


def test_resolve_language_falls_back_to_installed():
    # Requested pack is not installed -> English wins when present.
    assert pdf_ocr.resolve_language("FA", {"eng", "ara"}) == "eng"
    # English also missing -> deterministic fallback to an installed one.
    assert pdf_ocr.resolve_language("FA", {"ara"}) == "ara"


def test_resolve_language_keeps_installed_match():
    assert pdf_ocr.resolve_language("FA", {"eng", "fas"}) == "fas"


# ============================================================
# Analysis
# ============================================================

def test_analyze_text_pdf(tmp_path):
    pdf = _make_text_pdf(tmp_path / "text.pdf", [LONG, LONG])
    info = pdf_ocr.analyze_pdf(pdf)
    assert info["kind"] == "text"
    assert info["needs_ocr"] is False
    assert info["pages_with_text"] == 2


def test_analyze_scanned_pdf(tmp_path):
    pdf = _make_scanned_pdf(tmp_path / "scan.pdf", tmp_path, pages=2)
    info = pdf_ocr.analyze_pdf(pdf)
    assert info["kind"] == "scan"
    assert info["needs_ocr"] is True
    assert info["pages_with_text"] == 0


def test_analyze_mixed_pdf(tmp_path):
    # One real text page and one image-only page -> mixed.
    pdf = _make_text_pdf(tmp_path / "mixed.pdf", [LONG])
    pymupdf = _pymupdf()
    doc = pymupdf.open(str(pdf))
    doc.new_page(width=595, height=842)  # blank, no text
    doc.saveIncr()
    doc.close()
    info = pdf_ocr.analyze_pdf(pdf)
    assert info["kind"] == "mixed"
    assert info["needs_ocr"] is True


# ============================================================
# Availability reporting
# ============================================================

def test_ocr_available_returns_structured_report():
    info = pdf_ocr.ocr_available("eng")
    assert set(info) >= {"available", "ocrmypdf", "tesseract", "reason"}
    assert isinstance(info["available"], bool)
    if not info["available"]:
        # A missing tool must always carry a human-readable reason.
        assert info["reason"]


def test_ensure_text_pdf_skips_when_text_present(tmp_path):
    """A text PDF must never be handed to OCRmyPDF."""
    pdf = _make_text_pdf(tmp_path / "already.pdf", [LONG, LONG])
    out, report = pdf_ocr.ensure_text_pdf(pdf, tmp_path / "work")
    assert out == pdf
    assert report["used"] is False
    assert report["ok"] is True
    # No work directory should have been created for a file that needs no OCR.
    assert not (tmp_path / "work").exists()


def test_ensure_text_pdf_degrades_without_tools(tmp_path, monkeypatch):
    """When OCR is unavailable, return the input untouched and never raise."""
    monkeypatch.setattr(
        pdf_ocr, "ocr_available",
        lambda language="eng", work_dir=None: {
            "available": False, "reason": "not installed"
        },
    )
    pdf = _make_scanned_pdf(tmp_path / "scan.pdf", tmp_path)
    out, report = pdf_ocr.ensure_text_pdf(pdf, tmp_path / "work")
    assert out == pdf
    assert report["ok"] is False
    assert report["used"] is False
    assert "not installed" in report["reason"]


# ============================================================
# No network at extraction time
# ============================================================

def test_pdf_ocr_imports_no_provider(tmp_path, monkeypatch):
    """The pre-layer must be local-only: prove it by removing openai."""
    for name in list(sys.modules):
        if name == "openai" or name.startswith("openai."):
            monkeypatch.setitem(sys.modules, name, None)

    pdf = _make_text_pdf(tmp_path / "offline.pdf", [LONG])
    out, report = pdf_ocr.ensure_text_pdf(pdf, tmp_path / "work")
    assert out == pdf
    assert report["ok"] is True


# ============================================================
# Integration -- only when OCRmyPDF and Tesseract are installed
# ============================================================

def test_scan_becomes_text_and_text_is_skipped(tmp_path):
    """The real thing: a scan gains a text layer, a text PDF is left alone.

    This single test exercises ``--skip-text`` on both sides: the scanned file
    must come out with extractable text, and the text file must be returned
    unchanged without an OCR run.
    """
    work = tmp_path / "work"
    try:
        ready = bool(pdf_ocr.ocr_available("eng", work_dir=work)["available"])
    except Exception:  # noqa: BLE001
        ready = False
    if not ready:
        pytest.skip("OCRmyPDF/Tesseract not installed")

    scan = _make_scanned_pdf(tmp_path / "scan.pdf", tmp_path)
    out, report = pdf_ocr.ensure_text_pdf(scan, work)
    assert report["used"] is True
    assert report["ok"] is True, report["reason"]
    assert out != scan
    after = pdf_ocr.analyze_pdf(out)
    assert after["pages_with_text"] >= 1

    text = _make_text_pdf(tmp_path / "text.pdf", [LONG])
    out2, report2 = pdf_ocr.ensure_text_pdf(text, work)
    assert out2 == text
    assert report2["used"] is False


# ============================================================
# Pipeline wiring
# ============================================================

def test_translate_dispatcher_accepts_user_id():
    """Guards an incomplete multiuser refactor.

    ``web.py`` passes ``user_id=`` to ``translate()`` and both ``translate()``
    and ``_translate_pdf()`` read it to scope the translation memory. A
    signature that does not accept it raises ``NameError`` on *every* job, so
    the parameter is part of the public contract and must stay.
    """
    import inspect

    from app.pipeline import pipeline

    assert "user_id" in inspect.signature(pipeline.translate).parameters
    assert "user_id" in inspect.signature(pipeline._translate_pdf).parameters
    assert "user_id" in inspect.signature(pipeline._translate_epub).parameters


# ============================================================
# Phase 3 -- page profile, quality gate and routing
# ============================================================

def _make_figure_pdf(path: Path, tmp: Path) -> Path:
    """A page whose only content is a large image -- a chart or table."""
    pymupdf = _pymupdf()
    src = pymupdf.open()
    page = src.new_page(width=595, height=842)
    page.insert_text((72, 100), LONG, fontsize=16)
    png = tmp / "figure_src.png"
    src[0].get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(str(png))
    src.close()

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(40, 120, 555, 700), filename=str(png))
    doc.save(str(path))
    doc.close()
    return path


def test_profile_pages_classifies_four_kinds(tmp_path):
    text = _make_text_pdf(tmp_path / "text.pdf", [LONG])
    scan = _make_scanned_pdf(tmp_path / "scan.pdf", tmp_path)
    figure = _make_figure_pdf(tmp_path / "figure.pdf", tmp_path)

    pymupdf = _pymupdf()
    blank_doc = pymupdf.open()
    blank_doc.new_page(width=595, height=842)
    blank = tmp_path / "blank.pdf"
    blank_doc.save(str(blank))
    blank_doc.close()

    assert pdf_ocr.profile_pages(text)[0]["kind"] == "text"
    assert pdf_ocr.profile_pages(scan)[0]["kind"] == "scan"
    assert pdf_ocr.profile_pages(figure)[0]["kind"] == "figure"
    assert pdf_ocr.profile_pages(blank)[0]["kind"] == "blank"


def test_profile_pages_keeps_page_indexes_aligned(tmp_path):
    pdf = _make_text_pdf(tmp_path / "two.pdf", [LONG, ""])
    profile = pdf_ocr.profile_pages(pdf)
    assert [item["page"] for item in profile] == [0, 1]
    assert profile[0]["chars"] > 0
    assert profile[1]["chars"] == 0


def test_analyze_pdf_is_derived_from_the_profile(tmp_path):
    pdf = _make_text_pdf(tmp_path / "text.pdf", [LONG, LONG])
    profile = pdf_ocr.profile_pages(pdf)
    assert pdf_ocr.analyze_profile(profile) == pdf_ocr.analyze_pdf(pdf)


def test_page_quality_accepts_real_prose():
    result = pdf_ocr.page_quality(LONG)
    assert result["ok"] is True
    assert result["reasons"] == []


def test_page_quality_rejects_symbol_noise():
    result = pdf_ocr.page_quality("◆▯▮◇" * 20)
    assert result["ok"] is False
    assert result["garbage_ratio"] > 0.35


def test_page_quality_rejects_short_and_empty_text():
    assert pdf_ocr.page_quality("")["ok"] is False
    assert pdf_ocr.page_quality("page 7")["ok"] is False


def test_plan_pages_routes_each_kind():
    profile = [
        {"page": 0, "kind": "text", "chars": 900},
        {"page": 1, "kind": "scan", "chars": 0},
        {"page": 2, "kind": "figure", "chars": 0},
        {"page": 3, "kind": "blank", "chars": 0},
    ]
    plan = pdf_ocr.plan_pages(
        profile, ocr_available=True, config={"vision_fallback": "page"}
    )
    assert [entry["source"] for entry in plan] == ["text", "ocr", "vision", "blank"]


def test_plan_pages_without_ocr_sends_scans_to_vision():
    profile = [{"page": 0, "kind": "scan", "chars": 0}]
    plan = pdf_ocr.plan_pages(
        profile, ocr_available=False, config={"vision_fallback": "page"}
    )
    assert plan[0]["source"] == "vision"


def test_plan_pages_file_fallback_keeps_phase_two_behaviour():
    profile = [
        {"page": 0, "kind": "text", "chars": 900},
        {"page": 1, "kind": "figure", "chars": 0},
    ]
    plan = pdf_ocr.plan_pages(
        profile, ocr_available=True, config={"vision_fallback": "file"}
    )
    assert [entry["source"] for entry in plan] == ["vision", "vision"]


def test_quality_gate_demotes_garbage_ocr_to_vision():
    plan = [
        {"page": 0, "kind": "scan", "source": "ocr", "chars": 0},
        {"page": 1, "kind": "scan", "source": "ocr", "chars": 0},
    ]
    pages_text = ["◆▯▮◇" * 20, LONG]
    gated = pdf_ocr.apply_quality_gate(
        plan,
        pages_text,
        config={
            "quality_gate": True,
            "min_page_chars": 50,
            "max_garbage_ratio": 0.35,
            "vision_fallback": "page",
        },
    )
    assert gated[0]["source"] == "vision"
    assert gated[0]["quality"]["ok"] is False
    assert gated[1]["source"] == "ocr"


def test_pages_argument_compresses_ranges():
    assert pdf_ocr._pages_argument([0, 2, 3, 7]) == "1,3-4,8"
    assert pdf_ocr._pages_argument([]) == ""


def test_ensure_text_pdf_sends_only_scan_pages(tmp_path, monkeypatch):
    calls = []

    def fake_run(exe, input_path, output_path, **kwargs):
        calls.append(kwargs.get("pages"))
        Path(output_path).write_bytes(Path(input_path).read_bytes())
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(pdf_ocr, "_run_ocrmypdf", fake_run)
    monkeypatch.setattr(
        pdf_ocr, "ocr_available",
        lambda *args, **kwargs: {
            "available": True, "ocrmypdf": "ocrmypdf", "tessdata": None,
        },
    )
    monkeypatch.setattr(
        pdf_ocr, "analyze_pdf", lambda path: {"pages_with_text": 1}
    )

    profile = [
        {"page": page, "kind": "text", "chars": 500} for page in range(10)
    ]
    profile[3]["kind"] = "scan"
    profile[3]["chars"] = 0

    pdf = _make_text_pdf(tmp_path / "book.pdf", [LONG])
    out, report = pdf_ocr.ensure_text_pdf(
        pdf,
        tmp_path / "work",
        profile=profile,
        config={"min_page_chars": 50, "ocr_pages_threshold": 0.3},
    )
    assert calls == [[3]]
    assert report["pages"] == [3]


def test_ensure_text_pdf_retries_whole_file_when_pages_is_unknown(
    tmp_path, monkeypatch
):
    calls = []

    def fake_run(exe, input_path, output_path, **kwargs):
        calls.append(kwargs.get("pages"))
        if kwargs.get("pages"):
            return subprocess.CompletedProcess([], 2, "", "unknown option --pages")
        Path(output_path).write_bytes(Path(input_path).read_bytes())
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(pdf_ocr, "_run_ocrmypdf", fake_run)
    monkeypatch.setattr(
        pdf_ocr, "ocr_available",
        lambda *args, **kwargs: {
            "available": True, "ocrmypdf": "ocrmypdf", "tessdata": None,
        },
    )
    monkeypatch.setattr(
        pdf_ocr, "analyze_pdf", lambda path: {"pages_with_text": 1}
    )

    profile = [
        {"page": page, "kind": "text", "chars": 500} for page in range(10)
    ]
    profile[3]["kind"] = "scan"
    profile[3]["chars"] = 0

    pdf = _make_text_pdf(tmp_path / "book.pdf", [LONG])
    out, report = pdf_ocr.ensure_text_pdf(
        pdf,
        tmp_path / "work",
        profile=profile,
        config={"min_page_chars": 50, "ocr_pages_threshold": 0.3},
    )
    assert calls == [[3], None]
    assert report["pages_fallback"] is True
    assert report["ok"] is True


def test_merge_page_chunks_renumbers_in_page_order():
    from app.pipeline.pdf_handler import merge_page_chunks

    text_chunks = [("chunk-0", "<p>page0</p>"), ("chunk-1", "<p>page2</p>")]
    text_map = {"chunk-0": ("page_0", 0), "chunk-1": ("page_2", 0)}
    vision_chunks = [("chunk-1", "<p>page1</p>")]
    vision_map = {"chunk-1": {"item": "page_1.html", "pos": 0}}

    all_chunks, chapter_map, id_map = merge_page_chunks(
        (text_chunks, text_map),
        (vision_chunks, vision_map),
    )

    assert [chunk_id for chunk_id, _ in all_chunks] == [
        "chunk-0", "chunk-1", "chunk-2",
    ]
    assert [text for _, text in all_chunks] == [
        "<p>page0</p>", "<p>page1</p>", "<p>page2</p>",
    ]
    # chapter_map is normalized to the tuple shape save_chunks() requires.
    assert chapter_map["chunk-1"] == ("page_1.html", 0)
    assert id_map[(0, "chunk-1")] == "chunk-2"


def test_merge_page_chunks_keeps_pieces_of_one_page_in_order():
    from app.pipeline.pdf_handler import merge_page_chunks

    chunks = [("chunk-0", "second"), ("chunk-1", "first")]
    chapter_map = {"chunk-0": ("page_0", 1), "chunk-1": ("page_0", 0)}

    all_chunks, _, _ = merge_page_chunks((chunks, chapter_map))
    assert [text for _, text in all_chunks] == ["first", "second"]
