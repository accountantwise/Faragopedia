"""Rebuild every contact page's '## Interaction History' section from scratch, from the
live People tables of every callsheet that links to it.

Why: render_job_page() never writes back to a contact page when it links to it — a
contact's Interaction History only ever gets the entry from whichever job happened to
create their page, and is never updated on later jobs. Spot-checked 2026-09-24: one freelancer
links from 5 live callsheets (527, 534, 540, 548, 550) but his page only listed job 534.
A full scan found 158 of 905 linked contacts affected, one appearing on 33 callsheets.

This is a full rebuild of the section, not an append — the existing section is a mix of
one hand-written entry, auto-generated fragments ("Appeared on job N"), and (for the 9
pages hand-enriched 2026-09-24) prose paragraphs. Rebuilding uniformly from the callsheet
data itself is more reliable than trying to merge three inconsistent formats, and every
one of those existing entries' facts (job number, role, dates) is independently
re-derivable from the callsheet the entry names, so nothing is lost — only the exact
wording changes. Only the '## Interaction History' section is touched; every other
section and all frontmatter fields are preserved byte-for-byte.

One line per job, in this format, sorted by shoot_start (oldest first):
  "{shoot_start} to {shoot_end}: {role} for {client}, {campaign} (job {N})."
  or, single-day: "{shoot_start}: {role} for {client}, {campaign} (job {N})."

Read-only by default (--dry-run, the default); pass --live to write.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from dotenv import load_dotenv
load_dotenv(HERE / ".env")

from faragopedia_client import Faragopedia, FaragopediaError
from wiki import all_pages, require_snapshot
from postprocess import PEOPLE_HEADER, _people_rows

FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---\n', re.DOTALL)
FIELD_RE = re.compile(r'^([a-zA-Z_]+):\s*(.*)$', re.MULTILINE)


def parse_frontmatter(content: str) -> dict[str, str]:
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}
    return dict(FIELD_RE.findall(m.group(1)))


COMPANY_LINK_RE = re.compile(r'^\[\[companies/([a-z0-9-]+)\]\]$')


def clean_value(v: str, company_names: dict[str, str] | None = None) -> str:
    """Strip quotes/brackets from a frontmatter scalar: '"534"' -> '534'. A company link
    becomes that page's own `name` when known ('[[companies/alexander-mcqueen]]' ->
    'Alexander McQueen'); title-casing the slug gave 'Alexander Mcqueen' (2026-10-26)."""
    v = v.strip().strip('"').strip("'")
    m = COMPANY_LINK_RE.match(v)
    if m:
        slug = m.group(1)
        return (company_names or {}).get(slug) or slug.replace("-", " ").title()
    return v


def extract_people_rows(content: str) -> list[tuple[str, str, str]]:
    """Returns [(contact_slug, role, days_str), ...] from the People table.
    days_str is '' when the table has no Days column (single-day job).
    Rows are split by the shared escape-aware parser and width-checked (MalformedRow)."""
    lines = content.split("\n")
    header = next((l for l in lines if l.startswith(PEOPLE_HEADER)), "")
    has_days_col = "Days" in header
    rows = []
    for _i, raw in _people_rows(lines):
        cells = [c.strip() for c in raw]  # cells[0]='', 1=Role, 2=Name, 3=Company, 4=Contact, [5=Days]
        m = re.search(r'\[\[contacts/([a-z0-9-]+)\]\]', cells[2])
        if m:
            rows.append((m.group(1), cells[1], cells[5] if has_days_col and len(cells) > 5 else ""))
    return rows


def format_entry(fm: dict[str, str], role: str, callsheet_path: str,
                 company_names: dict[str, str] | None = None) -> str:
    job = clean_value(fm.get("job_reference_number", "?"))
    campaign = clean_value(fm.get("name", "")) or "unknown campaign"
    client = clean_value(fm.get("client", ""), company_names)
    start = clean_value(fm.get("shoot_start", ""))
    end = clean_value(fm.get("shoot_end", ""))

    date_part = start
    if end and end != start and end.lower() != "unknown":
        date_part = f"{start} to {end}"

    client_part = f" for {client}" if client and client.lower() != "unknown" else ""
    role_title = role.strip().title() if role else "Crew"
    # Bare wikilink, not a pipe-aliased one: the wiki's rendering behavior for [[path|Display]]
    # is unconfirmed outside the AI chat panel (which needed its own special-case parsing for
    # it per HANDOFF.md), so this uses only the syntax already proven live across 80+ callsheets.
    job_link = f"[[{callsheet_path.removesuffix('.md')}]]"

    return f"{date_part}: {role_title}{client_part}, {campaign} (job {job}, {job_link})."


def build_contact_history(all_paths: dict[str, list[str]], api: Faragopedia) -> dict[str, list[tuple[str, str]]]:
    """Returns contact_slug -> [(shoot_start, entry_text), ...] across every callsheet."""
    contact_entries: dict[str, list[tuple[str, str]]] = defaultdict(list)
    callsheet_paths = all_paths.get("callsheets", [])
    company_names: dict[str, str] = {}  # client slug -> the company page's own name
    for i, path in enumerate(callsheet_paths, 1):
        content = api.get_page(path)
        fm = parse_frontmatter(content)
        start = clean_value(fm.get("shoot_start", ""))
        m = COMPANY_LINK_RE.match(fm.get("client", "").strip().strip('"').strip("'"))
        if m and m.group(1) not in company_names:
            cfm = parse_frontmatter(api.get_page(f"companies/{m.group(1)}.md")) \
                if f"companies/{m.group(1)}.md" in all_paths.get("companies", []) else {}
            company_names[m.group(1)] = cfm.get("name", "").strip().strip('"').strip("'")
        for slug, role, _days in extract_people_rows(content):
            entry = format_entry(fm, role, path, company_names)
            contact_entries[slug].append((start, entry))
        if i % 20 == 0 or i == len(callsheet_paths):
            print(f"  scanned {i}/{len(callsheet_paths)} callsheets")
    return contact_entries


def rebuild_section(content: str, entries: list[str]) -> str:
    """Replace the '## Interaction History' section's body with `entries`, one per line
    pair (blank-line separated), leaving every other section untouched."""
    body = "\n\n".join(entries) if entries else ""
    pattern = re.compile(
        r"(^## Interaction History\s*\n)(.*?)(?=\n## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if not pattern.search(content):
        return content  # no such section on this page; leave it alone
    # Use a function replacement, never a string template: re.sub interprets a literal
    # backreference like \1 followed by a digit (e.g. body starting "2026-...") as a
    # longer group reference (\12), corrupting the heading. A callable's return value is
    # inserted verbatim, sidestepping backreference parsing entirely.
    suffix = (body + "\n") if body else ""
    return pattern.sub(lambda m: m.group(1) + suffix, content, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--limit", type=int, help="Only process the first N affected contacts (for testing)")
    ap.add_argument("--only", nargs="+", metavar="SLUG",
                    help="Only rebuild these contact slugs (e.g. the people on one job you just pushed)")
    args = ap.parse_args()

    api = Faragopedia()
    all_paths = all_pages()
    if args.live:
        print("snapshot:", require_snapshot("pre-interaction-history"))

    print("Scanning all callsheets to build contact -> jobs map...")
    contact_entries = build_contact_history(all_paths, api)
    print(f"Found {len(contact_entries)} contacts linked from at least one callsheet.")

    contacts_to_update = list(contact_entries.items())
    if args.only:
        contacts_to_update = [(s, e) for s, e in contacts_to_update if s in set(args.only)]
    if args.limit:
        contacts_to_update = contacts_to_update[: args.limit]

    changed = 0
    unchanged = 0
    errors = []
    for slug, entries in contacts_to_update:
        path = f"contacts/{slug}.md"
        if path not in all_paths.get("contacts", []):
            continue
        sorted_entries = [e for _start, e in sorted(entries, key=lambda x: x[0])]
        content = api.get_page(path)
        new_content = rebuild_section(content, sorted_entries)
        if new_content != content:
            changed += 1
            if args.live:
                try:
                    api._call("PUT", f"/api/pages/{path}",
                               ["-H", "Content-Type: application/json",
                                "-d", json.dumps({"content": new_content})])
                except FaragopediaError as e:
                    errors.append((path, str(e)))
        else:
            unchanged += 1

    print(f"\n{'LIVE — written' if args.live else 'DRY RUN — nothing written'}.")
    print(f"Changed: {changed}, unchanged (already correct): {unchanged}, errors: {len(errors)}")
    for path, err in errors:
        print(f"  ! {path}: {err}")


if __name__ == "__main__":
    main()
