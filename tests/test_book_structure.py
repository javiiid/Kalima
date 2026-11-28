"""The book furniture every output owes a reader.

A translated book used to be a wall of paragraphs: no cover, no
contents, no outline, no author, and chapter headings taken from the
file name. These tests pin the parts a reader sees first.
"""
from __future__ import annotations

import base64
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import fitz

from app.output.book_meta import book_meta, epub_toc_entries
from app.output.docx import write_docx
from app.output.epub_convert import write_epub_output
from app.output.rtl_docx import fix_docx_typography

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)

CHAPTERS = ("Chapter One", "Chapter Two", "Chapter Three")


def _make_epub(path: Path, *, cover: bool = True) -> Path:
    """A three-chapter EPUB with a nav document and (optionally) a cover."""

    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
        'properties="nav"/>',
        '<item id="cover" href="cover.xhtml" '
        'media-type="application/xhtml+xml"/>',
    ]
    spine = ['<itemref idref="cover"/>']
    body = []
    for index, title in enumerate(CHAPTERS, start=1):
        manifest.append(
            f'<item id="ch{index}" href="chapter{index}.xhtml" '
            'media-type="application/xhtml+xml"/>'
        )
        spine.append(f'<itemref idref="ch{index}"/>')
        body.append((
            f"OPS/chapter{index}.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            f"<h1>{title}</h1>"
            f"<p>Body text of {title}.</p>"
            "</body></html>",
        ))
    if cover:
        manifest.append(
            '<item id="cover-image" href="cover.png" media-type="image/png" '
            'properties="cover-image"/>'
        )
    nav_items = "".join(
        f'<li><a href="chapter{index}.xhtml">{title}</a></li>'
        for index, title in enumerate(CHAPTERS, start=1)
    )
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
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            'unique-identifier="id"><metadata '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="id">structure</dc:identifier>'
            "<dc:title>Structure Test</dc:title>"
            "<dc:creator>Test Author</dc:creator>"
            "<dc:language>en</dc:language>"
            "</metadata><manifest>"
            + "".join(manifest)
            + "</manifest><spine>"
            + "".join(spine)
            + "</spine></package>",
        )
        archive.writestr(
            "OPS/nav.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><body>'
            f'<nav epub:type="toc"><ol>{nav_items}</ol></nav>'
            "</body></html>",
        )
        archive.writestr(
            "OPS/cover.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            '<p><img src="cover.png" alt="Cover"/></p>'
            "</body></html>",
        )
        for name, content in body:
            archive.writestr(name, content)
        if cover:
            archive.writestr("OPS/cover.png", PIXEL)
    return path


def _tails(document):
    return [
        " ".join(document[i].get_text().splitlines()[-1:]).strip()
        for i in range(len(document))
    ]


def _book_pdf(tmp_path: Path, **kwargs):
    source = _make_epub(tmp_path / "source.epub", **kwargs)
    target = tmp_path / "book.pdf"
    write_epub_output(source, target, "translated_pdf", "EN")
    return source, fitz.open(str(target))


class TestBookMeta:
    def test_epub_fields_are_read(self, tmp_path):
        source = _make_epub(tmp_path / "a.epub")
        meta = book_meta(source)
        assert meta.title == "Structure Test"
        assert meta.author == "Test Author"
        assert meta.cover.startswith("data:image/png;base64,")
        assert meta.cover_bytes

    def test_the_navigation_titles_are_the_chapters(self, tmp_path):
        source = _make_epub(tmp_path / "a.epub")
        assert [title for _href, title in epub_toc_entries(source)] == list(CHAPTERS)

    def test_a_missing_cover_is_not_an_error(self, tmp_path):
        source = _make_epub(tmp_path / "a.epub", cover=False)
        meta = book_meta(source, title="Fallback")
        assert meta.title == "Structure Test"
        assert meta.cover == ""


class TestEpubPdf:
    def test_the_first_page_is_a_cover(self, tmp_path):
        _source, document = _book_pdf(tmp_path)
        try:
            cover = document[0].get_text()
            assert "Structure Test" in cover
            assert "Test Author" in cover
            # The cover is a title page: no footer number on it.
            assert not _tails(document)[0].isdigit()
        finally:
            document.close()

    def test_the_cover_carries_the_books_own_image(self, tmp_path):
        _source, document = _book_pdf(tmp_path)
        try:
            assert document[0].get_images()
        finally:
            document.close()

    def test_the_contents_page_lists_the_chapters(self, tmp_path):
        _source, document = _book_pdf(tmp_path)
        try:
            contents = " ".join(document[1].get_text().split())
            assert "Contents" in contents
            for title in CHAPTERS:
                assert title in contents, title
        finally:
            document.close()

    def test_the_outline_points_at_the_chapters(self, tmp_path):
        _source, document = _book_pdf(tmp_path)
        try:
            outline = document.get_toc()
            assert [entry[1] for entry in outline] == list(CHAPTERS)
            assert [entry[2] for entry in outline] == sorted(
                entry[2] for entry in outline
            )
            assert outline[0][2] > 2  # after the cover and the contents
        finally:
            document.close()

    def test_the_metadata_is_the_books_own(self, tmp_path):
        _source, document = _book_pdf(tmp_path)
        try:
            assert document.metadata.get("title") == "Structure Test"
            assert document.metadata.get("author") == "Test Author"
        finally:
            document.close()

    def test_no_file_name_is_printed_as_a_heading(self, tmp_path):
        _source, document = _book_pdf(tmp_path)
        try:
            text = "".join(page.get_text() for page in document)
            assert "chapter1.xhtml" not in text
            assert "cover.xhtml" not in text
        finally:
            document.close()


def _docx(tmp_path: Path):
    source = _make_epub(tmp_path / "a.epub")
    target = tmp_path / "book.docx"
    write_docx(
        [{"id": "c1", "chapter": "chapter1.xhtml", "target": "Body text."}],
        target,
        title="Structure Test",
        to_lang="EN",
        meta=book_meta(source),
    )
    fix_docx_typography(target, meta=book_meta(source))
    return target


def _part(path: Path, name: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(name).decode("utf-8")


class TestDocx:
    def test_the_cover_comes_before_the_table_of_contents(self, tmp_path):
        document = ElementTree.fromstring(_part(_docx(tmp_path), "word/document.xml"))
        body = document.find(f"{{{W}}}body")
        styles = []
        for element in body:
            style = element.find(f"{{{W}}}pPr/{{{W}}}pStyle")
            styles.append(style.get(f"{{{W}}}val") if style is not None else "")
        assert "KalimaCoverEnd" in styles
        toc_at = next(
            index for index, element in enumerate(body)
            if any("TOC" in (item.text or "") for item in element.iter(f"{{{W}}}instrText"))
        )
        assert styles.index("KalimaCoverEnd") < toc_at

    def test_the_author_is_the_creator(self, tmp_path):
        core = _part(_docx(tmp_path), "docProps/core.xml")
        assert "<dc:creator>Test Author</dc:creator>" in core
        assert "J Book Translate" not in core

    def test_the_body_pages_are_numbered(self, tmp_path):
        path = _docx(tmp_path)
        footer = _part(path, "word/footer1.xml")
        assert "PAGE" in footer
        document = _part(path, "word/document.xml")
        assert "footerReference" in document
        assert "titlePg" in document  # the cover is unnumbered
        assert 'PartName="/word/footer1.xml"' in _part(path, "[Content_Types].xml")
