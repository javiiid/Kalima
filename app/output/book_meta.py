# ============================================================
# app/output/book_meta.py
# ============================================================
"""
What the book says about itself: title, author, language, cover.

Every output used to be handed a bare ``title`` string -- the input
file's stem -- and nothing else. So a PDF had no author, no language
and no cover, and the DOCX core properties credited "J Book
Translate" as the creator of someone else's book.

This module reads the real values from the source file when it can
(EPUB's package document, a PDF's own metadata) and falls back to
what the caller knows. It never raises: a book whose metadata is
unreadable still gets an output, just a plainer one.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
import tempfile
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

DC = "http://purl.org/dc/elements/1.1/"
OPF = "http://www.idpf.org/2007/opf"
NCX = "http://www.daisy.org/z3986/2005/ncx/"
XHTML = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"


@dataclass
class BookMeta:
    """The bibliographic facts an output needs."""

    title: str = ""
    author: str = ""
    language: str = ""
    subject: str = ""
    keywords: list[str] = field(default_factory=list)
    #: The cover image as a ``data:`` URI, or "" when the book has none.
    cover: str = ""
    #: The cover image bytes, for formats that embed a file (DOCX).
    cover_bytes: bytes = b""
    cover_suffix: str = ""

    def with_fallbacks(self, title="", author="", language=""):
        """Fill the empty fields from the caller's knowledge."""

        if not self.title:
            self.title = str(title or "")
        if not self.author:
            self.author = str(author or "")
        if not self.language:
            self.language = str(language or "")
        return self

    def as_dict(self):
        return {
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "subject": self.subject,
            "keywords": list(self.keywords),
        }


def _opf_path(archive: zipfile.ZipFile) -> str | None:
    try:
        container = ElementTree.fromstring(
            archive.read("META-INF/container.xml")
        )
    except (KeyError, ElementTree.ParseError):
        return None
    node = container.find(".//{*}rootfile")
    return node.get("full-path") if node is not None else None


def _read_package(epub_path) -> tuple[zipfile.ZipFile, ElementTree.Element] | None:
    try:
        archive = zipfile.ZipFile(epub_path)
    except (OSError, zipfile.BadZipFile):
        return None
    opf_name = _opf_path(archive)
    if not opf_name:
        archive.close()
        return None
    try:
        package = ElementTree.fromstring(archive.read(opf_name))
    except (KeyError, ElementTree.ParseError):
        archive.close()
        return None
    return archive, package


def _text(package, name):
    node = package.find(f".//{{{DC}}}{name}")
    return (node.text or "").strip() if node is not None else ""


def _cover_data_uri(epub_path) -> tuple[str, bytes, str]:
    """The declared cover as ``(data URI, bytes, suffix)``, or empties."""

    from app.library.covers import extract_epub_cover

    try:
        with tempfile.TemporaryDirectory(prefix="kalima-cover-") as scratch:
            stored = extract_epub_cover(Path(epub_path), Path(scratch) / "cover")
            if stored is None:
                return "", b"", ""
            blob = stored.read_bytes()
            suffix = stored.suffix.lower()
    except Exception:  # noqa: BLE001 -- a cover is never worth failing an output
        return "", b"", ""
    media_type = mimetypes.guess_type(f"cover{suffix}")[0] or "image/png"
    encoded = base64.b64encode(blob).decode("ascii")
    return f"data:{media_type};base64,{encoded}", blob, suffix


def epub_meta(epub_path) -> BookMeta:
    """Title, author, language, subjects and cover from an EPUB."""

    meta = BookMeta()
    opened = _read_package(epub_path)
    if opened is None:
        return meta
    archive, package = opened
    try:
        meta.title = _text(package, "title")
        meta.author = _text(package, "creator")
        meta.language = _text(package, "language")
        meta.subject = _text(package, "description")
        meta.keywords = [
            (node.text or "").strip()
            for node in package.findall(f".//{{{DC}}}subject")
            if (node.text or "").strip()
        ]
    finally:
        archive.close()
    meta.cover, meta.cover_bytes, meta.cover_suffix = _cover_data_uri(epub_path)
    return meta


def pdf_meta(pdf_path) -> BookMeta:
    """Title and author from a PDF's own document information."""

    meta = BookMeta()
    try:
        import fitz

        with fitz.open(str(pdf_path)) as document:
            info = document.metadata or {}
    except Exception:  # noqa: BLE001
        return meta
    meta.title = str(info.get("title") or "").strip()
    meta.author = str(info.get("author") or "").strip()
    meta.subject = str(info.get("subject") or "").strip()
    keywords = str(info.get("keywords") or "").strip()
    meta.keywords = [item.strip() for item in keywords.split(",") if item.strip()]
    return meta


