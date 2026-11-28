# ============================================================
# app/output/rtl_pdf.py
# ============================================================
"""
Compatibility shim for the old RTL-PDF entry point.

The renderer moved to :mod:`app.output.html_pdf` when the project
settled on one PDF engine for every output. This module keeps the
``write_html_pdf`` name alive for the callers that still import it
(``app/output/convert.py``, ``app/output/epub_convert.py``) and
re-exports the stylesheet and direction script so nothing else has
to change.
"""

from app.output.html_pdf import (  # noqa: F401  (re-exported)
    PREPARE_DOCUMENT,
    PRINT_CSS,
    render_html_pdf,
    write_html_pdf,
)

__all__ = ["PREPARE_DOCUMENT", "PRINT_CSS", "render_html_pdf", "write_html_pdf"]
