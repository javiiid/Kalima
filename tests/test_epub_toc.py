"""Tests for app.pipeline.epub_toc: automatic TOC + internal-link rebuild
after EPUB translation reassembly."""
from __future__ import annotations

import zipfile

import pytest

from app.pipeline.epub_toc import rebuild_epub_structure


def _write_epub(path, chapters, nav_old="OLD.xhtml", extra=None):
    """Build a minimal EPUB with spine chapters + stale nav.xhtml."""
    container = (
        '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
        ' version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    manifest_items = []
    spine_refs = []
    for idx, (_title, body) in enumerate(chapters):
        fname = f"ch{idx}.xhtml"
        manifest_items.append(f'<item id="ch{idx}" href="{fname}" media-type="application/xhtml+xml"/>')
        spine_refs.append(f'<itemref idref="ch{idx}"/>')
    opf = (
        f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" '
        f'version="3.0" unique-identifier="bookid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">urn:uuid:1234</dc:identifier><dc:title>Test Book</dc:title>'
        f'<dc:language>en</dc:language></metadata><manifest>'
        f'<item id="nav" href="{nav_old}" media-type="application/xhtml+xml" properties="nav"/>'
        f'{"".join(manifest_items)}'
        f'{"".join(f"<item id=\"extra{idx}\" href=\"extra{idx}.css\" media-type=\"text/css\"/>" for idx in range((extra or 0)))}'
        f'</manifest><spine>{"".join(spine_refs)}</spine></package>'
    )
    nav = (
        f'<?xml version="1.0"?><html><body><nav epub:type="toc"><ol>'
        f'<li><a href="{nav_old}">Old Title</a></li></ol></nav></body></html>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/nav.xhtml", nav)
        for idx, (_title, body) in enumerate(chapters):
            archive.writestr(f"OEBPS/ch{idx}.xhtml", body)
        for idx in range(extra or 0):
            archive.writestr(f"OEBPS/extra{idx}.css", "body{}")


def _read(path, name):
    with zipfile.ZipFile(path) as archive:
        return archive.read(name).decode("utf-8")


def test_rebuild_nav_and_internal_links(tmp_path):
    src = tmp_path / "src.epub"
    out = tmp_path / "out.epub"
    _write_epub(
        src,
        [
            ("Chapter One", '<html><body><h1>Chapter One</h1><p><a href="ch1.xhtml">go to chapter two</a></p></body></html>'),
            ("Chapter Two", '<html><body><h1>Chapter Two</h1><p>done</p></body></html>'),
        ],
    )
    rebuild_epub_structure(str(src), str(out))

    nav = _read(out, "OEBPS/nav.xhtml")
    assert "Chapter One" in nav
    assert "Chapter Two" in nav
    assert "Old Title" not in nav
    assert '<a href="ch0.xhtml">Chapter One</a>' in nav
    assert '<a href="ch1.xhtml">Chapter Two</a>' in nav

    ch0 = _read(out, "OEBPS/ch0.xhtml")
    assert 'href="ch1.xhtml"' in ch0  # internal link preserved as relative

    opf = _read(out, "OEBPS/content.opf")
    assert '<itemref idref="ch-0"/>' in opf
    assert '<itemref idref="ch-1"/>' in opf
    assert 'properties="nav"' in opf
    assert "Test Book" in opf  # metadata preserved
    # no duplicate manifest items / no namespace prefixes leaked
    assert opf.count('<item id="ch-0"') == 1
    assert opf.count('<item id="ch-1"') == 1
    assert "ns0:" not in opf


def test_asset_and_external_links_untouched(tmp_path):
    src = tmp_path / "src.epub"
    out = tmp_path / "out.epub"
    _write_epub(
        src,
        [
            (
                "Chapter One",
                '<html><body><h1>Chapter One</h1><p>'
                '<a href="img.jpg">image</a> '
                '<a href="https://example.com">external</a> '
                '<a href="#section">fragment</a></p></body></html>',
            ),
            ("Chapter Two", '<html><body><h1>Chapter Two</h1><p>done</p></body></html>'),
        ],
    )
    rebuild_epub_structure(str(src), str(out))
    ch0 = _read(out, "OEBPS/ch0.xhtml")
    assert 'href="img.jpg"' in ch0
    assert 'href="https://example.com"' in ch0
    assert 'href="#section"' in ch0


def test_in_place_rebuild(tmp_path):
    src = tmp_path / "book.epub"
    _write_epub(
        src,
        [
            ("Chapter One", '<html><body><h1>Chapter One</h1><p><a href="ch1.xhtml">next</a></p></body></html>'),
            ("Chapter Two", '<html><body><h1>Chapter Two</h1><p>done</p></body></html>'),
        ],
    )
    before = _read(src, "OEBPS/nav.xhtml")
    assert "Old Title" in before
    rebuild_epub_structure(str(src), str(src))  # in place
    after = _read(src, "OEBPS/nav.xhtml")
    assert "Old Title" not in after
    assert "Chapter One" in after


def test_manifest_hrefs_are_relative_to_the_opf_directory(tmp_path):
    """An OPF inside ``OEBPS/`` must not produce ``OEBPS/OEBPS/ch0.xhtml``.

    Pandoc (and every reader) resolves a manifest href against the OPF's own
    directory. The old writer used a helper that stripped a *file* dirname,
    so the prefix doubled and the rebuilt EPUB was unreadable.
    """
    src = tmp_path / "src.epub"
    out = tmp_path / "out.epub"
    _write_epub(
        src,
        [
            ("Chapter One", "<html><body><h1>Chapter One</h1><p>x</p></body></html>"),
            ("Chapter Two", "<html><body><h1>Chapter Two</h1><p>y</p></body></html>"),
        ],
    )
    rebuild_epub_structure(str(src), str(out))

    opf = _read(out, "OEBPS/content.opf")
    assert '<item id="ch-0" href="ch0.xhtml"' in opf
    assert '<item id="ch-1" href="ch1.xhtml"' in opf
    assert "OEBPS/ch0.xhtml" not in opf
    assert "OEBPS/OEBPS" not in opf


def test_rebuild_accepts_path_objects_in_place(tmp_path):
    """The job pipeline passes ``Path`` objects; ``Path + str`` used to raise."""
    src = tmp_path / "book.epub"
    _write_epub(
        src,
        [("Chapter One", "<html><body><h1>Chapter One</h1><p>x</p></body></html>")],
    )
    rebuild_epub_structure(src, src)
    assert "Old Title" not in _read(src, "OEBPS/nav.xhtml")


def test_in_place_failure_keeps_original_and_cleans_temp(tmp_path, monkeypatch):
    from app.pipeline import epub_toc

    src = tmp_path / "book.epub"
    _write_epub(
        src,
        [("Chapter One", "<html><body><h1>Chapter One</h1><p>x</p></body></html>")],
    )
    original = src.read_bytes()

    def fail_replace(*_args, **_kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(epub_toc.os, "replace", fail_replace)

    with pytest.raises(OSError):
        rebuild_epub_structure(str(src), str(src))

    assert src.read_bytes() == original
    assert not (tmp_path / "book.epub.rebuild-tmp").exists()


def test_chapter_titles_from_headings(tmp_path):
    src = tmp_path / "src.epub"
    out = tmp_path / "out.epub"
    _write_epub(
        src,
        [
            ("Real Title", '<html><body><h2>Real Title</h2><p>no h1</p></body></html>'),
        ],
    )
    rebuild_epub_structure(str(src), str(out))
    nav = _read(out, "OEBPS/nav.xhtml")
    assert "Real Title" in nav
    assert "Chapter 1" not in nav


def test_malformed_container_is_noop(tmp_path):
    src = tmp_path / "bad.epub"
    out = tmp_path / "out.epub"
    with zipfile.ZipFile(src, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", "not xml")
    rebuild_epub_structure(str(src), str(out))  # must not raise


def test_rebuild_resources_preserved(tmp_path):
    src = tmp_path / "src.epub"
    out = tmp_path / "out.epub"
    _write_epub(
        src,
        [
            ("Chapter One", '<html><body><h1>Chapter One</h1><p>x</p></body></html>'),
            ("Chapter Two", '<html><body><h1>Chapter Two</h1><p>y</p></body></html>'),
        ],
        extra=2,
    )
    rebuild_epub_structure(str(src), str(out))
    with zipfile.ZipFile(out) as archive:
        names = set(archive.namelist())
    assert "mimetype" in names
    assert "OEBPS/extra0.css" in names
    assert "OEBPS/extra1.css" in names
