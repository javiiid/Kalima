"""Translated EPUB outputs must keep the book's illustrations.

The text-only segment model flattens every chunk to plain text, so a DOCX or
PDF built from segments loses every image. For an EPUB source the writers are
fed the reassembled EPUB instead, and pandoc carries the media through.
"""
from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import fitz

from app.output.formats import generate_epub_outputs
from app.pipeline.epub_handler import EPUBHandler

PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


def _make_epub(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
            'version="1.0"><rootfiles><rootfile full-path="OPS/book.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OPS/book.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" '
            'unique-identifier="id"><metadata '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="id">images</dc:identifier>'
            '<dc:title>Images</dc:title><dc:language>en</dc:language>'
            '</metadata><manifest>'
            '<item id="chapter" href="chapter.xhtml" '
            'media-type="application/xhtml+xml"/>'
            '<item id="image" href="pixel.png" media-type="image/png"/>'
            '</manifest><spine><itemref idref="chapter"/></spine></package>',
        )
        archive.writestr(
            "OPS/chapter.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            "<p>Hello world.</p>"
            '<p><img src="pixel.png" alt="Embedded picture"/></p>'
            "</body></html>",
        )
        archive.writestr("OPS/pixel.png", PIXEL)
    return path


def _translated_epub(tmp_path: Path) -> Path:
    source = _make_epub(tmp_path / "source.epub")
    chunks, chapter_map, _contexts = EPUBHandler.build_chunks(source)
    translations = {
        chunk_id: chunk.replace("Hello world.", "سلام دنیا.")
        for chunk_id, chunk in chunks
    }
    target = tmp_path / "translated.epub"
    EPUBHandler.save_translated_epub(
        source, target, translations, chapter_map,
    )
    return target


def test_epub_rendered_outputs_keep_images(tmp_path):
    translated = _translated_epub(tmp_path)

    result = generate_epub_outputs(
        translated,
        ["docx", "translated_pdf", "markdown"],
        tmp_path / "out",
        "book",
        to_lang="FA",
    )

    assert set(result["generated"]) == {"docx", "translated_pdf", "markdown"}
    assert result["skipped"] == {}

    with zipfile.ZipFile(result["generated"]["docx"]) as archive:
        assert any(
            name.startswith("word/media/") for name in archive.namelist()
        )

    with fitz.open(result["generated"]["translated_pdf"]) as document:
        assert any(page.get_images() for page in document)

    markdown = Path(result["generated"]["markdown"]).read_text(
        encoding="utf-8"
    )
    assert "data:image/png;base64," in markdown


def test_epub_rendered_outputs_reject_text_only_formats(tmp_path):
    translated = _translated_epub(tmp_path)

    result = generate_epub_outputs(
        translated,
        ["txt_bilingual", "docx"],
        tmp_path / "out",
        "book",
        to_lang="FA",
    )

    assert "docx" in result["generated"]
    assert "txt_bilingual" in result["skipped"]
