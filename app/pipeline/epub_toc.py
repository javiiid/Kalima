"""Regenerate a translated EPUB's Table of Contents (nav.xhtml) and internal
links so the navigable structure matches the translated chapters instead of
the stale source structure.

`EPUBHandler.save_translated_epub` swaps translated chapter bodies in place
but copies every non-chapter file (``content.opf``, ``nav.xhtml``, images,
CSS...) byte-for-byte. The reassembled EPUB is therefore valid but its TOC
still lists the source-book titles/hrefs and internal chapter links may point
at stale targets. This module rebuilds the navigation as the last step of EPUB
reassembly.

Public function
---------------
rebuild_epub_structure(input_epub_path, output_epub_path)
    Reads ``input_epub_path`` fully into memory, rebuilds ``nav.xhtml``,
    rewrites internal chapter links, refreshes ``content.opf`` (manifest +
    spine) and writes a valid EPUB to ``output_epub_path``. Supports
    in-place rebuild (input == output) via an atomic temp-file replace.
"""

from __future__ import annotations

import os
import posixpath
import re
import zipfile
from html import escape, unescape
from xml.etree import ElementTree

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
XHTML_NS = "http://www.w3.org/1999/xhtml"
OPS_NS = "http://www.idpf.org/2007/ops"


def _ns(tag: str) -> str:
    return f"{{{OPF_NS}}}{tag}"


# Match the first heading of a chapter; capture level and inner HTML.
_HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.I | re.S)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# Match an opening <a ...> tag and, separately, an href= attribute.
_A_OPEN_RE = re.compile(r"<a\b([^>]*)>", re.I | re.S)
_HREF_RE = re.compile(r"\bhref\s*=\s*(['\"])(.*?)\1", re.I)

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)


def _chapter_title(content: str, fallback: str) -> str:
    """Return a human title for a chapter body."""
    match = _HEADING_RE.search(content)
    if match:
        text = re.sub(_TAG_RE, "", match.group(2))
        text = unescape(text).strip()
        if text:
            return text
    match = _TITLE_RE.search(content)
    if match:
        text = re.sub(_TAG_RE, "", match.group(1))
        text = unescape(text).strip()
        if text:
            return text
    return fallback


def _resolve_href(href: str, base_path: str) -> str | None:
    """Resolve an EPUB-relative href against a chapter path.

    Returns the normalized archive-relative target path, or ``None`` when the
    reference is a fragment, an absolute/scheme URL, an asset, or escapes the
    archive root.
    """
    href = (href or "").strip()
    if not href or href.startswith("#"):
        return None
    if _SCHEME_RE.match(href):
        return None
    href = href.replace("\\", "/")
    if "#" in href:
        href = href.split("#", 1)[0]
    if not href:
        return None
    while href.startswith("./"):
        href = href[2:]
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(base_path), href))
    if joined.startswith(("/", "..")) or joined.split("/")[0] in {"..", ""}:
        return None
    return joined


def _relpath(from_path: str, to_path: str) -> str:
    """Relative path from ``from_path`` to ``to_path`` (both archive-relative)."""
    return posixpath.relpath(to_path, posixpath.dirname(from_path))


def _rewrite_chapter_links(html: str, chapter_path: str, chapter_paths: set[str]) -> str:
    """Rewrite internal ``<a href>`` targets inside one chapter.

    Only targets that resolve to another spine chapter are rewritten, to the
    relative path from this chapter to that chapter. Fragments are preserved.
    Everything else (external URLs, assets, images) is left untouched.
    """

    def replace_href(match: re.Match[str]) -> str:
        quote = match.group(1)
        href = match.group(2)
        target = _resolve_href(href, chapter_path)
        if target is None or target not in chapter_paths:
            return match.group(0)
        new_href = _relpath(chapter_path, target)
        if "#" in href:
            new_href = new_href + "#" + href.split("#", 1)[1]
        return f'href={quote}{new_href}{quote}'

    return _A_OPEN_RE.sub(
        lambda m: f"<a{_HREF_RE.sub(replace_href, m.group(1))}>", html
    )


def _build_nav_xhtml(chapters: list[dict], nav_path: str) -> str:
    """EPUB 3 nav document with an ``epub:type="toc"`` ordered list."""
    items = []
    for chapter in chapters:
        href = _relpath(nav_path, chapter["path"])
        items.append(
            f'    <li><a href="{escape(href, quote=True)}">'
            f"{escape(chapter['title'], quote=True)}</a></li>"
        )
    return (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<!DOCTYPE html>\n'
        f'<html xmlns="{XHTML_NS}" xmlns:epub="{OPS_NS}">\n'
        f'<head><title>Contents</title></head>\n'
        f'<body>\n'
        f'<nav epub:type="toc" id="toc">\n'
        f'<ol>\n'
        f"{chr(10).join(items)}\n"
        f'</ol>\n'
        f'</nav>\n'
        f'</body>\n'
        f'</html>\n'
    )


