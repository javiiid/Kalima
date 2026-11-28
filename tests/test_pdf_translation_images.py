"""Translated PDFs must keep the source pages' images.

The old writer built a fresh text-only page per chunk, so every figure in a
PDF disappeared. The new path copies the source page, redacts only its text,
and writes the translation over the original text area.
"""
from __future__ import annotations

import base64
from pathlib import Path

import fitz

from app.pipeline.pdf_handler import PDFHandler
from app.pipeline.pdf_text import build_chunks

PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


def _make_pdf(path: Path) -> Path:
    image = path.with_suffix(".png")
    image.write_bytes(PIXEL)

    document = fitz.open()
    page = document.new_page(width=400, height=500)
    page.insert_text((50, 80), "Hello original text", fontsize=14)
    page.insert_image(fitz.Rect(50, 150, 250, 300), filename=str(image))

    page = document.new_page(width=400, height=500)
    page.insert_text((50, 80), "Second page text", fontsize=14)

    document.save(str(path))
    document.close()
    return path


def _translations(chunks):
    return {
        chunk_id: text.replace(
            "Hello original text", "TRANSLATED ONE"
        ).replace("Second page text", "TRANSLATED TWO")
        for chunk_id, text in chunks
    }


def test_translated_pdf_keeps_source_images(tmp_path):
    source = _make_pdf(tmp_path / "source.pdf")
    chunks, chapter_map, _contexts = build_chunks(source)

    output = tmp_path / "translated.pdf"
    PDFHandler.save_translated_pdf(
        _translations(chunks),
        output,
        original_pdf_path=source,
        chapter_map=chapter_map,
    )

    with fitz.open(output) as document:
        assert document.page_count == 2
        assert document[0].get_images()
        assert "TRANSLATED ONE" in document[0].get_text()
        assert "Hello original text" not in document[0].get_text()
        assert "TRANSLATED TWO" in document[1].get_text()
        assert not document[1].get_images()


def test_translated_pdf_without_source_keeps_old_page_per_chunk_behaviour(
    tmp_path,
):
    source = _make_pdf(tmp_path / "source.pdf")
    chunks, _chapter_map, _contexts = build_chunks(source)

    output = tmp_path / "translated.pdf"
    PDFHandler.save_translated_pdf(_translations(chunks), output)

    with fitz.open(output) as document:
        assert document.page_count == len(chunks)
        assert not any(page.get_images() for page in document)


def test_bilingual_pdf_keeps_images_on_translated_pages(tmp_path):
    source = _make_pdf(tmp_path / "source.pdf")
    chunks, chapter_map, _contexts = build_chunks(source)

    output = tmp_path / "bilingual.pdf"
    PDFHandler.save_bilingual_pdf(
        source,
        _translations(chunks),
        output,
        chapter_map=chapter_map,
    )

    with fitz.open(output) as document:
        assert document.page_count == 4
        assert document[0].get_images()
        assert document[1].get_images()
        assert "TRANSLATED ONE" in document[1].get_text()


def test_pdf_source_outputs_leave_no_temp_copy(tmp_path):
    """The uncompressed ``.temp.pdf`` duplicate must not survive the job."""
    source = _make_pdf(tmp_path / "source.pdf")
    chunks, chapter_map, _contexts = build_chunks(source)

    translated = tmp_path / "translated.pdf"
    PDFHandler.save_translated_pdf(
        _translations(chunks),
        translated,
        original_pdf_path=source,
        chapter_map=chapter_map,
    )
    bilingual = tmp_path / "bilingual.pdf"
    PDFHandler.save_bilingual_pdf(
        source,
        _translations(chunks),
        bilingual,
        chapter_map=chapter_map,
    )

    assert not (tmp_path / "translated.temp.pdf").exists()
    assert not (tmp_path / "bilingual.temp.pdf").exists()
