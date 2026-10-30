"""Integration test: the real EPUB reassembly path rebuilds the TOC.

Unlike ``tests/test_epub_toc.py`` (which exercises ``rebuild_epub_structure``
directly), this file drives ``reassemble_translation`` end to end with a
fabricated translation -- no API calls, no network. It proves that a normal
job's final EPUB has a regenerated ``nav.xhtml`` whose links point at the
translated chapters, and that a rebuild failure leaves the saved output
usable.
"""
from __future__ import annotations

import posixpath
import zipfile
from xml.etree import ElementTree

import pytest

import app.pipeline.epub_pipeline as epub_pipeline
from app.pipeline.epub_handler import EPUBHandler
from app.pipeline.epub_pipeline import reassemble_translation
from app.pipeline.html_processor import split_html_by_paragraph

XHTML_NS = "{http://www.w3.org/1999/xhtml}"
CHAPTERS = {
    "OEBPS/ch1.xhtml": (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>The Beginning</h1>"
        '<p>The story starts here and <a href="ch2.xhtml">continues in chapter two</a>.</p>'
        "</body></html>"
    ),
    "OEBPS/ch2.xhtml": (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>The Middle</h1>"
        '<p>Chapter two links back to <a href="ch1.xhtml">chapter one</a>.</p>'
        "</body></html>"
    ),
    "OEBPS/ch3.xhtml": (
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<h1>The End</h1>"
        "<p>The last page.</p>"
        "</body></html>"
    ),
}
TRANSLATIONS = {
    "The Beginning": "آغاز",
    "The Middle": "میانه",
    "The End": "پایان",
    "The story starts here and": "داستان از اینجا شروع می‌شود و",
    "continues in chapter two": "در فصل دو ادامه می‌یابد",
    "Chapter two links back to": "فصل دو به",
    "chapter one": "فصل یک",
    "The last page.": "آخرین صفحه.",
}
STALE_NAV = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
    "<body><nav epub:type=\"toc\"><ol>"
    '<li><a href="ch1.xhtml">Old Title One</a></li>'
    '<li><a href="ch2.xhtml">Old Title Two</a></li>'
    "</ol></nav></body></html>"
)


def _write_epub(path):
    container = (
        '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
        ' version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf"'
        ' media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    manifest = (
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="ch3" href="ch3.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="style" href="style.css" media-type="text/css"/>'
    )
    spine = (
        '<itemref idref="ch1"/><itemref idref="ch2"/><itemref idref="ch3"/>'
    )
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="bookid">urn:uuid:toc-e2e</dc:identifier>'
        "<dc:title>TOC E2E</dc:title><dc:language>en</dc:language></metadata>"
        f"<manifest>{manifest}</manifest><spine>{spine}</spine></package>"
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/nav.xhtml", STALE_NAV)
        archive.writestr("OEBPS/style.css", "body { margin: 0; }")
        for name, content in CHAPTERS.items():
            archive.writestr(name, content)


def _translated_chunks(chapter_map):
    """Translate every chapter chunk by string replacement (same split as the
    handler, so this mirrors a real translation run without an API call)."""
    translations = {}
    for chunk_id, (filename, position) in chapter_map.items():
        if filename not in CHAPTERS:
            continue
        pieces = split_html_by_paragraph(CHAPTERS[filename])
        chunk = pieces[position]
        for source, target in TRANSLATIONS.items():
            chunk = chunk.replace(source, target)
        translations[chunk_id] = chunk
    return translations


def _read(path, name):
    with zipfile.ZipFile(path) as archive:
        return archive.read(name).decode("utf-8")


@pytest.fixture(autouse=True)
def _deterministic_splitter(monkeypatch):
    """Force paragraph chunking even if the local config enables semantic
    chunking; the test's split must match the handler's save-time split."""
    monkeypatch.setattr(
        "app.pipeline.epub_handler._chunk_settings",
        lambda: {
            "semantic_chunking": False,
            "chunk_max_tokens": 1200,
            "chunk_context_window": 2,
        },
    )


def test_reassemble_regenerates_toc_and_chapter_links(tmp_path):
    source = tmp_path / "book.epub"
    output = tmp_path / "book-fa.epub"
    _write_epub(source)

    _, chapter_map, _ = EPUBHandler.build_chunks(str(source))
    translations = _translated_chunks(chapter_map)
    assert translations

    reassemble_translation(
        str(source), str(output), chapter_map, translations
    )

    # The assembled archive is a valid EPUB and the translated text landed.
    assert zipfile.is_zipfile(output)
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert names[0] == "mimetype"
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert "OEBPS/style.css" in names
    chapter_one = _read(output, "OEBPS/ch1.xhtml")
    assert "آغاز" in chapter_one

    # nav.xhtml is regenerated from the translated headings.
    nav_text = _read(output, "OEBPS/nav.xhtml")
    assert "Old Title" not in nav_text
    nav = ElementTree.fromstring(nav_text.encode("utf-8"))
    links = nav.findall(f".//{XHTML_NS}nav/{XHTML_NS}ol/{XHTML_NS}li/{XHTML_NS}a")
    assert [link.text for link in links] == ["آغاز", "میانه", "پایان"]

    # Every TOC href resolves to a chapter that exists in the archive.
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    nav_dir = posixpath.dirname("OEBPS/nav.xhtml")
    targets = [
        posixpath.normpath(posixpath.join(nav_dir, link.attrib["href"]))
        for link in links
    ]
    assert targets == ["OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml", "OEBPS/ch3.xhtml"]
    assert set(targets) <= names

    # Internal chapter links are relative and resolve to a real chapter.
    assert 'href="ch2.xhtml"' in chapter_one
    assert 'href="../OEBPS/ch2.xhtml"' not in chapter_one
    assert 'href="ch1.xhtml"' in _read(output, "OEBPS/ch2.xhtml")

    # The OPF spine follows the translated chapter order and still carries
    # the nav + non-chapter resources.
    opf = _read(output, "OEBPS/content.opf")
    assert '<item id="nav"' in opf
    assert 'href="style.css"' in opf
    assert opf.count('<itemref idref="ch-') == 3
    assert (
        opf.index('idref="ch-0"')
        < opf.index('idref="ch-1"')
        < opf.index('idref="ch-2"')
    )


def test_rebuild_failure_does_not_break_the_job(tmp_path, monkeypatch):
    source = tmp_path / "book.epub"
    output = tmp_path / "book-fa.epub"
    _write_epub(source)

    _, chapter_map, _ = EPUBHandler.build_chunks(str(source))
    translations = _translated_chunks(chapter_map)

    def explode(*_args, **_kwargs):
        raise RuntimeError("simulated rebuild failure")

    monkeypatch.setattr(epub_pipeline, "rebuild_epub_structure", explode)

    reassemble_translation(str(source), str(output), chapter_map, translations)

    # The job still produced a readable EPUB with the translation applied and
    # the pre-rebuild (stale but valid) nav document intact.
    assert zipfile.is_zipfile(output)
    assert "آغاز" in _read(output, "OEBPS/ch1.xhtml")
    assert "Old Title One" in _read(output, "OEBPS/nav.xhtml")
    assert not (tmp_path / "book-fa.epub.rebuild-tmp").exists()
