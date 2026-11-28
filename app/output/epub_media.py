# ============================================================
# app/output/epub_media.py
# ============================================================
"""
Images from an EPUB, keyed by the chapter that references them.

The segment model is plain text: ``build_segments`` flattens every
chunk, so a writer that works from segments cannot see a picture.
That is why the EPUB-rendered outputs go through pandoc -- and why
``mobile_pdf`` and ``bilingual_pdf``, which are built from
segments, used to drop every illustration.

This module gives those writers the pictures back: for each XHTML
chapter it returns the images that chapter references, already
encoded as ``data:`` URIs so the HTML is self-contained (the
renderer aborts every network request, so a relative path would
simply not load).
"""

from __future__ import annotations

import base64
import mimetypes
import posixpath
import re
import zipfile
from pathlib import Path

_CHAPTER_SUFFIXES = (".xhtml", ".html", ".htm")

#: ``<img src=...>`` and the SVG ``<image href=...>`` form. Attribute
#: order varies in the wild, so the two attributes are matched
#: independently rather than as one fixed pattern.
_IMG_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
_SVG_IMAGE_RE = re.compile(
    r"<image\b[^>]*?\b(?:xlink:)?href\s*=\s*[\"']([^\"']+)[\"']", re.I
)


def _data_uri(blob, name):
    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    encoded = base64.b64encode(blob).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def chapter_images(epub_path) -> dict[str, list[str]]:
    """Map each chapter's *href* to its images as data URIs.

    Keys are the hrefs the EPUB's OPF uses (``OPS/chapter1.xhtml``),
    because that is what ``chapter_map`` stores as a segment's
    ``chapter``. Lookup is tolerant: a caller that holds only the
    file name gets the match too, since the writer falls back to
    comparing basenames.
    """

    epub_path = Path(epub_path)
    result: dict[str, list[str]] = {}
    if not epub_path.is_file():
        return result

    try:
        archive = zipfile.ZipFile(epub_path)
    except (OSError, zipfile.BadZipFile):
        return result

    with archive:
        names = set(archive.namelist())
        for name in sorted(names):
            if not name.lower().endswith(_CHAPTER_SUFFIXES):
                continue
            try:
                content = archive.read(name).decode("utf-8", "replace")
            except (KeyError, OSError):
                continue
            sources = _IMG_RE.findall(content) + _SVG_IMAGE_RE.findall(content)
            if not sources:
                continue
            images = []
            base = posixpath.dirname(name)
            for source in sources:
                if source.startswith(("data:", "http:", "https:", "//", "#")):
                    continue
                target = posixpath.normpath(posixpath.join(base, source))
                if target not in names:
                    continue
                try:
                    images.append(_data_uri(archive.read(target), target))
                except (KeyError, OSError):
                    continue
            if images:
                result[name] = images

    return result


def images_for(images, chapter):
    """Images for one segment's ``chapter`` value.

    Exact href first, then a basename match -- ``chapter_map`` from
    older job state sometimes stores just ``chapter1.xhtml``.
    """

    if not images or not chapter:
        return []
    chapter = str(chapter).replace("\\", "/")
    if chapter in images:
        return images[chapter]
    wanted = posixpath.basename(chapter)
    for name, sources in images.items():
        if posixpath.basename(name) == wanted:
            return sources
    return []
