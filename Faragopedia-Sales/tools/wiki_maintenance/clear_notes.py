"""Clear the `notes:` frontmatter field on contact and company pages, keeping human flags.

Rule (Nick, 2026-09-25): run this after ANY AI processing of the wiki. `notes` must not
become a second, drifting copy of Overview. The only notes that survive are ones flagged
for a human, i.e. whose value starts with `HUMAN:` — AI writes these when something needs
a person to check it, and people can use the same prefix to protect a note of their own.

Handles values YAML wrote across several lines, and repairs the orphaned continuation
lines an earlier version of this script left behind (it assumed notes were single-line).
Touches only the notes block; the rest of every page is left byte-for-byte as it was.

    python clear_notes.py                  # dry run: counts + every note that would be kept
    python clear_notes.py --live           # write
    from clear_notes import clean; clean(paths, live=True)   # from other pipelines
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(HERE / ".env")
import wikiapi as ia  # noqa: E402

HUMAN_PREFIX = "HUMAN:"
FOLDERS = ("contacts", "companies")
NOTES_BLOCK = re.compile(r"^notes:.*(?:\n[ \t]+\S.*)*$", re.M)


def frontmatter(content: str) -> tuple[str, str] | None:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, re.S)
    return (m.group(1), m.group(2)) if m else None


def cleaned(content: str) -> tuple[str | None, str]:
    """(new content or None if unchanged, reason)."""
    parts = frontmatter(content)
    if not parts:
        return None, "no frontmatter"
    fm_text, body = parts
    m = NOTES_BLOCK.search(fm_text)
    if not m:
        return None, "no notes field"
    try:
        value = str((yaml.safe_load(m.group(0)) or {}).get("notes") or "").strip()
    except yaml.YAMLError:
        value = m.group(0).split(":", 1)[1].strip().strip("'\"")
    if value.startswith(HUMAN_PREFIX):
        return None, "kept (human flag)"
    if m.group(0) in ("notes: ''", 'notes: ""', "notes:"):
        return None, "already empty"
    new_fm = fm_text[:m.start()] + "notes: ''" + fm_text[m.end():]
    return f"---\n{new_fm}\n---\n{body}", "cleared"


def clean(paths: list[str] | None = None, live: bool = False, verbose: bool = False) -> dict[str, list[str]]:
    if paths is None:
        idx = ia.all_pages(refresh=True)
        paths = [p for f in FOLDERS for p in idx.get(f, [])]
    result: dict[str, list[str]] = {}
    for path in paths:
        if path.split("/")[0] not in FOLDERS:
            continue
        content = ia.get_page(path)
        new, reason = cleaned(content)
        result.setdefault(reason, []).append(path)
        if new and live:
            ia.write_page(path, new)
        if verbose and reason == "kept (human flag)":
            print(f"  kept {path}: {NOTES_BLOCK.search(content).group(0)[:160]}")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    result = clean(live=args.live, verbose=True)
    for reason, paths in sorted(result.items()):
        print(f"{reason:22} {len(paths)}")
    print("LIVE - written" if args.live else "DRY RUN - nothing written")


if __name__ == "__main__":
    main()
