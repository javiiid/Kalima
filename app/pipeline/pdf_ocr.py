"""Local OCR pre-layer for scanned PDFs -- the OCRmyPDF integration.

Why this exists
---------------
Phase 1 (``pdf_text.py``) taught the pipeline to read a PDF that *already*
carries a text layer, locally and for free. That left one gap: a scanned PDF
has no text, so ``pdf_text.has_extractable_text`` returns ``False`` and the
whole file falls back to the per-page vision path -- one paid image request per
page, and no translation memory.

This module fills that gap. It runs OCRmyPDF once, locally, over the file and
produces a PDF that *does* carry a text layer. From that point on the file is
indistinguishable from a text PDF: it rides the chunker and translation memory
that ``pdf_text`` and the EPUB path already share.

The one flag that matters
-------------------------
OCRmyPDF is always invoked with ``--skip-text``: a page that already has text is
left completely alone. So a text PDF pays nothing for this step, and a *mixed*
file (some pages text, some scans) is solved page by page -- the strongest
argument for using a mature tool here instead of re-implementing per-page
detection.

Scope and safety
----------------
No network calls and no ``openai`` import. Everything here is local: OCRmyPDF,
Tesseract, and PyMuPDF. When OCRmyPDF or Tesseract is missing, or OCR fails,
this module says so plainly and the caller keeps its existing vision fallback --
installing OCR is optional, never a hard dependency.

Runtime requirements (learned the hard way on Windows)
------------------------------------------------------
* OCRmyPDF 17.x shells out to Tesseract. It needs a tessdata directory that
  contains **both** ``configs/hocr`` and the requested ``*.traineddata``. On a
  machine where the installer's tessdata and the per-user language packs live in
  different folders, neither folder alone works -- they must be resolved
  together (see ``_usable_tessdata``).
* OCRmyPDF writes a scratch copy of the input into a temp dir. If ``TEMP`` is
  not writable it dies with ``PermissionError``, so we hand it an explicit
  writable temp dir under the job.
* ``--output-type pdf`` (not ``pdfa``) avoids the Ghostscript requirement.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


# Project language codes -> Tesseract traineddata codes. Kept small and
# explicit: a wrong code silently degrades OCR, so the mapping is visible here
# rather than inferred.
TESSERACT_LANGUAGE = {
    "EN": "eng",
    "FA": "fas",
    "DE": "deu",
    "FR": "fra",
    "AR": "ara",
}

DEFAULT_OCR_LANGUAGE = "eng"

# How long OCRmyPDF may run before we give up and fall back to vision. OCR is
# CPU-bound and a big scanned book can take minutes; this is a safety valve,
# not a target.
DEFAULT_TIMEOUT_SECONDS = 1800


# ============================================================
# Discovery
# ============================================================

def _candidate_ocrmypdf_paths():
    """Yield paths where an ``ocrmypdf`` entry point might live."""
    found = shutil.which("ocrmypdf")
    if found:
        yield Path(found)
    # The console script sits in the Scripts dir of whichever interpreter has
    # it installed. Check the running interpreter first, then the common
    # per-user Python root.
    roots = [
        Path(sys.executable).parent,
        Path(sys.executable).parent / "Scripts",
        Path(sys.executable).parent.parent / "Scripts",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
    ]
    for root in roots:
        if not str(root) or str(root) == ".":
            continue
        for name in ("ocrmypdf", "ocrmypdf.exe"):
            yield root / name
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for py in Path(local).glob("Python*/**/Scripts/ocrmypdf.exe"):
            yield py


def ocrmypdf_path() -> Path | None:
    """Absolute path to the ``ocrmypdf`` executable, or None when absent."""
    for candidate in _candidate_ocrmypdf_paths():
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _tesseract_helpers():
    """Import the shared Tesseract resolver lazily to avoid import cycles."""
    from app.calibration import documents

    return documents


def _tessdata_dirs() -> list[Path]:
    """Every tessdata directory we know about, richest first.

    A machine commonly has two: the installer's own ``tessdata`` next to the
    binary (which ships ``configs/hocr``) and a per-user directory where extra
    language packs were dropped (which has the languages but no ``configs``).
    Neither is complete on its own, so callers get the whole list.
    """
    dirs: list[Path] = []
    env = os.environ.get("TESSDATA_PREFIX")
    if env and Path(env).is_dir():
        dirs.append(Path(env))
    try:
        helpers = _tesseract_helpers()
        exe = helpers.tesseract_path()
    except Exception:  # noqa: BLE001
        exe = None
    if exe:
        dirs += [exe.parent / "tessdata", exe.parent.parent / "share" / "tessdata"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Tesseract-OCR" / "tessdata")
    seen: list[Path] = []
    for directory in dirs:
        try:
            if directory.is_dir() and directory not in seen:
                seen.append(directory)
        except OSError:
            continue
    return seen


def _hocr_configs_dir() -> Path | None:
    """A tessdata dir that ships ``configs/hocr`` (the installer's own)."""
    for directory in _tessdata_dirs():
        try:
            if (directory / "configs" / "hocr").is_file():
                return directory
        except OSError:
            continue
    return None


def _traineddata_file(language: str) -> Path | None:
    """The first ``<language>.traineddata`` found across known tessdata dirs."""
    for directory in _tessdata_dirs():
        try:
            candidate = directory / f"{language}.traineddata"
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _direct_usable_tessdata(languages: set[str]) -> Path | None:
    """A single dir with ``configs/hocr`` *and* all the wanted languages.

    This is the happy path: a normal Tesseract install has both. Returning None
    here does not mean OCR is impossible -- ``ensure_tessdata`` can still merge
    the split pieces together.
    """
    wanted = {lang for lang in languages if lang}
    for directory in _tessdata_dirs():
        try:
            if not (directory / "configs" / "hocr").is_file():
                continue
            installed = {p.stem for p in directory.glob("*.traineddata")}
        except OSError:
            continue
        if wanted and not wanted <= installed:
            continue
        return directory
    return None


def ensure_tessdata(languages: set[str], work_dir) -> Path | None:
    """Return a tessdata dir OCRmyPDF can use, merging split installs if needed.

    A machine often keeps the installer's ``configs/hocr`` and the per-user
    language packs in two different folders. Neither works alone: without
    ``configs/hocr`` Tesseract cannot emit the hOCR OCRmyPDF parses, and without
    the pack OCR fails on the language. When no single directory has both, this
    assembles one under the job's work dir -- the ``configs`` tree is a few KB,
    and only the requested language (plus ``osd``) is copied.
    """
    wanted = {lang for lang in languages if lang}
    direct = _direct_usable_tessdata(wanted)
    if direct is not None:
        return direct

    configs_dir = _hocr_configs_dir()
    if configs_dir is None:
        return None

    merged = Path(work_dir) / "tessdata"
    merged.mkdir(parents=True, exist_ok=True)

    target_configs = merged / "configs"
    if not (target_configs / "hocr").is_file():
        shutil.copytree(configs_dir / "configs", target_configs, dirs_exist_ok=True)

    for language in wanted | {"osd"}:
        source = _traineddata_file(language)
        if source is not None:
            destination = merged / source.name
            if not destination.exists():
                shutil.copy2(source, destination)

    if not (merged / "configs" / "hocr").is_file():
        return None
    return merged


def ocr_available(language: str = DEFAULT_OCR_LANGUAGE, work_dir=None) -> dict:
    """Report whether OCRmyPDF can actually run, and why not when it cannot.

    Returns a dict so callers can log a precise reason without re-reading the
    environment. ``available`` is the single field the pipeline branches on.
    """
    info: dict = {
        "available": False,
        "ocrmypdf": None,
        "tesseract": None,
        "tessdata": None,
        "languages": set(),
        "reason": "",
    }

    exe = ocrmypdf_path()
    info["ocrmypdf"] = str(exe) if exe else None
    if exe is None:
        info["reason"] = "ocrmypdf executable not found"
        return info

    try:
        helpers = _tesseract_helpers()
        tesseract = helpers.tesseract_path()
        languages = set(helpers.available_ocr_languages())
    except Exception as exc:  # noqa: BLE001
        info["reason"] = f"tesseract lookup failed: {exc}"
        return info

    info["tesseract"] = str(tesseract) if tesseract else None
    info["languages"] = languages
    if tesseract is None:
        info["reason"] = "tesseract not found"
        return info

    if language and languages and language not in languages:
        info["reason"] = (
            f"tesseract language '{language}' not installed "
            f"(have: {', '.join(sorted(languages)) or 'none'})"
        )
        return info

    wanted = {language} if language else set()
    tessdata = _direct_usable_tessdata(wanted)
    if tessdata is None and work_dir is not None:
        # No single directory has both configs/hocr and the pack; assemble one.
        try:
            tessdata = ensure_tessdata(wanted, work_dir)
        except OSError as exc:
            info["reason"] = f"could not assemble tessdata: {exc}"
            return info
    if tessdata is None:
        info["reason"] = "no tessdata directory with configs/hocr"
        return info
    if not (tessdata / "configs" / "hocr").is_file():
        info["reason"] = f"tessdata '{tessdata}' has no configs/hocr"
        return info
    info["tessdata"] = str(tessdata)

    info["available"] = True
    return info


def resolve_language(from_lang: str | None, installed: set[str] | None = None) -> str:
    """Map a project language code to a Tesseract code, with a safe fallback.

    An exact match wins. If the mapped pack is not installed, fall back to
    English when present, else to any installed language, so a missing pack
    degrades OCR quality rather than failing the job.
    """
    mapped = TESSERACT_LANGUAGE.get((from_lang or "").strip().upper())
    if mapped and (not installed or mapped in installed):
        return mapped
    if installed:
        if "eng" in installed:
            return "eng"
        return sorted(installed)[0]
    return mapped or DEFAULT_OCR_LANGUAGE


# ============================================================
# Analysis
# ============================================================

def analyze_pdf(pdf_path) -> dict:
    """Classify a PDF locally as ``text``, ``scan`` or ``mixed``.

    Built on ``pdf_text.page_text_stats`` so the definition of "has text" is the
    exact one the fast path already uses -- there is only one threshold in the
    codebase, not two that can drift.
    """
    from app.pipeline import pdf_text

    stats = pdf_text.page_text_stats(pdf_path)
    total = int(stats["total_pages"])
    with_text = int(stats["pages_with_text"])
    ratio = float(stats["ratio"])

    if total == 0 or with_text == 0:
        kind = "scan"
    elif with_text == total:
        kind = "text"
    else:
        kind = "mixed"

    return {
        "kind": kind,
        "total_pages": total,
        "pages_with_text": with_text,
        "chars": int(stats["chars"]),
        "ratio": ratio,
        "needs_ocr": kind != "text",
    }


# ============================================================
# Execution
# ============================================================

def _run_ocrmypdf(
    exe: Path,
    input_path: Path,
    output_path: Path,
    *,
    language: str,
    tessdata: Path | None,
    temp_dir: Path,
    timeout: int,
    jobs: int | None = None,
) -> subprocess.CompletedProcess:
    """Invoke OCRmyPDF once with the flags this project depends on.

    ``--skip-text`` is the whole point: pages with text are never touched, so a
    text PDF costs nothing and a mixed PDF is solved page by page.
    """
    cmd = [
        str(exe),
        "--skip-text",
        "--language", language,
        "--output-type", "pdf",
        "--optimize", "1",
        str(input_path),
        str(output_path),
    ]
    if jobs:
        cmd[1:1] = ["--jobs", str(jobs)]

    env = dict(os.environ)
    # OCRmyPDF copies the input into a scratch dir; a non-writable TEMP aborts
    # the whole run with PermissionError before OCR even starts.
    writable = temp_dir / "ocrmypdf-temp"
    writable.mkdir(parents=True, exist_ok=True)
    for key in ("TEMP", "TMP", "TMPDIR"):
        env[key] = str(writable)
    if tessdata is not None:
        env["TESSDATA_PREFIX"] = str(tessdata)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def ensure_text_pdf(
    input_path,
    work_dir,
    *,
    language: str | None = None,
    from_lang: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    jobs: int | None = None,
    force: bool = False,
) -> tuple[Path, dict]:
    """Return a PDF with a usable text layer, running OCR only when needed.

    Returns ``(path, report)``. ``path`` is the original input when the file
    already has text (nothing is ever modified in place), or a new OCR'd PDF
    written next to the job's work dir. ``report`` carries ``used`` (whether OCR
    ran), ``ok`` (whether the result is usable) and ``reason`` for logging.

    Never raises for the ordinary "OCR is not available / did not help" cases:
    the caller decides whether to keep its vision fallback.
    """
    input_path = Path(input_path)
    work_dir = Path(work_dir)
    report: dict = {"used": False, "ok": False, "reason": "", "output": None}

    if not force:
        analysis = analyze_pdf(input_path)
        report["analysis"] = analysis
        if analysis["kind"] == "text":
            report["ok"] = True
            report["reason"] = "already has a text layer; OCR not needed"
            report["output"] = str(input_path)
            return input_path, report

    installed: set[str] | None = None
    try:
        installed = set(_tesseract_helpers().available_ocr_languages()) or None
    except Exception:  # noqa: BLE001
        installed = None
    lang = language or resolve_language(from_lang, installed)

    work_dir.mkdir(parents=True, exist_ok=True)

    availability = ocr_available(lang, work_dir=work_dir)
    if not availability["available"]:
        report["reason"] = availability["reason"] or "ocr not available"
        return input_path, report

    output_path = work_dir / f"{input_path.stem}_ocr.pdf"

    try:
        result = _run_ocrmypdf(
            Path(availability["ocrmypdf"]),
            input_path,
            output_path,
            language=lang,
            tessdata=Path(availability["tessdata"]) if availability["tessdata"] else None,
            temp_dir=work_dir,
            timeout=timeout,
            jobs=jobs,
        )
    except subprocess.TimeoutExpired:
        report["used"] = True
        report["reason"] = f"ocr timed out after {timeout}s"
        return input_path, report
    except (OSError, subprocess.SubprocessError) as exc:
        report["used"] = True
        report["reason"] = f"ocr failed to start: {exc}"
        return input_path, report

    report["used"] = True

    if result.returncode != 0 or not output_path.exists():
        tail = (result.stderr or "").strip().splitlines()
        report["reason"] = (
            f"ocrmypdf exit {result.returncode}: "
            f"{tail[-1] if tail else 'no stderr'}"
        )
        return input_path, report

    after = analyze_pdf(output_path)
    report["analysis_after"] = after
    if after["pages_with_text"] == 0:
        # OCR ran but produced nothing usable. Kept as a distinct signal so the
        # caller can fall back to vision for this file.
        report["reason"] = "ocr ran but produced no extractable text"
        return input_path, report

    report["ok"] = True
    report["reason"] = "ocr produced a text layer"
    report["output"] = str(output_path)
    return output_path, report
