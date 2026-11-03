"""Prepare immutable translation units; never silently skip source content."""
from __future__ import annotations

import hashlib
import html
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from app.pipeline.epub_toc import rebuild_epub_structure
from app.pipeline.semantic_chunker import SemanticChunker, strip_tags
from app.reader.service import _spine_items, _title

# ============================================================
# Tesseract discovery for OCR of scanned pages
# ============================================================
#
# PyMuPDF's OCR path needs Tesseract and its tessdata on PATH/TESSDATA_PREFIX.
# The service used to inherit whatever the launching shell happened to export,
# so a correct install could still fail with "Tesseract is not installed"
# depending on how the server was started (a Windows service, a container, an
# IDE run button). Resolve both here instead, once, and fall back to the
# environment when nothing is found.

_TESSERACT_EXE = None
_TESSDATA_DIR = None


def _candidate_tesseract_paths():
    import os
    import shutil

    found = shutil.which("tesseract")
    if found:
        yield Path(found)
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("USERPROFILE"),
        "/usr/bin",
        "/usr/local/bin",
        "/opt/homebrew/bin",
    ]
    for root in roots:
        if not root:
            continue
        for name in ("Tesseract-OCR/tesseract.exe", "Tesseract-OCR/bin/tesseract",
                     "Programs/Tesseract-OCR/tesseract.exe", "scoop/shims/tesseract.exe"):
            yield Path(root) / name
        yield Path(root) / "tesseract"


def tesseract_path():
    """Absolute path to the tesseract binary, or None when not installed."""
    global _TESSERACT_EXE
    if _TESSERACT_EXE is not None:
        return _TESSERACT_EXE or None
    for candidate in _candidate_tesseract_paths():
        if candidate.is_file():
            _TESSERACT_EXE = candidate
            return candidate
    _TESSERACT_EXE = ""
    return None


