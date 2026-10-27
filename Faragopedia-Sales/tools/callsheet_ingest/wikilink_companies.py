"""Link the 'Company / agency' column of every live callsheet's People table to its
existing companies/*.md page, when one exists under the exact slug.

A whole-wiki pass over postprocess.wikilink_companies() — the same step push_job.py
applies to each page it writes — for pages written before that existed. Exact-slug match
only via wiki.slugify(): a near miss is left as plain text rather than guessed at (the
2026-09-22 duplicate audit found "DM Casting" / "SMN Casting" sharing only "Casting").

Read-only by default (prints what would change); --live snapshots the wiki, then writes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from faragopedia_client import FaragopediaError  # noqa: E402
from postprocess import wikilink_companies  # noqa: E402
from wiki import all_pages, get_page, require_snapshot, slugify, write_page  # noqa: E402

# Cell values that are placeholders, never a real company name — never look these up.
NON_COMPANY_CELLS = {"", "—", "-", "unknown", "n/a"}


def exact_slug_resolver(company_paths: set[str]):
    def resolve(name: str) -> str | None:
        if not name or name.strip().lower() in NON_COMPANY_CELLS:
            return None
        slug = slugify(name)
        return slug if f"companies/{slug}.md" in company_paths else None
    return resolve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="Write changes. Default is dry-run.")
    ap.add_argument("--job", help="Only this callsheet path (e.g. callsheets/0534-cos-summer-in-the-city.md)")
    args = ap.parse_args()

    pages = all_pages()
    resolve = exact_slug_resolver(set(pages.get("companies", [])))
    paths = [args.job] if args.job else pages.get("callsheets", [])
    if args.live:
        print("snapshot:", require_snapshot("pre-wikilink-companies"))

    changed = 0
    for path in paths:
        content = get_page(path)
        new = wikilink_companies(content, resolve)
        if new != content:
            changed += 1
            print(f"{path}: +{new.count('[[companies/') - content.count('[[companies/')} company link(s)")
            if args.live:
                try:
                    write_page(path, new)
                except FaragopediaError as e:
                    print(f"  ! write failed: {e}")
    print(f"\n{'LIVE — written' if args.live else 'DRY RUN — nothing written'}. "
          f"{changed}/{len(paths)} callsheets changed.")


if __name__ == "__main__":
    main()
