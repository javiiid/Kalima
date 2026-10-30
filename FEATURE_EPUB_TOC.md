FEATURE: Auto-regenerate EPUB Table of Contents (TOC) and internal links
=======================================================================

Goal
----
After a translated EPUB is reassembled, automatically rebuild its
navigable structure so the Table of Contents (`nav.xhtml`) and every
internal cross-chapter link (`<a href="...">`) point at the actual
translated chapters instead of the stale source structure.

Why
---
`EPUBHandler.save_translated_epub` copies every non-chapter file
(container.xml, content.opf, nav.xhtml, images, CSS...) byte-for-byte
and only swaps translated chapter bodies in place. Consequences:

1. `nav.xhtml` still lists the source-book chapter titles/hrefs. If
   translation reorders, renames, or drops headings, the TOC lies.
2. Internal links inside translated chapters still point at the
   original chapter file names. Those names are preserved, so most links
   survive, but any link that referenced a heading/fragment or a renamed
   chapter breaks silently.
3. `content.opf` keeps the original manifest/spine, which is usually
   consistent but is never re-validated against the final chapter set.

Scope
-----
* EPUB outputs only (the reassembly step is EPUB-specific).
* Runs automatically as the last step of `reassemble_translation`, so
    every translated EPUB gets a fresh TOC + fixed links with zero
    user action. Pass `rebuild_structure=False` to opt out.
* Calibration EPUB output (`app/calibration/documents.py:write_translation`)
    runs the same rebuild after saving. Failure there is swallowed silently.
* Non-fatal: if the rebuild raises, the job still completes with the
    output produced by `save_translated_epub` (valid, just stale
    structure) and a warning is printed. In-place rebuilds write to a
    `.rebuild-tmp` sidecar and only replace the real file on success, so
    a failed rebuild never truncates the saved output; a failed sidecar
    write is cleaned up.

Behavior
--------
0. If `META-INF/container.xml` or the rootfile OPF cannot be read, the
   function returns without writing anything (non-navigable EPUBs are
   left alone).
1. Read the reassembled output EPUB into memory.
2. Locate `META-INF/container.xml` → rootfile (`content.opf`).
3. Walk `<spine>` itemrefs in order → ordered chapter paths (relative to
   `content.opf`). Skip anything missing from the archive.
4. For each chapter:
   a. Extract a display title: first `<h1>`-`<h6>` text, else `<title>`,
      else `Chapter N`.
   b. Rewrite every internal `<a href>` whose target resolves (relative
      to the chapter) to another spine chapter, so the href becomes the
      relative path to that chapter. Fragments on a rewritten target are
      preserved. External URLs, `data:`, fragment-only links, and asset
      links are left untouched.
5. Regenerate `nav.xhtml`. The nav file is located in this order: the
   manifest item with `properties="nav"` (if it exists in the archive),
   else `nav.xhtml` next to the OPF, else any archive entry ending in
   `nav.xhtml`/`nav.html`; if none exists, a new `nav.xhtml` is written
   next to the OPF:
   `<html ...><body><nav epub:type="toc"><ol><li><a href="..">Title</a></li>...</ol></nav></body></html>`
6. Regenerate `content.opf`:
   * Preserve all original `<metadata>` children verbatim.
   * Rebuild `<manifest>`: nav item (`properties="nav"`, id `nav`) + one
     item per chapter (ids `ch-0`, `ch-1`, ...) + all pre-existing
     non-chapter items (images, CSS, fonts, extra XHTML) that are not
     already covered as a chapter or the nav.
   * Rebuild `<spine>`: one `<itemref idref="ch-N">` per chapter in spine
     order.
7. Write a valid EPUB: `mimetype` first and stored; entries that already
   existed keep their original compression method and timestamp, new
   entries use deflate.

Interface
---------
app.pipeline.epub_toc.rebuild_epub_structure(input_epub_path, output_epub_path)
    Reads input, writes a structurally-rebuilt EPUB to output. Supports
    in-place rebuild (input == output) via an atomic temp-file replace.

Wiring
------
app.pipeline.epub_pipeline.reassemble_translation gains an optional
`rebuild_structure=True` keyword. After saving translated chapters it
calls `rebuild_epub_structure(output, output)` (in-place). Existing
4-argument callers are unchanged.

Acceptance (informal)
---------------------
* Translated EPUB opens in readers and `nav.xhtml` lists translated
  chapter titles.
* Clicking a TOC entry opens the correct chapter.
* Internal chapter-to-chapter links resolve.
* `mimetype` remains first + stored; archive remains a valid EPUB.
* Job still completes if rebuild raises (warning printed, output
  untouched).

Tests
-----
* `tests/test_epub_toc.py` — unit coverage of the rebuild (nav, links,
  metadata, in-place atomicity, malformed input).
* `tests/test_e2e_epub_toc.py` — real `reassemble_translation` path with
  fabricated translations: regenerated TOC, resolvable chapter links,
  rebuilt spine, and a rebuild failure that leaves a usable output.
