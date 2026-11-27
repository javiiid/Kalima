"""Provision the landing page's display face (Geist Sans).

WHY THIS IS A SEPARATE SCRIPT
-----------------------------
`build_fonts.py` owns Vazirmatn and is generated from the Python project's
woff2 files; it is also the file whose portability changes are load-bearing for
this checkout. The landing needs a second, unrelated face, so it gets its own
provisioning step rather than being bolted into a file that another process
regenerates.

WHY IT EXISTS AT ALL
--------------------
`public/fonts/` is gitignored -- font binaries are build artifacts, not source.
That is correct, but it has a sharp edge: `fonts-landing.css` declares Geist,
and if the file is absent the browser falls back to Vazirmatn for Latin text
with nothing in any log. That is precisely the failure this rebuild started
from (a declared Manrope face that was never shipped). So the file is fetched
or copied here, and `scripts/ensure-fonts.mjs` fails the build when it is
missing instead of letting the page render in the wrong typeface.

USAGE
-----
    python ../docs/build_landing_font.py

It prefers a local copy and only reaches the network if there is not one, so a
machine that has already built once never needs to be online again.
"""
import shutil
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

FRONTEND = Path(__file__).resolve().parents[1]
UI = FRONTEND / "ui"
FONT_OUT = UI / "public" / "fonts"
TARGET = FONT_OUT / "Geist-Variable.woff2"

# Geist Sans, variable wght 100-900, latin subset. Vercel ships it under the
# SIL Open Font License 1.1, which permits redistribution and self-hosting.
SOURCE_URL = (
    "https://cdn.jsdelivr.net/npm/geist@1.9.2/dist/fonts/geist-sans/Geist-Variable.woff2"
)

# A truncated download is worse than no download: it parses as a font, renders
# a subset of glyphs, and looks like a CSS bug. The real file is ~68 KB.
MIN_BYTES = 40_000


def main() -> int:
    FONT_OUT.mkdir(parents=True, exist_ok=True)

    if TARGET.is_file() and TARGET.stat().st_size >= MIN_BYTES:
        print(f"  geist: already present ({TARGET.stat().st_size // 1024} KB)")
        return 0

    local = FRONTEND.parent / "app" / "library" / "Geist-Variable.woff2"
    if local.is_file() and local.stat().st_size >= MIN_BYTES:
        shutil.copyfile(local, TARGET)
        print(f"  geist: copied from {local}")
        return 0

    print(f"  geist: fetching {SOURCE_URL}")
    try:
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
            payload = response.read()
    except Exception as error:  # noqa: BLE001 - the message is the point
        print(f"  FAILED to fetch Geist: {error}")
        print("  Place Geist-Variable.woff2 in public/fonts/ manually, or re-run online.")
        return 1

    if len(payload) < MIN_BYTES:
        print(f"  FAILED: downloaded {len(payload)} bytes, which looks truncated")
        return 1

    TARGET.write_bytes(payload)
    print(f"  geist: wrote {TARGET.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
