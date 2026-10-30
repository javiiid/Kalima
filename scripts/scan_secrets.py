"""Scan for leaked credentials — the working tree and, with --history, every
commit ever made.

The provider key is kept out of the repo by a single named gitignore rule
(``config/config.yaml``). One rule between a live key and a public page is thin,
so this checks the actual content instead of trusting the rule: a copy-pasted
key in a test, a notebook, or a docstring would otherwise ship silently.

Run:   python scripts/scan_secrets.py            # tracked + untracked files
       python scripts/scan_secrets.py --history  # also every blob in git log
Exit:  0 clean, 1 a finding (fail the build / CI job).

Known, already-rotated leaks still sit in old commits. They are listed by exact
value in scripts/secrets_allowlist.txt (never by pattern, so a new key of the
same shape is still caught). Rotating a key does not erase it from history, so
the allowlist records that the leak is handled rather than pretending it is not
there.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent

#: High-signal credential shapes. A broad ``password = "..."`` match is handled
#: separately by GENERIC + _looks_secret so a code expression (a token *prefix*
#: being built, an i18n key) is not reported as a credential.
PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{16,}"), "OpenAI-style API key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub personal access token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "Google API key"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
]

GENERIC = re.compile(
    r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]"
)

PLACEHOLDERS = re.compile(
    r"(?i)(your[-_ ]|example|dummy|placeholder|xxx+|changeme|<your|redacted|fake|"
    r"test[-_]key|not[-_]a[-_]real|sup3r|secret-pass|\*\*\*)"
)

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".pdf", ".epub", ".zip"}
MAX_LINE = 4000
ALLOWLIST_FILE = Path(__file__).with_name("secrets_allowlist.txt")

#: Exact secret values that have been rotated; filled from ALLOWLIST_FILE.
ALLOWED: set[str] = set()


def load_allowlist() -> set[str]:
    if not ALLOWLIST_FILE.is_file():
        return set()
    return {
        line.strip()
        for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, errors="ignore", check=False
    ).stdout


def matches(text: str) -> list[str]:
    if not text or len(text) > MAX_LINE or PLACEHOLDERS.search(text):
        return []
    labels = []
    for pattern, label in PATTERNS:
        found = pattern.search(text)
        if found and found.group(0) not in ALLOWED:
            labels.append(label)
    generic = GENERIC.search(text)
    if generic and _looks_secret(generic.group(2)) and generic.group(2) not in ALLOWED:
        labels.append("assigned credential")
    return labels


def _looks_secret(value: str) -> bool:
    """Reject code, not credentials: i18n keys, paths, short prefixes."""
    if any(char in value for char in "./\\") or len(value) < 12:
        return False
    return any(char.isdigit() for char in value) and any(char.isalpha() for char in value)


def tracked_and_untracked() -> list[Path]:
    paths: set[Path] = set()
    for name in git("ls-files").splitlines():
        if name:
            paths.add(REPO / name)
    for line in git("status", "--porcelain").splitlines():
        if line.startswith("??"):
            paths.add(REPO / line[3:].strip())
    return sorted(paths)


def scan_files() -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []
    for path in tracked_and_untracked():
        if not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "\x00" in text[:2048]:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            labels = matches(line)
            if labels:
                findings.append((str(path.relative_to(REPO)), str(number), ", ".join(labels)))
    return findings


def scan_history() -> list[tuple[str, str, str]]:
    """Scan only added lines in every commit, so a removed key still surfaces."""
    process = subprocess.Popen(
        ["git", "-C", str(REPO), "log", "--all", "-p", "--no-color", "--no-ext-diff", "--no-textconv", "-U0"],
        stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore",
    )
    findings: list[tuple[str, str, str]] = []
    commit = ""
    path = ""
    assert process.stdout is not None
    for raw in process.stdout:
        line = raw.rstrip("\n")
        if line.startswith("commit "):
            commit = line.split(" ", 1)[1][:12]
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            labels = matches(line[1:])
            if labels:
                findings.append((f"{commit}:{path}", "added line", ", ".join(labels)))
    process.wait()
    return findings


def report(title: str, findings: list[tuple[str, str, str]]) -> None:
    print(f"=== {title} ===")
    if not findings:
        print("  clean\n")
        return
    for location, detail, labels in findings:
        print(f"  {location} ({detail}) -> {labels}")
    print()


def main(argv: list[str]) -> int:
    global ALLOWED
    ALLOWED = load_allowlist()
    print(f"repo: {REPO}\n")
    if ALLOWED:
        print(f"allowlisted (rotated) values: {len(ALLOWED)}\n")
    working = scan_files()
    report("working tree (tracked + untracked)", working)

    history: list[tuple[str, str, str]] = []
    if "--history" in argv:
        history = scan_history()
        report("git history (added lines, all refs)", history)

    total = len(working) + len(history)
    if total:
        print(f"FAIL: {total} potential secret(s) found.")
        return 1
    print("PASS: no secrets found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
