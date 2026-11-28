"""Provision the English UI's Latin face (Manrope).

WHY THIS IS A SEPARATE SCRIPT
-----------------------------
`build_fonts.py` owns Vazirmatn and regenerates `fonts.generated.css`;
`build_landing_font.py` owns the landing's Geist. Manrope is the third face and
belongs to neither file, so it gets its own step rather than being bolted into
one that another process regenerates.

WHY IT EXISTS AT ALL
--------------------
`public/fonts/` is gitignored, so a fresh clone has no Manrope. Nothing
produced it: the file was present on the development machine only as a
leftover, which is why `tests/latin-font.test.ts` passed locally and failed in
CI the moment the Vazirmatn import was fixed. `fonts-latin.css` declares the
face for `html[lang='en']`, so a missing file is not cosmetic -- the English UI
falls back to Vazirmatn's Latin with nothing in any log.

USAGE
-----
    python ../docs/build_latin_font.py

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
TARGET = FONT_OUT / "Manrope-Variable.woff2"

# Manrope, variable wght 200-800, latin subset, from Fontsource. Manrope ships
# under the SIL Open Font License 1.1, which permits redistribution and
# self-hosting. The version is pinned: an unpinned tag would let a font upgrade
# change line lengths in the UI without a commit that says so.
SOURCE_URL = (
    "https://cdn.jsdelivr.net/npm/@fontsource-variable/manrope@5.2.8"
    "/files/manrope-latin-wght-normal.woff2"
)

# A truncated download is worse than no download: it parses as a font, renders
# a subset of glyphs, and looks like a CSS bug. The real file is ~24 KB.
MIN_BYTES = 20_000


def main() -> int:
    FONT_OUT.mkdir(parents=True, exist_ok=True)

    if TARGET.is_file() and TARGET.stat().st_size >= MIN_BYTES:
        print(f"  manrope: already present ({TARGET.stat().st_size // 1024} KB)")
        return 0

    local = FRONTEND.parent / "app" / "library" / "Manrope-Variable.woff2"
    if local.is_file() and local.stat().st_size >= MIN_BYTES:
        shutil.copyfile(local, TARGET)
        print(f"  manrope: copied from {local}")
        return 0

    print(f"  manrope: fetching {SOURCE_URL}")
    try:
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
            payload = response.read()
    except Exception as error:  # noqa: BLE001 - the message is the point
        print(f"  FAILED to fetch Manrope: {error}")
        print("  Place Manrope-Variable.woff2 in public/fonts/ manually, or re-run online.")
        return 1

    if len(payload) < MIN_BYTES:
        print(f"  FAILED: downloaded {len(payload)} bytes, which looks truncated")
        return 1

    TARGET.write_bytes(payload)
    print(f"  manrope: wrote {TARGET.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
