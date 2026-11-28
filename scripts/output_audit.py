"""Phase 0 output audit harness.

Builds a small fixture set locally -- no API key, no network -- runs every
output writer, and reports what each file actually contains:

* PDF: page count, embedded fonts, page numbers, image count, a text sample,
  and whether the extracted text carries Arabic presentation forms.
* DOCX: media parts, ``w:bidi`` / ``w:rtl`` counts, embedded ``odttf`` fonts,
  TOC field, heading count, and how much Persian text it holds.
* EPUB: spine length, nav entries, media parts.
* Markdown / TXT / JSON / SRT: size and the few structural numbers that
  matter.

Every PDF is also rendered to PNG so a human can look at the thing instead
of trusting a metric. The report ends with a "Findings" section that turns
the measurements into plain sentences -- that is the part Phase 1 works
from.

Usage:

    python scripts/output_audit.py
    python scripts/output_audit.py --out output/audit --dpi 100
    python scripts/output_audit.py --no-png
    python scripts/output_audit.py --max-pages 4
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import fitz

from app.output.formats import generate_epub_outputs, generate_outputs
from app.output.segments import build_segments
from app.pipeline.epub_handler import EPUBHandler
from app.pipeline.epub_pipeline import reassemble_translation
from app.pipeline.pdf_handler import PDFHandler


# A 1x1 transparent PNG. Small enough to inline, real enough for pandoc and
# PyMuPDF to treat as an image.
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)

PERSIAN = "این یک متن آزمایشی فارسی است که باید راست‌به‌چپ خوانده شود."

#: Arabic presentation forms (U+FB50..U+FEFF). A PDF that extracts these
#: instead of the base characters is shaped-but-not-searchable.
_PRESENTATION = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]")
_PERSIAN_CHARS = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_LATIN_CHARS = re.compile(r"[A-Za-z]")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_epub(path: Path) -> Path:
    """A two-chapter EPUB with a heading, a paragraph and one image."""
    path.parent.mkdir(parents=True, exist_ok=True)
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
            '<dc:identifier id="id">audit-book</dc:identifier>'
            "<dc:title>Audit Book</dc:title><dc:language>en</dc:language>"
            "<dc:creator>Audit Author</dc:creator>"
            "</metadata><manifest>"
            '<item id="c1" href="chapter1.xhtml" '
            'media-type="application/xhtml+xml"/>'
            '<item id="c2" href="chapter2.xhtml" '
            'media-type="application/xhtml+xml"/>'
            '<item id="img" href="pixel.png" media-type="image/png"/>'
            "</manifest><spine>"
            '<itemref idref="c1"/><itemref idref="c2"/>'
            "</spine></package>",
        )
        archive.writestr(
            "OPS/chapter1.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
            "<title>Chapter One</title></head><body>"
            "<h1>Chapter One</h1>"
            "<p>Hello world.</p>"
            "<p>This paragraph carries an image.</p>"
            '<p><img src="pixel.png" alt="Audit picture"/></p>'
            "</body></html>",
        )
        archive.writestr(
            "OPS/chapter2.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
            "<title>Chapter Two</title></head><body>"
            "<h1>Second chapter.</h1>"
            "<p>The second chapter has its own text.</p>"
            "</body></html>",
        )
        archive.writestr("OPS/pixel.png", PIXEL)
    return path


def make_text_pdf(path: Path) -> Path:
    """A one-page PDF with a real text layer and one image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_text(
            (72, 84),
            "Original English sentence for the audit.",
            fontsize=12,
        )
        page.insert_image(fitz.Rect(72, 120, 172, 220), stream=PIXEL)
        document.save(path)
    finally:
        document.close()
    return path


