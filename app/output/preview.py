# ============================================================
# app/output/preview.py
# ============================================================
"""
What an output looks like inside the app, without a download.

A browser can show a PDF on its own, but a DOCX is a ZIP of XML and
an EPUB is a container: neither opens in a tab. So the preview of
those two is text, extracted here and rendered as a plain, script-free
HTML page.

Everything in this module assumes the text came from a book someone
else wrote: it is escaped, never trusted, and the page carries no
script, no external stylesheet and no remote image. The CSP the web
layer sends with it (``sandbox; default-src 'none'``) is a second line
of defence, not the only one.
"""

from __future__ import annotations

import zipfile
from html import escape
from pathlib import Path
from xml.etree import ElementTree

from app.output.typography import has_rtl

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

#: A preview is for reading, not for archiving. A 900-page book would
#: otherwise build a multi-megabyte HTML page on every request.
MAX_PARAGRAPHS = 3000

PREVIEW_CSS = """
:root { color-scheme: light dark; }
body {
  margin: 0; padding: 24px 18px 64px;
  font-family: Vazirmatn, "Segoe UI", Tahoma, sans-serif;
  font-size: 16px; line-height: 1.9;
  background: #ffffff; color: #1d2430;
}
main { max-width: 46rem; margin: 0 auto; }
h1 { font-size: 1.35rem; line-height: 1.6; margin: 0 0 1.2em; }
p { margin: 0 0 0.85em; }
p.empty { margin: 0; height: 0.9em; }
.note {
  margin-top: 2em; padding-top: 1em; border-top: 1px solid #d8dee8;
  color: #6b7688; font-size: 0.85rem;
}
@media (prefers-color-scheme: dark) {
  body { background: #12161d; color: #e6ebf2; }
  .note { border-color: #2a3341; color: #8b97a8; }
}
"""


def _paragraph_text(paragraph) -> str:
    return " ".join(
        "".join(node.text or "" for node in paragraph.iter(f"{{{W}}}t")).split()
    )


def docx_paragraphs(path) -> list[str]:
    """The visible text of a DOCX, one entry per paragraph.

    Table rows are flattened onto one line each, because a preview that
    drops a table's text is worse than one that shows it without the
    grid. Walking the body's children rather than every ``w:p`` in the
    tree is what keeps a table's cells from being printed twice.
    """

    try:
        with zipfile.ZipFile(path) as archive:
            payload = archive.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile):
        return []
    try:
        document = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return []
    body = document.find(f"{{{W}}}body")
    if body is None:
        return []
    paragraphs: list[str] = []
    for element in body:
        if element.tag == f"{{{W}}}p":
            paragraphs.append(_paragraph_text(element))
        elif element.tag == f"{{{W}}}tbl":
            for row in element.iter(f"{{{W}}}tr"):
                cells = [
                    " ".join(
                        _paragraph_text(paragraph)
                        for paragraph in cell.findall(f"{{{W}}}p")
                    ).strip()
                    for cell in row.findall(f"{{{W}}}tc")
                ]
                if any(cells):
                    paragraphs.append(" | ".join(cells))
    return paragraphs


def preview_page(title: str, paragraphs, *, note: str = "") -> str:
    """A script-free HTML page for ``paragraphs``."""

    body = ["" if not text else str(text) for text in paragraphs or []]
    truncated = len(body) > MAX_PARAGRAPHS
    if truncated:
        body = body[:MAX_PARAGRAPHS]
    direction = "rtl" if has_rtl(" ".join(body[:200])) else "ltr"
    rendered = "".join(
        '<p class="empty"></p>' if not text else f"<p>{escape(text)}</p>"
        for text in body
    )
    tail = ""
    if truncated or note:
        message = note or (
            f"پیش‌نمایش {MAX_PARAGRAPHS} پاراگراف اول است؛ "
            "فایل کامل را دانلود کنید."
        )
        tail = f'<p class="note">{escape(message)}</p>'
    return (
        "<!doctype html>"
        f'<html lang="fa" dir="{direction}">'
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title>"
        f"<style>{PREVIEW_CSS}</style>"
        "</head><body><main>"
        f"<h1>{escape(title)}</h1>"
        f"{rendered}{tail}"
        "</main></body></html>"
    )


def docx_preview(path, title: str) -> str:
    """The DOCX preview page: the book's text, escaped, nothing else."""

    paragraphs = docx_paragraphs(path)
    if not paragraphs:
        return preview_page(
            title,
            [],
            note="متنی برای پیش‌نمایش در این فایل پیدا نشد؛ فایل را دانلود کنید.",
        )
    return preview_page(title, paragraphs)


def text_preview(path, title: str) -> str:
    """The preview page for a plain-text output (Markdown, TXT, SRT)."""

    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw = ""
    return preview_page(title, raw.splitlines())
