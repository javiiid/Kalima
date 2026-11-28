# ============================================================
# app/output/html_pdf.py
# ============================================================
"""
The one PDF engine: HTML in, PDF out, through Chromium.

Every PDF this project produces goes through here -- the segment
writers in ``app/output/pdf.py``, the EPUB-rendered outputs in
``app/output/epub_convert.py`` and the source-page overlay in
``app/pipeline/pdf_handler.py``. Three reasons, all measured:

1. **Vazirmatn.** Chromium embeds the real face and writes a correct
   ``ToUnicode`` map, so Persian text is selectable and searchable.
   MuPDF's own HTML/text insertion path embeds the same face but
   extracts ``ت`` as U+04A5 and ``پ`` as U+0423 -- the glyphs render,
   the copy-paste is garbage. (Reproduced with both ``insert_htmlbox``
   and ``insert_textbox``; the font's cmap and glyph names are
   correct, so the defect is MuPDF's mapping, not the font.)
2. **Page numbers.** Chromium's footer template numbers pages and the
   number is the last text on the page, which is what the existing
   tests and the audit harness read.
3. **Flow.** Chromium breaks pages inside paragraphs, tables and
   figures properly, so a long book is a book rather than a stack of
   clipped boxes.

MuPDF's ``Story`` writer is kept in ``app/output/pdf.py`` as a
fallback for machines with neither Chromium nor Edge installed.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import fitz
from playwright.sync_api import Error, sync_playwright

from app.core.fonts import embedded_vazirmatn_font_faces

#: Base print stylesheet. Direction is decided per element by
#: :data:`PREPARE_DOCUMENT`; this file only owns geometry and type.
PRINT_CSS = """
html { background: white; color: black; }
body { max-width: none; margin: 0; padding: 0; font-size: 12pt; line-height: 1.8; }
body, p, li, td, th, h1, h2, h3, h4, h5, h6, blockquote, span, a, figcaption {
  font-family: Vazirmatn, sans-serif !important;
}
p { margin: 0 0 0.7em; orphans: 3; widows: 3; }
h1, h2, h3, h4, h5, h6 { line-height: 1.5; break-after: avoid; }
table { border-collapse: collapse; max-width: 100%; margin-block: 1em; }
td, th { border: 0.5pt solid #999; padding: 0.35em 0.6em; vertical-align: top; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
img, svg { max-width: 100%; height: auto; }
figure { break-inside: avoid; margin-inline: 0; }
pre, code { direction: ltr; unicode-bidi: isolate; font-family: monospace !important; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; text-align: left; }
ul, ol { padding-inline-start: 1.75em; padding-inline-end: 0; }
blockquote { margin-inline: 1.5em; }
a { overflow-wrap: anywhere; }
bdi { unicode-bidi: isolate; }
"""

#: Per-element direction, plus ``<bdi>`` isolation of Latin runs
#: inside RTL text so a URL or a product name does not scramble the
#: sentence around it.
PREPARE_DOCUMENT = r"""() => {
  const direction = (text, fallback = 'ltr') => {
    const sample = text.replace(/https?:\/\/\S+|\b[\w.+-]+@[\w.-]+\b/g, '');
    let rtl = 0, ltr = 0;
    for (const char of sample) {
      if (!/\p{L}/u.test(char)) continue;
      if (/\p{Script=Arabic}|\p{Script=Hebrew}/u.test(char)) rtl++;
      else ltr++;
    }
    return rtl + ltr ? (rtl > ltr ? 'rtl' : 'ltr') : fallback;
  };
  document.documentElement.dir = direction(document.body.textContent);
  document.documentElement.lang = document.documentElement.dir === 'rtl' ? 'fa' : 'en';
  for (const element of document.querySelectorAll('table,ul,ol,blockquote,p,h1,h2,h3,h4,h5,h6,li,td,th,figcaption,caption')) {
    const base = element.parentElement.closest('[dir]')?.dir || document.documentElement.dir;
    element.dir = direction(element.textContent, base);
    element.style.direction = element.dir;
    if (!['center', 'justify'].includes(element.style.textAlign)) {
      element.style.textAlign = element.dir === 'rtl' ? 'right' : 'left';
    }
  }
  for (const element of document.querySelectorAll('pre,code')) element.dir = 'ltr';
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  const latin = /(?:https?:\/\/[^\s<>]+|[A-Za-z0-9]+(?:[ .:/@_+#=\-]+[A-Za-z0-9]+)*)/g;
  for (const node of nodes) {
    if (node.parentElement.closest('script,style,pre,code,bdi')) continue;
    if (node.parentElement.closest('[dir]')?.dir !== 'rtl') continue;
    const fragment = document.createDocumentFragment();
    let offset = 0;
    for (const match of node.textContent.matchAll(latin)) {
      fragment.append(node.textContent.slice(offset, match.index));
      const isolate = document.createElement('bdi');
      isolate.dir = 'ltr';
      isolate.textContent = match[0];
      fragment.append(isolate);
      offset = match.index + match[0].length;
    }
    if (offset) {
      fragment.append(node.textContent.slice(offset));
      node.replaceWith(fragment);
    }
  }
}"""

def default_footer_template():
    """Chromium footer: the page number, centred in the bottom margin.

    The font faces are embedded in the template itself. Chromium renders
    header/footer templates as their own document, so without this the
    digits fall back to Arial and every Persian PDF ships a second,
    unasked-for font -- which is exactly what the typography test forbids.
    Latin digits, deliberately: a Persian numeral would need shaping in a
    document that has no bidi context.
    """

    return (
        embedded_vazirmatn_font_faces()
        + '<div style="width:100%;font-size:9px;color:#555555;'
        'text-align:center;font-family:Vazirmatn,sans-serif;">'
        '<span class="pageNumber"></span></div>'
    )

HEADER_TEMPLATE = "<span></span>"

#: Shrink-to-fit for fixed-size fragments (the source-page overlay).
#: A translation longer than the area it replaces is reduced in
#: quarter-point steps until it fits, rather than being clipped or
#: spilling onto a page that does not exist.
SHRINK_TO_FIT = r"""() => {
  const shrink = (element) => {
    let size = parseFloat(getComputedStyle(element).fontSize) || 12;
    let guard = 0;
    while (
      (element.scrollHeight > element.clientHeight + 1 ||
       element.scrollWidth > element.clientWidth + 1) &&
      size > 4 && guard++ < 400
    ) {
      size = Math.max(4, size - 0.25);
      element.style.fontSize = size + 'px';
    }
  };
  for (const element of document.querySelectorAll('[data-fit]')) shrink(element);
}"""


def _launch(playwright):
    """Chromium if Playwright downloaded it, else the system Edge.

    Playwright's own browser is the preferred path; Edge is the
    fallback that makes the desktop install work without a 150 MB
    download. Both are Chromium, so the PDF output is the same.
    """

    if Path(playwright.chromium.executable_path).exists():
        return playwright.chromium.launch(headless=True)
    try:
        return playwright.chromium.launch(channel="msedge", headless=True)
    except Error as exc:
        raise RuntimeError(
            "برای ساخت PDF فارسی، دستور python -m playwright install chromium را اجرا کنید."
        ) from exc


def _margin_dict(margin):
    """``"18mm 17mm"`` / ``"1cm 2cm 3cm 4cm"`` -> Playwright's dict."""

    if isinstance(margin, dict):
        return margin
    # Playwright accepts px/in/cm/mm only -- points are converted, because
    # every geometry constant in this project is in points.
    values = [_length(value) for value in str(margin).split()]
    if len(values) == 1:
        top = right = bottom = left = values[0]
    elif len(values) == 2:
        top = bottom = values[0]
        right = left = values[1]
    elif len(values) == 4:
        top, right, bottom, left = values
    else:
        raise ValueError(f"Unsupported margin '{margin}'")
    return {"top": top, "right": right, "bottom": bottom, "left": left}


def _length(value):
    text = str(value).strip()
    if text.endswith("pt"):
        try:
            return f"{float(text[:-2]) * 25.4 / 72:.4f}mm"
        except ValueError:
            return text
    return text


def _page_rule(page_size, margin):
    return f"@page {{ size: {page_size}; margin: {margin}; }}"


def _document(html, *, page_size, margin, extra_css="", title=None):
    """Wrap ``html`` in a printable document with the print stylesheet."""

    styles = _styles(page_size, margin, extra_css)
    if _looks_like_document(html):
        return _inject(html, styles, title)
    head = [
        "<!doctype html>",
        '<html><head><meta charset="utf-8">',
    ]
    if title:
        head.append(f"<title>{_escape(title)}</title>")
    head.append(styles + "</head><body>")
    return "".join(head) + html + "</body></html>"


def _escape(value):
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _styles(page_size, margin, extra_css=""):
    return (
        embedded_vazirmatn_font_faces()
        + "<style>"
        + _page_rule(page_size, margin)
        + PRINT_CSS
        + extra_css
        + "</style>"
    )


def _looks_like_document(html):
    """Whether ``html`` is already a whole document (pandoc output is)."""

    head = str(html or "")[:2048].lower()
    return "<html" in head or "<!doctype" in head


def _inject(html, styles, title=None):
    """Put the print stylesheet into an existing document's head.

    Wrapping a full document in another one would bury pandoc's own
    ``<head>`` inside ``<body>``, where its stylesheet is no longer
    guaranteed to apply.
    """

    html = str(html)
    if title and "<title" not in html[:4096].lower():
        styles = f"<title>{_escape(title)}</title>" + styles
    lowered = html.lower()
    position = lowered.find("</head>")
    if position != -1:
        return html[:position] + styles + html[position:]
    position = lowered.find("<body")
    if position != -1:
        return html[:position] + "<head>" + styles + "</head>" + html[position:]
    return styles + html


def _render(page, path, *, page_size, margin, footer, footer_template):
    """Print the already-loaded page to ``path``."""

    options = {
        "path": str(path),
        "print_background": True,
        "prefer_css_page_size": True,
        "display_header_footer": bool(footer),
    }
    if footer:
        options["header_template"] = HEADER_TEMPLATE
        options["footer_template"] = footer_template or default_footer_template()
        options["margin"] = _margin_dict(margin)
    page.pdf(**options)
    return path


def _open_page(context, html):
    page = context.new_page()
    page.set_content(html, wait_until="load")
    page.evaluate(PREPARE_DOCUMENT)
    page.evaluate(
        """async () => {
          await Promise.race([
            Promise.all([
              document.fonts.load('12pt Vazirmatn'),
              document.fonts.load('bold 12pt Vazirmatn'),
              document.fonts.ready,
            ]),
            new Promise((resolve, reject) =>
              setTimeout(() => reject(new Error('Font loading timed out')), 15000))
          ]);
        }"""
    )
    return page


def render_html_pdf(
    html,
    path,
    *,
    page_size="A4",
    margin="18mm 17mm",
    footer=True,
    footer_template=None,
    extra_css="",
    title=None,
    prepare=True,
):
    """Render one HTML document to ``path``.

    ``prepare=False`` skips the direction pass for a document that
    already carries its own ``dir`` attributes (the EPUB pipeline's
    pandoc output does not, but a caller that has done the work
    itself should not pay for it twice).
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = _document(
        html,
        page_size=page_size,
        margin=margin,
        extra_css=extra_css,
        title=title,
    )
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            context = browser.new_context(java_script_enabled=False)
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(document, wait_until="load")
            if prepare:
                page.evaluate(PREPARE_DOCUMENT)
            page.evaluate(
                """async () => {
                  await Promise.race([
                    Promise.all([
                      document.fonts.load('12pt Vazirmatn'),
                      document.fonts.load('bold 12pt Vazirmatn'),
                      document.fonts.ready,
                    ]),
                    new Promise((resolve, reject) =>
                      setTimeout(() => reject(new Error('Font loading timed out')), 15000))
                  ]);
                }"""
            )
            _render(
                page,
                path,
                page_size=page_size,
                margin=margin,
                footer=footer,
                footer_template=footer_template,
            )
        finally:
            browser.close()
    return path


def render_parts(
    parts,
    path,
    *,
    title=None,
    page_size="A4",
    margin="18mm 17mm",
    extra_css="",
    footer_template=None,
):
    """Render several documents and concatenate them into one PDF.

    ``parts`` is a sequence of ``(html, footer)`` pairs. Front matter
    is rendered with ``footer=False`` so it carries no page number;
    the body is a separate render, so its numbering starts at 1 --
    which is the contract every caller and test already relies on.

    The title metadata is set on the merged document because only the
    first part's ``<title>`` would otherwise survive.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [(html, bool(footer)) for html, footer in parts if html]
    if not parts:
        raise ValueError("render_parts needs at least one part")

    scratch = Path(tempfile.gettempdir())
    rendered = []
    try:
        with sync_playwright() as playwright:
            browser = _launch(playwright)
            try:
                context = browser.new_context(java_script_enabled=False)
                context.route("**/*", lambda route: route.abort())
                for index, (html, footer) in enumerate(parts):
                    target = scratch / f"kalima-part-{uuid.uuid4().hex}-{index}.pdf"
                    page = _open_page(
                        context,
                        _document(
                            html,
                            page_size=page_size,
                            margin=margin,
                            extra_css=extra_css,
                            title=title,
                        ),
                    )
                    try:
                        _render(
                            page,
                            target,
                            page_size=page_size,
                            margin=margin,
                            footer=footer,
                            footer_template=footer_template,
                        )
                    finally:
                        page.close()
                    rendered.append(target)
            finally:
                browser.close()

        merged = fitz.open()
        try:
            for part in rendered:
                with fitz.open(str(part)) as source:
                    merged.insert_pdf(source)
            if title:
                metadata = dict(merged.metadata or {})
                metadata["title"] = str(title)
                merged.set_metadata(metadata)
            merged.save(str(path), garbage=4, deflate=True)
        finally:
            merged.close()
    finally:
        for part in rendered:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
    return path


def render_fragments(fragments, path, *, title=None, extra_css=""):
    """Render fixed-size fragments, one PDF page each, in one pass.

    ``fragments`` is a sequence of ``(width_pt, height_pt, html)``.
    Each becomes its own page at exactly that size -- CSS named pages
    are what make the sizes differ within one document -- and the
    content is shrunk to fit rather than clipped.

    This is what the source-PDF overlay uses: the translation for a
    source page is rendered at the exact size of the area it
    replaces, then stamped onto the copied page with
    ``show_pdf_page``. One Chromium launch for the whole book.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fragments = list(fragments)
    if not fragments:
        raise ValueError("render_fragments needs at least one fragment")

    rules = []
    blocks = []
    for index, (width, height, html) in enumerate(fragments):
        name = f"frag{index}"
        rules.append(
            f"@page {name} {{ size: {width:.2f}pt {height:.2f}pt; margin: 0; }}"
            f" .{name} {{ page: {name}; width: {width:.2f}pt;"
            f" height: {height:.2f}pt; overflow: hidden; }}"
        )
        blocks.append(f'<div class="{name}" data-fit>{html}</div>')

    fragments_css = (
        "".join(rules)
        + " .frag-page { break-after: page; }"
        + " .frag-page:last-child { break-after: auto; }"
        + " body { font-size: 10pt; line-height: 1.75; }"
        + " p { margin: 0 0 0.5em; }"
        + extra_css
    )

    document = _document(
        "".join(f'<div class="frag-page">{block}</div>' for block in blocks),
        page_size="A4",
        margin="0",
        extra_css=fragments_css,
        title=title,
    )

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            context = browser.new_context(java_script_enabled=False)
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(document, wait_until="load")
            page.evaluate(PREPARE_DOCUMENT)
            page.evaluate(
                """async () => {
                  await Promise.race([
                    Promise.all([
                      document.fonts.load('10pt Vazirmatn'),
                      document.fonts.ready,
                    ]),
                    new Promise((resolve, reject) =>
                      setTimeout(() => reject(new Error('Font loading timed out')), 15000))
                  ]);
                }"""
            )
            page.evaluate(SHRINK_TO_FIT)
            _render(
                page,
                path,
                page_size="A4",
                margin="0",
                footer=False,
                footer_template=None,
            )
        finally:
            browser.close()
    return path


def write_html_pdf(html, path):
    """Backward-compatible entry point (the old ``rtl_pdf`` API)."""

    return render_html_pdf(html, path)