def make_scanned_pdf(path: Path) -> Path:
    """A one-page PDF whose only content is an image of text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    source = fitz.open()
    try:
        page = source.new_page(width=595, height=842)
        page.insert_text(
            (72, 84),
            "Scanned page for the audit.",
            fontsize=16,
        )
        pixmap = page.get_pixmap(dpi=150)
    finally:
        source.close()

    document = fitz.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_image(page.rect, pixmap=pixmap)
        document.save(path)
    finally:
        document.close()
    return path


def make_srt(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nHello world.\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nA second subtitle line.\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def _translate_epub(source: Path, out_dir: Path) -> tuple[Path, list, dict, dict]:
    chunks, chapter_map, _contexts = EPUBHandler.build_chunks(source)
    translations = {}
    for chunk_id, html in chunks:
        translations[chunk_id] = (
            html.replace("Hello world.", PERSIAN)
            .replace("Second chapter.", "فصل دوم.")
            .replace(
                "The second chapter has its own text.",
                "فصل دوم متن خودش را دارد.",
            )
        )
    translated = out_dir / "translated.epub"
    # Mirror the real job path, which also rebuilds nav.xhtml and the spine.
    reassemble_translation(source, translated, chapter_map, translations)
    return translated, chunks, chapter_map, translations


def run_epub_job(source: Path, out_dir: Path) -> list[tuple[str, str, Path]]:
    """Generate every EPUB-source output and return (source, format, path)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    translated, chunks, chapter_map, translations = _translate_epub(
        source, out_dir,
    )
    segments = build_segments(
        chunks, translations, chapter_map, "epub",
    )
    text_result = generate_outputs(
        segments,
        ["json_segments", "txt_bilingual", "srt"],
        output_dir=out_dir,
        base_name="epub-book",
        filetype="epub",
        title="Audit Book",
        to_lang="FA",
    )
    epub_result = generate_epub_outputs(
        translated,
        ["docx", "translated_pdf", "mobile_pdf", "bilingual_pdf", "markdown"],
        out_dir,
        "epub-book",
        to_lang="FA",
        segments=segments,
    )
    produced = [("epub", "translated_epub", translated)]
    for result in (text_result, epub_result):
        for name, item_path in result["generated"].items():
            produced.append(("epub", name, Path(item_path)))
    return produced


def run_pdf_job(
    source: Path, out_dir: Path, label: str,
) -> list[tuple[str, str, Path]]:
    """Generate the PDF-source outputs, including the image-preserving overlay."""
    out_dir.mkdir(parents=True, exist_ok=True)
    translations = {
        "chunk-0": f"<p>{PERSIAN}</p>",
    }
    chapter_map = {"chunk-0": ("page_0000.html", 0)}
    translated_pdf = out_dir / "translated.pdf"
    PDFHandler.save_translated_pdf(
        translations,
        translated_pdf,
        original_pdf_path=source,
        chapter_map=chapter_map,
    )
    segments = [
        {
            "id": "chunk-0",
            "position": 0,
            "source": "Original English sentence for the audit.",
            "target": PERSIAN,
            "format": "pdf",
            "chapter": "page_0000.html",
            "flagged": False,
            "notes": [],
        }
    ]
    result = generate_outputs(
        segments,
        ["docx", "markdown", "txt_bilingual", "json_segments", "mobile_pdf", "bilingual_pdf"],
        output_dir=out_dir,
        base_name="pdf-book",
        filetype="pdf",
        title="Audit PDF",
        to_lang="FA",
    )
    produced = [(label, "translated_pdf", translated_pdf)]
    for name, item_path in result["generated"].items():
        produced.append((label, name, Path(item_path)))
    return produced


