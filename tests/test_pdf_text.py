"""Tests for the PDF text fast path.

The behaviour worth protecting is not "text comes out" -- PyMuPDF already does
that. It is that a text-bearing PDF is recognized before any provider call is
made, and that the chunk ids it produces are contiguous. A gap in those ids is
not a cosmetic bug: ``PDFHandler.save_translated_pdf`` orders translations by
``int(chunk_id.split('-')[1])``, so a missing id silently drops a page from the
finished book.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.pipeline import pdf_text


def _make_pdf(path: Path, pages: list[str]) -> Path:
    """Write a small PDF with a real text layer using PyMuPDF."""
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # type: ignore[no-redef]

    document = pymupdf.open()
    for body in pages:
        page = document.new_page()
        page.insert_text((72, 72), body)
    document.save(str(path))
    document.close()
    return path


def _make_image_only_pdf(path: Path, pages: int = 3) -> Path:
    """A PDF with pages but no text layer, standing in for a scan."""
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # type: ignore[no-redef]

    document = pymupdf.open()
    for _ in range(pages):
        document.new_page()
    document.save(str(path))
    document.close()
    return path


LONG = "The cartographer unrolled the map and weighed its corners carefully. " * 4


# ============================================================
# Detection
# ============================================================

def test_has_extractable_text_true_for_text_pdf(tmp_path):
    pdf = _make_pdf(tmp_path / "text.pdf", [LONG, LONG])
    assert pdf_text.has_extractable_text(pdf) is True


def test_has_extractable_text_false_for_image_only_pdf(tmp_path):
    pdf = _make_image_only_pdf(tmp_path / "scan.pdf", pages=3)
    assert pdf_text.has_extractable_text(pdf) is False


def test_short_text_page_is_not_counted(tmp_path):
    # A page number or running head shorter than the threshold must not promote
    # a scan to a text PDF.
    pdf = _make_pdf(tmp_path / "tiny.pdf", ["7", "8", "9"])
    assert pdf_text.has_extractable_text(pdf) is False


def test_mixed_ratio_governs_decision(tmp_path):
    # Two of four pages have text -> ratio 0.5 -> text path when threshold is 0.5.
    pdf = _make_pdf(tmp_path / "mixed.pdf", [LONG, "", LONG, ""])
    assert pdf_text.has_extractable_text(pdf, min_page_ratio=0.5) is True
    # Raising the bar above the observed ratio flips the decision.
    assert pdf_text.has_extractable_text(pdf, min_page_ratio=0.75) is False


def test_page_text_stats(tmp_path):
    pdf = _make_pdf(tmp_path / "stats.pdf", [LONG, LONG, ""])
    stats = pdf_text.page_text_stats(pdf)
    assert stats["total_pages"] == 3
    assert stats["pages_with_text"] == 2
    assert stats["chars"] > 0


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        pdf_text.extract_pages_text(tmp_path / "nope.pdf")


# ============================================================
# HTML conversion
# ============================================================

def test_page_text_to_html_wraps_paragraphs():
    result = pdf_text.page_text_to_html("First line\nsame paragraph.\n\nSecond paragraph.")
    assert result == "<p>First line same paragraph.</p>\n<p>Second paragraph.</p>"


def test_page_text_to_html_escapes_markup():
    result = pdf_text.page_text_to_html("Tom & Jerry <not a tag>")
    assert "&amp;" in result
    assert "&lt;not a tag&gt;" in result
    assert "<not a tag>" not in result


def test_page_text_to_html_empty():
    assert pdf_text.page_text_to_html("") == ""
    assert pdf_text.page_text_to_html("   \n  ") == ""


def test_pages_to_html_length_matches_pages(tmp_path):
    pdf = _make_pdf(tmp_path / "pages.pdf", [LONG, "", LONG])
    pages = pdf_text.extract_pages_text(pdf)
    assert len(pages) == 3
    assert len(pdf_text.pages_to_html(pages)) == 3


# ============================================================
# Chunk building -- the contract the pipeline depends on
# ============================================================

def test_build_chunks_ids_are_contiguous(tmp_path):
    pdf = _make_pdf(tmp_path / "chunks.pdf", [LONG, LONG, LONG])
    all_chunks, chapter_map, contexts = pdf_text.build_chunks(pdf)

    assert all_chunks, "expected at least one chunk"
    ids = [chunk_id for chunk_id, _ in all_chunks]
    assert ids == [f"chunk-{i}" for i in range(len(ids))]
    assert set(chapter_map) == set(ids)
    for chunk_id, _ in all_chunks:
        item, pos = chapter_map[chunk_id]
        assert item.startswith("page_")
        assert isinstance(pos, int)


def test_build_chunks_skips_blank_pages_without_gap(tmp_path):
    # A blank page in the middle must not create an id gap.
    pdf = _make_pdf(tmp_path / "gap.pdf", [LONG, "", LONG])
    all_chunks, _, _ = pdf_text.build_chunks(pdf)
    ids = [chunk_id for chunk_id, _ in all_chunks]
    assert ids == [f"chunk-{i}" for i in range(len(ids))]


def test_build_chunks_returns_no_chunks_for_scan(tmp_path):
    pdf = _make_image_only_pdf(tmp_path / "empty.pdf", pages=2)
    all_chunks, chapter_map, contexts = pdf_text.build_chunks(pdf)
    assert all_chunks == []
    assert chapter_map == {}
    assert contexts == {}


def test_build_chunks_needs_no_provider(tmp_path, monkeypatch):
    """The fast path must not touch the network. Prove it by removing the client.

    ``pdf_text`` imports nothing from ``openai`` today; this test fails loudly
    if that ever changes, because the whole point of the fast path is that a
    text PDF costs no API call at extraction time.
    """
    for name in list(sys.modules):
        if name == "openai" or name.startswith("openai."):
            monkeypatch.setitem(sys.modules, name, None)

    pdf = _make_pdf(tmp_path / "offline.pdf", [LONG, LONG])
    all_chunks, _, _ = pdf_text.build_chunks(pdf)
    assert all_chunks


# ============================================================
# Tesseract discovery (calibration OCR)
# ============================================================
#
# Tests for the calibration PDF OCR branch's Tesseract lookup. Written as
# separate tests because the defect being fixed was environmental: a correct
# Tesseract install was invisible to the service whenever it did not inherit
# the launching shell's PATH (a service, a container, an IDE run button).

def test_tesseract_helper_functions_exist():
    from app.calibration import documents
    for name in ("tesseract_path", "tessdata_path", "configure_tesseract_env",
                 "available_ocr_languages"):
        assert callable(getattr(documents, name)), name


def test_tesseract_path_found_without_shell_path(monkeypatch):
    """Discovery must not depend on PATH already containing Tesseract."""
    import os
    from app.calibration import documents

    monkeypatch.setattr(documents, "_TESSERACT_EXE", None, raising=False)
    cleaned = os.pathsep.join(
        p for p in os.environ.get("PATH", "").split(os.pathsep) if "esser" not in p
    )
    monkeypatch.setenv("PATH", cleaned)

    exe = documents.tesseract_path()
    if exe is None:
        import pytest
        pytest.skip("Tesseract is not installed on this machine")
    assert exe.is_file()


def test_tessdata_prefers_directory_with_most_languages(monkeypatch, tmp_path):
    """The richest tessdata wins; an eng-only directory must not shadow fas.

    Both candidates are built as real directories under the same LOCALAPPDATA
    root, which is how this actually happens on a machine: the installer drops
    an eng-only ``tessdata`` next to the binary, and a user later adds language
    packs to the per-user copy. The per-user one must win.
    """
    from app.calibration import documents

    local = tmp_path / "AppData"
    installed = local / "Tesseract-OCR" / "tessdata"
    user = tmp_path / "userdata" / "tessdata"
    installed.mkdir(parents=True)
    user.mkdir(parents=True)
    (installed / "eng.traineddata").write_bytes(b"x")
    for name in ("eng", "fas", "ara"):
        (user / f"{name}.traineddata").write_bytes(b"x")

    monkeypatch.setattr(documents, "_TESSDATA_DIR", None, raising=False)
    monkeypatch.setattr(documents, "tesseract_path", lambda: None)
    monkeypatch.setenv("TESSDATA_PREFIX", str(user))
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    chosen = documents.tessdata_path()
    assert chosen is not None
    assert len(list(chosen.glob("*.traineddata"))) == 3


def test_configure_sets_env_when_available(monkeypatch):
    import os
    from app.calibration import documents

    monkeypatch.setattr(documents, "_TESSERACT_EXE", None, raising=False)
    if not documents.configure_tesseract_env():
        import pytest
        pytest.skip("Tesseract is not installed on this machine")
    assert "TESSDATA_PREFIX" in os.environ
    assert documents.available_ocr_languages()