def tessdata_path():
    """The best tessdata directory, or None to let Tesseract decide.

    A machine can have more than one: the installer's own ``tessdata`` next to
    the binary, plus a per-user directory where extra language packs were
    dropped without administrator rights. Picking the first one found silently
    hid the extra languages, so the richest directory wins -- the one with the
    most ``*.traineddata`` files -- with a preference for anything containing
    ``eng`` so we never choose a directory that breaks English OCR.
    """
    global _TESSDATA_DIR
    if _TESSDATA_DIR is not None:
        return _TESSDATA_DIR or None
    import os

    candidates = []
    env = os.environ.get("TESSDATA_PREFIX")
    if env and Path(env).is_dir():
        candidates.append(Path(env))
    exe = tesseract_path()
    if exe:
        candidates += [exe.parent / "tessdata", exe.parent.parent / "share" / "tessdata"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Tesseract-OCR" / "tessdata")

    existing = [c for c in candidates if c.is_dir()]
    if not existing:
        _TESSDATA_DIR = ""
        return None

    def rank(directory):
        langs = {p.stem for p in directory.glob("*.traineddata")}
        return (1 if "eng" in langs else 0, len(langs))

    best = max(existing, key=rank)
    _TESSDATA_DIR = best
    return best


def configure_tesseract_env():
    """Make the resolved Tesseract visible to PyMuPDF before an OCR call.

    Returns True when Tesseract is available. PyMuPDF shells out to the binary
    and reads TESSDATA_PREFIX from the process environment, so both have to be
    set here rather than assumed.
    """
    import os

    exe = tesseract_path()
    if exe is None:
        return False
    os.environ["PATH"] = str(exe.parent) + os.pathsep + os.environ.get("PATH", "")
    data = tessdata_path()
    if data is not None:
        os.environ["TESSDATA_PREFIX"] = str(data)
    return True


def available_ocr_languages():
    """Installed Tesseract language codes, lowercased. Empty when unavailable."""
    import subprocess

    exe = tesseract_path()
    if exe is None:
        return set()
    try:
        result = subprocess.run(
            [str(exe), "--list-langs"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    languages = set()
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line and " " not in line and not line.lower().startswith("list of"):
            languages.add(line.lower())
    return languages



def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_epub(path, chapters, title):
    """Build a reflowable source EPUB for PDF/TXT, retaining chapter/page labels."""
    items, refs = [], []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as book:
        book.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        book.writestr("META-INF/container.xml", '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        for i, (label, content) in enumerate(chapters):
            name = f"chapter-{i}.xhtml"
            book.writestr(f"OEBPS/{name}", '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>' + html.escape(label) + '</title></head><body>' + content + '</body></html>')
            items.append(f'<item id="ch{i}" href="{name}" media-type="application/xhtml+xml"/>')
            refs.append(f'<itemref idref="ch{i}"/>')
        nav = ''.join(f'<li><a href="chapter-{i}.xhtml">{html.escape(label)}</a></li>' for i, (label, _) in enumerate(chapters))
        book.writestr("OEBPS/nav.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><ol>' + nav + '</ol></nav></body></html>')
        book.writestr("OEBPS/content.opf", '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:sha256:' + digest(chapters) + '</dc:identifier><dc:title>' + html.escape(title) + '</dc:title><dc:language>und</dc:language><meta property="dcterms:modified">2026-10-01T00:00:00Z</meta></metadata><manifest>' + ''.join(items) + '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine>' + ''.join(refs) + '</spine></package>')


def prepare(source: Path, directory: Path, source_language="EN"):
    directory.mkdir(parents=True, exist_ok=True)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    warnings = []
    suffix = source.suffix.lower()
    prepared = directory / "source.epub"
    if suffix == ".epub":
        with zipfile.ZipFile(source) as archive:
            if sum(i.file_size for i in archive.infolist()) > 300 * 1024 * 1024:
                raise ValueError("حجم محتوای بازشدهٔ کتاب بیش از حد مجاز است.")
            paths = _spine_items(archive)
            if not paths:
                raise ValueError("کتاب فصل قابل‌خواندن ندارد.")
            # Normalize declared non-UTF8 XML encodings explicitly, never skip a chapter.
            with zipfile.ZipFile(prepared, "w", zipfile.ZIP_DEFLATED) as output:
                for entry in archive.infolist():
                    data = archive.read(entry)
                    if entry.filename in paths:
                        match = re.search(br'encoding=["\']([^"\']+)', data[:250])
                        encoding = match.group(1).decode("ascii") if match else "utf-8-sig"
                        text = data.decode(encoding)
                        text = re.sub(r'(encoding=["\'])[^"\']+', r'\1utf-8', text, count=1)
                        data = text.encode("utf-8")
                    output.writestr(entry, data)
    elif suffix == ".txt":
        raw = source.read_bytes()
        encoding = "utf-16" if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig"
        try:
            text = raw.decode(encoding)
        except UnicodeError as exc:
            raise ValueError("فایل متنی باید UTF-8 یا UTF-16 باشد؛ ابتدا رمزگذاری را اصلاح کنید.") from exc
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        # Group into small chapters so manual selection remains practical.
        chapters = [(f"بخش {i // 40 + 1}", ''.join('<p>' + html.escape(p).replace('\n', '<br/>') + '</p>' for p in paragraphs[i:i + 40])) for i in range(0, len(paragraphs), 40)]
        make_epub(prepared, chapters, source.stem)
    elif suffix == ".pdf":
        import fitz
        chapters = []
        with fitz.open(source) as pdf:
            if pdf.needs_pass:
                raise ValueError("ابتدا رمز فایل PDF را بردارید.")
            if len(pdf) > 3000:
                raise ValueError("حداکثر ۳۰۰۰ صفحه در هر کتاب پشتیبانی می‌شود.")
            # Resolve Tesseract before the first OCR call. Relying on the
            # launching shell's PATH made a correct install fail whenever the
            # server was started as a service, a container, or an IDE run.
            ocr_ready = configure_tesseract_env()
            installed_langs = available_ocr_languages() if ocr_ready else set()

            for i, page in enumerate(pdf):
                text = page.get_text("text", sort=True)
                if len(text.strip()) < 25 and page.get_images():
                    lang = {"EN": "eng", "FA": "fas", "DE": "deu", "FR": "fra", "AR": "ara"}.get(source_language, "eng")
                    if ocr_ready and installed_langs and lang not in installed_langs:
                        # The requested pack is missing. Use an installed one and
                        # say so, instead of failing the whole book.
                        fallback = "eng" if "eng" in installed_langs else sorted(installed_langs)[0]
                        warnings.append(f"زبان OCR «{lang}» نصب نیست؛ با «{fallback}» خوانده می‌شود.")
                        lang = fallback
                    try:
                        text = page.get_text("text", textpage=page.get_textpage_ocr(language=lang), sort=True)
                        warnings.append(f"صفحهٔ {i + 1} با OCR خوانده شد؛ متن نمونه را بررسی کنید.")
                    except Exception as exc:
                        detail = ("Tesseract پیدا نشد" if not ocr_ready
                                  else "بستهٔ زبان «" + lang + "» پیدا نشد" if installed_langs and lang not in installed_langs
                                  else "OCR با خطا مواجه شد")
                        raise ValueError(f"صفحهٔ {i + 1} اسکن‌شده است و {detail}. Tesseract و بستهٔ زبان را نصب کنید یا نسخهٔ متنی کتاب را وارد کنید.") from exc
                if text.strip():
                    content = ''.join('<p>' + html.escape(p).replace('\n', '<br/>') + '</p>' for p in re.split(r"\n\s*\n", text) if p.strip())
                    chapters.append((f"صفحهٔ {i + 1}", content))

        warnings.append("خروجی PDF بازچینی می‌شود؛ ترتیب متن، جدول‌ها و پانویس‌ها را در نمونه بررسی کنید.")
        make_epub(prepared, chapters, source.stem)
    else:
        raise ValueError("فقط EPUB، PDF و TXT پشتیبانی می‌شود.")

    units = []
    with zipfile.ZipFile(prepared) as archive:
        for chapter_no, name in enumerate(_spine_items(archive)):
            content = archive.read(name).decode("utf-8-sig")
            title = _title(content, f"فصل {chapter_no + 1}")
            for pos, chunk in enumerate(SemanticChunker(max_tokens=550, context_window=1).chunk(content)):
                plain = strip_tags(chunk.html).strip()
                units.append({"id": f"chunk-{len(units)}", "source": chunk.html, "plain": plain,
                              "context": chunk.context_before, "chapter": title, "item": name, "pos": pos,
                              "role": classify(plain), "hash": digest([chunk.html, chunk.context_before])})
    if not any(u["plain"] for u in units):
        raise ValueError("متن قابل‌ترجمه‌ای پیدا نشد.")
    if len(units) > 30000:
        raise ValueError("کتاب بیش از حد بزرگ است؛ آن را به چند جلد تقسیم کنید.")
    selected = sample_units(units)
    return {"source_hash": original_hash, "prepared_hash": hashlib.sha256(prepared.read_bytes()).hexdigest(),
            "prepared_path": str(prepared), "units": units, "selected": selected,
            "warnings": warnings[:30], "parser_version": 1}


def classify(text):
    if len(re.findall(r'[“”«»]|(?:^|\n)[—–]|\b(?:said|asked|replied)\b', text, re.I)) >= 2:
        return "dialogue"
    if len(re.findall(r'\b[A-Z]{2,}\b|\d|\b(?:algorithm|theorem|equation|parameter|therefore|hypothesis)\b', text, re.I)) >= 5:
        return "technical"
    return "narrative"


def sample_units(units, count=3):
    candidates = [u for u in units if len(u["plain"]) >= 80] or [u for u in units if u["plain"]]
    selected = []
    for role in ("narrative", "technical", "dialogue")[:count]:
        pool = [u for u in candidates if u["id"] not in selected]
        if not pool:
            break
        chosen = max(pool, key=lambda u: (int(u["role"] == role) * 3
                     + int(u["item"] not in {x["item"] for x in units if x["id"] in selected}) * 2
                     + min((abs(int(u["id"].split('-')[1]) - int(s.split('-')[1])) / max(1, len(units)) for s in selected), default=0)))
        selected.append(chosen["id"])
    return selected


def write_translation(document, translations, output_path, target_language):
    chapters = {}
    for unit in document["units"]:
        if unit["id"] not in translations:
            raise ValueError("خروجی ناقص است؛ همهٔ بخش‌ها باید ترجمه شوند.")
        chapters.setdefault(unit["item"], []).append(translations[unit["id"]])
    temporary = Path(output_path).with_suffix(".partial.epub")
    with zipfile.ZipFile(document["prepared_path"]) as source, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for entry in source.infolist():
            data = ''.join(chapters[entry.filename]).encode("utf-8") if entry.filename in chapters else source.read(entry)
            if entry.filename.lower().endswith('.opf'):
                try:
                    root = ElementTree.fromstring(data)
                    for node in root.iter():
                        if node.tag == '{http://purl.org/dc/elements/1.1/}language':
                            node.text = target_language.lower()
                    data = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
                except ElementTree.ParseError:
                    pass
            target.writestr(entry, data)
    temporary.replace(output_path)

    # Rebuild navigation (TOC), internal chapter links, and spine so the
    # translated EPUB matches the actual chapter contents instead of the
    # source structure. Calibration must not fail because of this step.
    try:
        rebuild_epub_structure(output_path, output_path)
    except Exception:
        pass