def book_meta(source=None, title="", author="", language="") -> BookMeta:
    """Metadata for ``source``, with the caller's values as fallbacks."""

    meta = BookMeta()
    if source:
        suffix = Path(str(source)).suffix.lower()
        try:
            if suffix == ".epub":
                meta = epub_meta(source)
            elif suffix == ".pdf":
                meta = pdf_meta(source)
        except Exception:  # noqa: BLE001
            meta = BookMeta()
    return meta.with_fallbacks(title=title, author=author, language=language)


def epub_toc_entries(epub_path) -> list[tuple[str, str]]:
    """The book's own chapters as ``(href, title)``, in reading order.

    Read from the EPUB 3 navigation document, falling back to the
    NCX. Used to label chapter headings and to build a PDF outline for
    a book rendered from its own XHTML, where the writer never sees the
    headings -- and where the file name ("chapter7.xhtml") is not a
    title a reader should ever be shown.
    """

    entries: list[tuple[str, str]] = []
    opened = _read_package(epub_path)
    if opened is None:
        return entries
    archive, package = opened
    try:
        nav_href = ""
        ncx_href = ""
        for item in package.findall(f".//{{{OPF}}}manifest/{{{OPF}}}item"):
            properties = (item.get("properties") or "").lower()
            media = (item.get("media-type") or "").lower()
            href = item.get("href") or ""
            if "nav" in properties.split():
                nav_href = href
            elif media == "application/x-dtbncx+xml":
                ncx_href = href
        base = ""
        opf_name = _opf_path(archive) or ""
        if "/" in opf_name:
            base = opf_name.rsplit("/", 1)[0] + "/"

        if nav_href:
            name = urllib.parse.unquote(base + nav_href)
            try:
                nav = ElementTree.fromstring(archive.read(name))
            except (KeyError, ElementTree.ParseError):
                nav = None
            if nav is not None:
                for anchor in nav.iter(f"{{{XHTML}}}a"):
                    text = " ".join((anchor.text or "").split())
                    if text:
                        entries.append((anchor.get("href") or "", text))
                if entries:
                    return entries

        if ncx_href:
            name = urllib.parse.unquote(base + ncx_href)
            try:
                ncx = ElementTree.fromstring(archive.read(name))
            except (KeyError, ElementTree.ParseError):
                ncx = None
            if ncx is not None:
                for point in ncx.iter(f"{{{NCX}}}navPoint"):
                    label = point.find(f"{{{NCX}}}navLabel/{{{NCX}}}text")
                    content = point.find(f"{{{NCX}}}content")
                    if label is None:
                        continue
                    text = " ".join((label.text or "").split())
                    if text:
                        entries.append((
                            content.get("src") if content is not None else "",
                            text,
                        ))
    finally:
        archive.close()
    return entries


def epub_toc_titles(epub_path) -> list[str]:
    """Just the titles, in reading order."""

    return [title for _href, title in epub_toc_entries(epub_path)]


_HEADING_RE = re.compile(r"<h([1-3])\b[^>]*>(.*?)</h\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def chapter_headings(epub_path) -> dict[str, str]:
    """Each chapter's first heading, keyed by its href.

    The EPUB's navigation document is not a reliable source of chapter
    titles -- real books ship TOCs that list only "Cover" and
    "Description", or one entry per page ("صفحهٔ 1"). The heading the
    chapter itself opens with is always the title a reader sees, so
    that is what the segment-based writers print above a chapter.
    """

    headings: dict[str, str] = {}
    opened = _read_package(epub_path)
    if opened is None:
        return headings
    archive, package = opened
    try:
        base = ""
        opf_name = _opf_path(archive) or ""
        if "/" in opf_name:
            base = opf_name.rsplit("/", 1)[0] + "/"
        for item in package.findall(f".//{{{OPF}}}manifest/{{{OPF}}}item"):
            media = (item.get("media-type") or "").lower()
            if media not in {"application/xhtml+xml", "text/html"}:
                continue
            href = item.get("href") or ""
            if not href:
                continue
            try:
                markup = archive.read(
                    urllib.parse.unquote(base + href)
                ).decode("utf-8", "replace")
            except KeyError:
                continue
            match = _HEADING_RE.search(markup)
            if match is None:
                continue
            text = " ".join(
                html.unescape(_TAG_RE.sub(" ", match.group(2))).split()
            )
            if text:
                headings[href] = text
    finally:
        archive.close()
    return headings
