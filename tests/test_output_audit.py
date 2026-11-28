"""Phase 0: the output audit harness must keep measuring the right things.

The harness is the before/after instrument for the output work. If it stops
seeing an image, a font or a nav entry, every later phase loses its baseline.
"""
from __future__ import annotations

from pathlib import Path

from scripts import output_audit


def test_output_audit_report_and_baseline(tmp_path):
    result = output_audit.run(tmp_path / "audit", render_png=False)

    report = Path(result["report"])
    assert report.is_file()
    assert "## Findings" in report.read_text(encoding="utf-8")

    entries = {
        (entry["source"], entry["format"]): entry
        for entry in result["entries"]
    }
    # A job-level failure means the harness itself broke, not a finding.
    assert not [
        entry for entry in result["entries"]
        if entry.get("format") == "job"
    ]

    # EPUB -> PDF goes through pandoc + Chromium: images and Vazirmatn.
    epub_pdf = entries[("epub", "translated_pdf")]["metrics"]
    assert epub_pdf["pages"] >= 1
    assert epub_pdf["images"] >= 1
    assert epub_pdf["has_vazirmatn"]

    # EPUB -> DOCX embeds the font and marks the Persian runs RTL.
    epub_docx = entries[("epub", "docx")]["metrics"]
    assert epub_docx["media"] >= 1
    assert epub_docx["odttf"] >= 1
    assert epub_docx["rtl"] >= 1

    # The reassembled EPUB carries a rebuilt nav and both spine entries.
    translated_epub = entries[("epub", "translated_epub")]["metrics"]
    assert translated_epub["nav_items"] >= 2
    assert translated_epub["spine"] == 2

    # PDF source: the overlay keeps the source image, scanned or not.
    assert entries[("pdf", "translated_pdf")]["metrics"]["images"] >= 1
    assert entries[("scanned", "translated_pdf")]["metrics"]["images"] >= 1

    # The report must say something; an empty findings list means the
    # measurements above are not being turned into sentences.
    assert result["findings"]