def _abs_href(href: str, opf_base: str) -> str:
    """Archive-absolute path for a manifest href resolved against opf base."""
    return posixpath.normpath(posixpath.join(opf_base, (href or "").replace("\\", "/")))


def _manifest_item_string(item: ElementTree.Element) -> str:
    """Serialize one preserved manifest item as a clean, namespaced-free tag."""
    parts = [
        f'id="{escape(item.attrib.get("id", "") or "", quote=True)}"',
        f'href="{escape(item.attrib.get("href", "") or "", quote=True)}"',
    ]
    media_type = item.attrib.get("media-type")
    if media_type:
        parts.append(f'media-type="{escape(media_type, quote=True)}"')
    properties = item.attrib.get("properties")
    if properties:
        parts.append(f'properties="{escape(properties, quote=True)}"')
    return "<item " + " ".join(parts) + "/>"


def _block(text: str, tag: str, inner: str) -> str:
    """Replace the <tag>...</tag> block (with optional namespace prefix)."""
    pattern = re.compile(
        rf"<(?:\w+:)?{tag}\b[^>]*>.*?</(?:\w+:)?{tag}>", re.I | re.S
    )
    return pattern.sub(f"<{tag}>\n{inner}\n</{tag}>", text, count=1)


def _build_opf(
    opf_text: str,
    chapters: list[dict],
    nav_rel: str,
    opf_base: str,
    chapter_abs_paths: set[str],
    nav_abs: str,
) -> str:
    """Rebuild content.opf: keep metadata byte-for-byte, refresh manifest +
    spine. ``chapter_abs_paths`` and ``nav_abs`` identify old manifest items
    that must not be re-emitted (avoiding duplicates)."""
    reserved = set(chapter_abs_paths)
    reserved.add(nav_abs)

    manifest_lines = [
        f'<item id="nav" href="{escape(nav_rel, quote=True)}" '
        f'media-type="application/xhtml+xml" properties="nav"/>'
    ]
    for chapter in chapters:
        href = _relpath(opf_base, chapter["path"]).replace("\\", "/")
        manifest_lines.append(
            f'<item id="{chapter["id"]}" href="{escape(href, quote=True)}" '
            f'media-type="application/xhtml+xml"/>'
        )

    # Keep every pre-existing non-chapter / non-nav manifest item
    # (images, CSS, fonts...), resolved so duplicates are not emitted.
    try:
        original_root = ElementTree.fromstring(opf_text.encode("utf-8"))
    except ElementTree.ParseError:
        original_root = None
    if original_root is not None:
        manifest = original_root.find(_ns("manifest"))
        if manifest is not None:
            for item in manifest:
                if not item.tag.endswith("item"):
                    continue
                if _abs_href(item.attrib.get("href", ""), opf_base) in reserved:
                    continue
                manifest_lines.append(_manifest_item_string(item))

    spine_lines = [f'<itemref idref="{chapter["id"]}"/>' for chapter in chapters]

    manifest_block = "    " + "\n    ".join(manifest_lines)
    spine_block = "    " + "\n    ".join(spine_lines)

    text = _block(opf_text, "manifest", manifest_block)
    text = _block(text, "spine", spine_block)
    return text