def run_srt_job(source: Path, out_dir: Path) -> list[tuple[str, str, Path]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    segments = [
        {
            "id": "chunk-0",
            "position": 0,
            "source": "Hello world.",
            "target": PERSIAN,
            "format": "srt",
            "chapter": "block-1.srt",
            "flagged": False,
            "notes": [],
        },
        {
            "id": "chunk-1",
            "position": 1,
            "source": "A second subtitle line.",
            "target": "خط دوم زیرنویس.",
            "format": "srt",
            "chapter": "block-2.srt",
            "flagged": False,
            "notes": [],
        },
    ]
    result = generate_outputs(
        segments,
        ["docx", "markdown", "txt_bilingual", "json_segments", "srt"],
        output_dir=out_dir,
        base_name="srt-book",
        filetype="srt",
        title="Audit SRT",
        to_lang="FA",
    )
    return [("srt", name, Path(item_path)) for name, item_path in result["generated"].items()]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _last_line(page) -> str:
    lines = [line.strip() for line in page.get_text().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def audit_pdf(path: Path) -> dict:
    with fitz.open(path) as document:
        pages = len(document)
        fonts = sorted({font[3] for page in document for font in page.get_fonts()})
        images = sum(len(page.get_images(full=True)) for page in document)
        numbers = [page for page in document if _last_line(page).isdigit()]
        text = unicodedata.normalize(
            "NFKC", "".join(page.get_text() for page in document),
        )
        sample = " ".join(text.split())[:160]
        return {
            "pages": pages,
            "fonts": fonts,
            "images": images,
            "numbered_pages": len(numbers),
            "has_vazirmatn": any("vazir" in name.lower() for name in fonts),
            "has_naskh": any("naskh" in name.lower() for name in fonts),
            "presentation_forms": len(_PRESENTATION.findall(text)),
            "persian_chars": len(_PERSIAN_CHARS.findall(text)),
            "text_sample": sample,
            "metadata_title": (document.metadata or {}).get("title", ""),
        }


def audit_docx(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        document_xml = archive.read("word/document.xml").decode("utf-8")
        text = " ".join(
            re.findall(r"<w:t[^>]*>(.*?)</w:t>", document_xml, re.S)
        )
        return {
            "media": len([name for name in names if name.startswith("word/media/")]),
            "bidi": len(re.findall(r"<w:bidi\s*/>", document_xml)),
            "rtl": len(re.findall(r"<w:rtl\s*/>", document_xml)),
            "odttf": len([name for name in names if name.endswith(".odttf")]),
            "font_table": "word/fontTable.xml" in names,
            "toc_field": bool(
                re.search(r"<w:instrText[^>]*>\s*TOC", document_xml)
                or re.search(r'<w:fldSimple[^>]*w:instr="[^"]*TOC', document_xml)
            ),
            "page_field": bool(
                re.search(r"<w:instrText[^>]*>\s*PAGE", document_xml)
                or re.search(r'<w:fldSimple[^>]*w:instr="[^"]*PAGE', document_xml)
            ),
            "headings": len(re.findall(r'w:pStyle w:val="Heading', document_xml)),
            "persian_chars": len(_PERSIAN_CHARS.findall(text)),
            "latin_chars": len(_LATIN_CHARS.findall(text)),
        }


def audit_epub(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        chapters = [
            name for name in names
            if name.lower().endswith((".xhtml", ".html", ".htm"))
        ]
        nav_names = [
            name for name in names
            if name.lower().endswith(("nav.xhtml", "nav.html"))
        ]
        nav_items = 0
        for name in nav_names:
            try:
                nav_items += len(
                    re.findall(r"<li\b", archive.read(name).decode("utf-8"))
                )
            except Exception:
                pass
        spine = 0
        for name in names:
            if name.lower().endswith(".opf"):
                try:
                    root = ET.fromstring(archive.read(name))
                    spine = len(root.findall(".//{*}itemref"))
                except Exception:
                    pass
                break
        media = [
            name for name in names
            if name.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
            )
        ]
        return {
            "chapters": len(chapters),
            "nav_files": len(nav_names),
            "nav_items": nav_items,
            "spine": spine,
            "media": len(media),
        }


def audit_markdown(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "chars": len(text),
        "data_uri_images": text.count("data:image/"),
    }


def audit_text(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"chars": len(text), "lines": len(text.splitlines())}


def audit_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}
    if isinstance(data, dict):
        for key in ("segments", "items", "chunks"):
            if isinstance(data.get(key), list):
                return {"segments": len(data[key])}
        return {"keys": len(data)}
    return {"items": len(data) if isinstance(data, list) else 1}


def audit_srt(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "blocks": len(re.findall(r"^\d+\s*$", text, re.M)),
        "chars": len(text),
    }


def audit_file(source: str, fmt: str, path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        metrics = audit_pdf(path)
    elif suffix == ".docx":
        metrics = audit_docx(path)
    elif suffix == ".epub":
        metrics = audit_epub(path)
    elif suffix == ".md":
        metrics = audit_markdown(path)
    elif suffix == ".json":
        metrics = audit_json(path)
    elif suffix == ".srt":
        metrics = audit_srt(path)
    else:
        metrics = audit_text(path)
    return {
        "source": source,
        "format": fmt,
        "path": str(path),
        "size_kb": round(path.stat().st_size / 1024, 1),
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def findings(entries: list[dict]) -> list[str]:
    """Turn the measurements into sentences a human can act on."""
    notes: list[str] = []
    for entry in entries:
        if "error" in entry:
            notes.append(f"{entry['source']}/{entry['format']}: FAILED — {entry['error']}")
            continue
        metrics = entry["metrics"]
        name = f"{entry['source']}/{entry['format']}"
        if entry["format"] in {"translated_pdf", "mobile_pdf", "bilingual_pdf"}:
            if metrics.get("pages", 0) == 0:
                notes.append(f"{name}: no pages")
            if not metrics.get("has_vazirmatn"):
                notes.append(f"{name}: Vazirmatn is not embedded")
            if metrics.get("presentation_forms"):
                notes.append(
                    f"{name}: extracted text has "
                    f"{metrics['presentation_forms']} presentation-form characters"
                )
            if metrics.get("numbered_pages", 0) == 0:
                # A source-PDF overlay keeps the original page, so the
                # numbering is whatever the source had -- nothing to add.
                if not (
                    entry["source"] in {"pdf", "scanned"}
                    and entry["format"] == "translated_pdf"
                ):
                    notes.append(f"{name}: no page numbers detected")
            if entry["source"] == "epub" and entry["format"] in {
                "mobile_pdf", "bilingual_pdf",
            } and metrics.get("images", 0) == 0:
                notes.append(f"{name}: EPUB images were dropped")
        if entry["format"] == "docx":
            if metrics.get("persian_chars", 0) and not metrics.get("rtl"):
                notes.append(f"{name}: Persian text but no w:rtl runs")
            if not metrics.get("odttf"):
                notes.append(f"{name}: no embedded font (odttf)")
            if not metrics.get("toc_field"):
                notes.append(f"{name}: no TOC field")
        if entry["format"] == "translated_epub" and not metrics.get("nav_items"):
            notes.append(f"{name}: no nav/TOC entries")
    return notes


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _summary(fmt: str, metrics: dict) -> str:
    if fmt in {"translated_pdf", "mobile_pdf", "bilingual_pdf"}:
        fonts = ",".join(
            name.split("+")[-1] for name in metrics.get("fonts", [])
        ) or "-"
        return (
            f"pages={metrics.get('pages')} images={metrics.get('images')} "
            f"numbers={metrics.get('numbered_pages')} fonts={fonts}"
        )
    if fmt == "docx":
        return (
            f"media={metrics.get('media')} bidi={metrics.get('bidi')} "
            f"rtl={metrics.get('rtl')} odttf={metrics.get('odttf')} "
            f"toc={metrics.get('toc_field')}"
        )
    if fmt == "translated_epub":
        return (
            f"spine={metrics.get('spine')} nav={metrics.get('nav_items')} "
            f"media={metrics.get('media')}"
        )
    if fmt == "markdown":
        return f"chars={metrics.get('chars')} images={metrics.get('data_uri_images')}"
    if fmt == "srt":
        return f"blocks={metrics.get('blocks')}"
    if fmt == "json_segments":
        return f"segments={metrics.get('segments', metrics.get('items', '-'))}"
    return f"chars={metrics.get('chars')}"


def render_pdf_pages(path: Path, target_dir: Path, dpi: int, max_pages: int) -> list[str]:
    target_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    with fitz.open(path) as document:
        for index in range(min(len(document), max_pages)):
            pixmap = document[index].get_pixmap(dpi=dpi)
            target = target_dir / f"page-{index + 1:02d}.png"
            pixmap.save(target)
            rendered.append(str(target))
    return rendered


def write_report(out_dir: Path, entries: list[dict], notes: list[str], elapsed: float) -> Path:
    report = out_dir / "report.md"
    lines = [
        "# KALIMA output audit",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- PyMuPDF: {getattr(fitz, 'VersionBind', '')}",
        f"- Elapsed: {elapsed:.1f}s",
        "",
        "## Files",
        "",
        "| source | format | size KB | summary |",
        "| --- | --- | ---: | --- |",
    ]
    for entry in entries:
        if "error" in entry:
            lines.append(
                f"| {entry['source']} | {entry['format']} | - | ERROR: {entry['error']} |"
            )
            continue
        lines.append(
            f"| {entry['source']} | {entry['format']} | {entry['size_kb']} "
            f"| {_summary(entry['format'], entry['metrics'])} |"
        )
    lines += ["", "## Findings", ""]
    lines += [f"- {note}" for note in notes] or ["- none"]
    lines += ["", "## Details", ""]
    for entry in entries:
        if "error" in entry:
            continue
        lines += [
            f"### {entry['source']} / {entry['format']}",
            "",
            f"`{entry['path']}`",
            "",
            "```json",
            json.dumps(entry["metrics"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    lines += ["", "## Visual review", ""]
    pngs = [
        str(Path(entry["png_dir"]))
        for entry in entries
        if entry.get("png_dir")
    ]
    lines += [f"- `{png}`" for png in pngs] or ["- (PNG rendering disabled)"]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(
    out_dir: Path | str = REPO_ROOT / "output" / "audit",
    *,
    dpi: int = 100,
    render_png: bool = True,
    max_pages: int = 8,
) -> dict:
    """Build fixtures, run every writer, audit the results, write the report."""
    started = time.time()
    out_dir = Path(out_dir)
    fixtures = out_dir / "fixtures"
    files = out_dir / "files"
    png_root = out_dir / "png"
    fixtures.mkdir(parents=True, exist_ok=True)

    epub = make_epub(fixtures / "audit-book.epub")
    text_pdf = make_text_pdf(fixtures / "audit-text.pdf")
    scanned_pdf = make_scanned_pdf(fixtures / "audit-scanned.pdf")
    srt = make_srt(fixtures / "audit.srt")

    produced: list[tuple[str, str, Path]] = []
    errors: list[dict] = []
    for label, job in (
        ("epub", lambda: run_epub_job(epub, files / "epub")),
        ("pdf", lambda: run_pdf_job(text_pdf, files / "pdf", "pdf")),
        ("scanned", lambda: run_pdf_job(scanned_pdf, files / "scanned", "scanned")),
        ("srt", lambda: run_srt_job(srt, files / "srt")),
    ):
        try:
            produced.extend(job())
        except Exception as exc:  # keep auditing the other sources
            errors.append({"source": label, "format": "job", "error": repr(exc)})

    entries: list[dict] = []
    for source, fmt, path in produced:
        try:
            entry = audit_file(source, fmt, path)
            if render_png and path.suffix.lower() == ".pdf":
                png_dir = png_root / f"{source}-{fmt}"
                render_pdf_pages(path, png_dir, dpi, max_pages)
                entry["png_dir"] = str(png_dir)
            entries.append(entry)
        except Exception as exc:
            entries.append({
                "source": source,
                "format": fmt,
                "path": str(path),
                "error": repr(exc),
            })
    entries.extend(errors)

    notes = findings(entries)
    report = write_report(out_dir, entries, notes, time.time() - started)
    return {
        "report": str(report),
        "entries": entries,
        "findings": notes,
        "elapsed": round(time.time() - started, 1),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "output" / "audit"),
        help="directory for fixtures, outputs, PNGs and report.md",
    )
    parser.add_argument("--dpi", type=int, default=100, help="PNG render DPI")
    parser.add_argument("--no-png", action="store_true", help="skip PNG rendering")
    parser.add_argument(
        "--max-pages", type=int, default=8,
        help="render at most this many pages per PDF",
    )
    args = parser.parse_args(argv)

    result = run(
        args.out,
        dpi=args.dpi,
        render_png=not args.no_png,
        max_pages=args.max_pages,
    )
    print(f"report: {result['report']}")
    print(f"files : {len([e for e in result['entries'] if 'error' not in e])}")
    print(f"time  : {result['elapsed']}s")
    print()
    print("findings:")
    for note in result["findings"]:
        print(f"  - {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
