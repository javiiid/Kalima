from app.pipeline.epub_handler import EPUBHandler
from app.pipeline.epub_toc import rebuild_epub_structure


def reassemble_translation(
    input_epub_path,
    output_epub_path,
    chapter_map,
    translations,
    rebuild_structure=True,
):
    """
    Reassemble translated chunks into a new EPUB.

    Parameters
    ----------
    input_epub_path : str or Path
        مسیر EPUB اصلی

    output_epub_path : str or Path
        مسیر EPUB خروجی

    chapter_map : dict
        نقشه محل قرارگیری Chunkها

    translations : dict
        ترجمه Chunkها

    rebuild_structure : bool
        When true (default), regenerate ``nav.xhtml`` (Table of Contents),
        rewrite internal chapter links and refresh ``content.opf`` (manifest +
        spine) on the output EPUB so the navigable structure matches the
        translated chapters. Failures here are printed as warnings and never
        fail the job.
    """

    EPUBHandler.save_translated_epub(
        input_epub_path=input_epub_path,
        output_epub_path=output_epub_path,
        translations=translations,
        chapter_map=chapter_map
    )

    if rebuild_structure:
        try:
            rebuild_epub_structure(output_epub_path, output_epub_path)
            print(
                f"Rebuilt EPUB navigation and internal links at "
                f"{output_epub_path} [reassemble_translation]"
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(
                f"Warning: EPUB navigation rebuild skipped ({exc}); "
                f"output kept as-is [reassemble_translation]"
            )

    print(
        f"Processed translation output saved to "
        f"{output_epub_path} [reassemble_translation]"
    )
