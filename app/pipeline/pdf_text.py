"""Local text extraction for PDFs -- the text fast path.

Why this exists
---------------
The PDF pipeline used to render every page to an image and send each image to
the provider as a vision request. For a book that already carries a text layer
that is pure waste: the text is sitting in the file, and extracting it costs
nothing. This module pulls that text out locally so a text-bearing PDF can ride
the same chunker and translation memory that EPUB already uses.

Scope
-----
Phase 1 only. This decides whether a PDF has extractable text and, if so, turns
the text into the exact chunk shape the rest of the pipeline expects. It makes
no network calls and imports nothing from ``openai``. OCR of image-only PDFs is
out of scope and stays on the existing vision path.

The contract
------------
``build_chunks`` returns ``(all_chunks, chapter_map, contexts)`` where
``all_chunks`` is ``list[tuple[str, str]]`` of ``("chunk-N", html)`` ids numbered
contiguously from zero. The ids must be contiguous because
``PDFHandler.save_translated_pdf`` orders translations by
``int(chunk_id.split('-')[1])``; a gap silently drops pages from the output.
"""

from __future__ import annotations

import html as _html
import re
from pathlib import Path


# A page counts as "has text" when its stripped text reaches this length. Below
# it a page is treated as image-only: a stray page number or running head is not
# a usable text layer.
TEXT_MIN_CHARS_PER_PAGE = 50

# Fraction of pages that must carry text before the whole file is treated as
# text-bearing. Below this the file is more scan than text, so the vision path
# keeps its old behaviour and phase 3 handles the mixed case properly.
TEXT_MIN_PAGE_RATIO = 0.5

_BLANK_LINE = re.compile(r"\n\s*\n")


def _open_pdf(pdf_path):
    """Open a PDF with PyMuPDF, tolerating either import name."""
    try:
        import pymupdf
    except ImportError:  # older PyMuPDF ships as ``fitz``
        import fitz as pymupdf  # type: ignore[no-redef]

    return pymupdf.open(str(pdf_path))


def extract_pages_text(pdf_path) -> list[str]:
    """Return the extracted text of every page, in document order.

    A page that raises while extracting contributes an empty string, so the
    returned list always has one entry per page and indexes stay aligned with
    the source document.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Input PDF does not exist: {pdf_path}")

    pages: list[str] = []
    with _open_pdf(pdf_path) as document:
        for page in document:
            try:
                raw = page.get_text("text")
            except Exception:
                raw = ""
            pages.append(raw or "")
    return pages


def page_text_stats(
    pdf_path,
    *,
    min_chars_per_page: int = TEXT_MIN_CHARS_PER_PAGE,
) -> dict[str, int | float]:
    """Summarize how much text a PDF carries. Used for logging and decisions."""
    pages = extract_pages_text(pdf_path)
    total_pages = len(pages)
    chars = sum(len(text) for text in pages)
    pages_with_text = sum(
        1 for text in pages if len(text.strip()) >= min_chars_per_page
    )
    ratio = (pages_with_text / total_pages) if total_pages else 0.0
    return {
        "total_pages": total_pages,
        "pages_with_text": pages_with_text,
        "chars": chars,
        "ratio": ratio,
    }


def has_extractable_text(
    pdf_path,
    *,
    min_chars_per_page: int = TEXT_MIN_CHARS_PER_PAGE,
    min_page_ratio: float = TEXT_MIN_PAGE_RATIO,
) -> bool:
    """True when enough pages carry real text to skip the vision path."""
    stats = page_text_stats(pdf_path, min_chars_per_page=min_chars_per_page)
    if not stats["total_pages"]:
        return False
    return stats["ratio"] >= min_page_ratio


def page_text_to_html(text: str) -> str:
    """Convert one page of plain text to simple paragraph markup.

    The chunker segments on block tags, so blank-line separated paragraphs
    become real blocks instead of one giant block that has to be cut on
    sentence boundaries. Text is escaped because page text routinely contains
    ``&`` and angle brackets.
    """
    text = (text or "").strip()
    if not text:
        return ""

    paragraphs = []
    for block in _BLANK_LINE.split(text):
        # PyMuPDF ends each visual line with a newline; join them into flowing
        # prose so the result reads as a paragraph rather than broken lines.
        joined = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if joined:
            paragraphs.append(f"<p>{_html.escape(joined)}</p>")
    return "\n".join(paragraphs)


def pages_to_html(pages: list[str]) -> list[str]:
    """Convert a list of page texts to a list of HTML fragments."""
    return [page_text_to_html(text) for text in pages]


def _split_for_page(fragment: str, settings: dict) -> tuple[list[str], dict[int, str]]:
    """Split one page fragment the way the EPUB path splits a chapter.

    Kept deliberately identical to ``epub_handler._split_for_build`` so PDF and
    EPUB agree on what a chunk is, and so the same config governs both.
    """
    if not settings.get("semantic_chunking"):
        from app.pipeline.html_processor import split_html_by_paragraph

        return split_html_by_paragraph(fragment, 10000), {}

    from app.pipeline.semantic_chunker import SemanticChunker

    chunker = SemanticChunker(
        max_tokens=settings["chunk_max_tokens"],
        context_window=settings["chunk_context_window"],
    )
    chunks = chunker.chunk(fragment)
    return [chunk.html for chunk in chunks], {
        index: chunk.context_before
        for index, chunk in enumerate(chunks)
        if chunk.context_before
    }


def build_chunks(pdf_path) -> tuple[list[tuple[str, str]], dict, dict[str, str]]:
    """Extract a text PDF and build the pipeline's chunk structures.

    Returns ``(all_chunks, chapter_map, contexts)`` with contiguous
    ``chunk-N`` ids. Pages without text produce no chunks, so the numbering
    stays gapless and the output builder never skips a position.

    This function makes no network calls. It is the whole point of the fast
    path that a text-bearing PDF never reaches the provider at this stage.
    """
    from app.core.config import get_chunking_config

    settings = get_chunking_config()
    pages = extract_pages_text(pdf_path)
    pages_html = pages_to_html(pages)

    all_chunks: list[tuple[str, str]] = []
    chapter_map: dict[str, tuple[str, int]] = {}
    contexts: dict[str, str] = {}

    counter = 0
    for page_index, page_html in enumerate(pages_html):
        if not page_html:
            continue

        pieces, page_contexts = _split_for_page(page_html, settings)
        for pos, piece in enumerate(pieces):
            chunk_id = f"chunk-{counter}"
            all_chunks.append((chunk_id, piece))
            # The original PDF page this chunk came from, for reporting and for
            # any later per-page work. Not used to position output PDF pages.
            chapter_map[chunk_id] = (f"page_{page_index}", pos)
            context = page_contexts.get(pos)
            if context:
                contexts[chunk_id] = context
            counter += 1

    return all_chunks, chapter_map, contexts
