"""Tests for the OCRmyPDF pre-layer (phase 2).

The behaviour worth protecting is not "OCRmyPDF runs" -- it is that a PDF which
already has text never pays for OCR, that a scan is recognized locally before
any provider call, and that a machine without OCRmyPDF/Tesseract degrades to the
vision fallback instead of raising. The integration tests are skipped when the
tools are not installed, which is the whole point of "OCR is optional".
"""
from __future__ import annotations

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