def rebuild_epub_structure(input_epub_path: str, output_epub_path: str) -> None:
    """Rebuild the EPUB navigation and internal links.

    Reads ``input_epub_path``, regenerates ``nav.xhtml`` from actual chapter
    headings, rewrites internal chapter-to-chapter links, refreshes
    ``content.opf`` (manifest + spine) and writes a valid EPUB to
    ``output_epub_path``. When both paths are identical the replacement is
    atomic (temp file + ``os.replace``).
    """
    in_place = os.path.abspath(input_epub_path) == os.path.abspath(output_epub_path)
    target_path = output_epub_path if not in_place else output_epub_path + ".rebuild-tmp"

    with zipfile.ZipFile(input_epub_path) as src:
        names = set(src.namelist())
        infos = {info.filename: info for info in src.infolist()}
        entries = {name: src.read(name) for name in src.namelist()}

    # Locate content.opf via META-INF/container.xml.
    try:
        container = ElementTree.fromstring(entries["META-INF/container.xml"])
    except (KeyError, ElementTree.ParseError):
        # Not a navigable EPUB; nothing to rebuild.
        return
    rootfile_nodes = [
        node.attrib["full-path"]
        for node in container.iter()
        if node.tag.endswith("rootfile") and node.attrib.get("full-path")
    ]
    if not rootfile_nodes:
        return
    opf_path = rootfile_nodes[0]
    opf_base = posixpath.dirname(opf_path)
    opf_text = entries[opf_path].decode("utf-8", errors="replace")

    try:
        original_root = ElementTree.fromstring(opf_text.encode("utf-8"))
    except (KeyError, ElementTree.ParseError):
        return

    # Ordered chapter paths from the spine (hrefs resolved against opf base).
    id_to_href = {}
    manifest_node = original_root.find(_ns("manifest"))
    if manifest_node is not None:
        for item in manifest_node:
            if item.tag.endswith("item") and item.attrib.get("id"):
                id_to_href[item.attrib["id"]] = item.attrib.get("href", "")

    chapter_paths = []
    spine_node = original_root.find(_ns("spine"))
    if spine_node is not None:
        for itemref in spine_node:
            if not itemref.tag.endswith("itemref"):
                continue
            href = id_to_href.get(itemref.attrib.get("idref", ""))
            if not href:
                continue
            path = posixpath.normpath(
                posixpath.join(opf_base, href.replace("\\", "/"))
            )
            if path in names:
                chapter_paths.append(path)

    if not chapter_paths:
        return

    chapter_set = set(chapter_paths)
    chapters: list[dict] = []

    # Translate chapter bodies + rewrite their internal links.
    for index, path in enumerate(chapter_paths):
        content = entries[path].decode("utf-8", errors="replace")
        title = _chapter_title(content, f"Chapter {index + 1}")
        content = _rewrite_chapter_links(content, path, chapter_set)
        entries[path] = content.encode("utf-8")
        chapters.append(
            {"index": index, "path": path, "id": f"ch-{index}", "title": title}
        )

    # Regenerate nav.xhtml.
    # The manifest href may be stale (pointing at a removed/renamed nav file),
    # so locate the real nav document in the archive and fall back to a
    # conventional location next to content.opf.
    nav_rel = None
    if manifest_node is not None:
        for item in manifest_node:
            if (
                item.tag.endswith("item")
                and "nav" in (item.attrib.get("properties") or "")
            ):
                nav_rel = item.attrib.get("href")
                break
    nav_abs = None
    if nav_rel:
        candidate = posixpath.normpath(
            posixpath.join(opf_base, nav_rel.replace("\\", "/"))
        )
        if candidate in names:
            nav_abs = candidate
    if nav_abs is None:
        default = (
            posixpath.join(opf_base, "nav.xhtml") if opf_base else "nav.xhtml"
        )
        if default in names:
            nav_abs = default
        else:
            for name in names:
                if name.lower().endswith(("nav.xhtml", "nav.html")):
                    nav_abs = name
                    break
    if nav_abs is None:
        nav_abs = posixpath.join(opf_base, "nav.xhtml") if opf_base else "nav.xhtml"
    nav_rel = (
        posixpath.relpath(nav_abs, opf_base) if opf_base else nav_abs
    ).replace("\\", "/")
    entries[nav_abs] = _build_nav_xhtml(chapters, nav_abs).encode("utf-8")

    # Regenerate content.opf (metadata preserved; manifest + spine rebuilt).
    entries[opf_path] = _build_opf(
        opf_text, chapters, nav_rel, opf_base, set(chapter_paths), nav_abs
    ).encode("utf-8")

    # Write the output EPUB (mimetype first + stored; everything else deflated).
    try:
        with zipfile.ZipFile(target_path, "w") as dst:
            if "mimetype" in entries:
                dst.writestr(
                    zipfile.ZipInfo("mimetype"),
                    entries["mimetype"],
                    compress_type=zipfile.ZIP_STORED,
                )
            for name, blob in entries.items():
                if name == "mimetype":
                    continue
                info = infos.get(name)
                zip_info = zipfile.ZipInfo(name)
                if info is not None:
                    zip_info.date_time = info.date_time
                    zip_info.compress_type = info.compress_type
                else:
                    zip_info.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(zip_info, blob)

        if in_place:
            os.replace(target_path, output_epub_path)
    except Exception:
        # Never leave a half-written sidecar next to the real book. The
        # original output is untouched until ``os.replace`` succeeds.
        if in_place:
            try:
                os.remove(target_path)
            except OSError:
                pass
        raise
