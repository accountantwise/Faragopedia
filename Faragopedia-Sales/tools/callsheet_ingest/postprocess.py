"""Steps every rendered callsheet page goes through before it is written.

render_job_page() emits names and companies as plain text and slug_for() emits the
wrong filename form, so on their own they produce a page that is subtly wrong. These are
the fixes every live page received by hand or by one-off scripts until 2026-10-26; they
now live in one place and push_job.py applies them.
"""
from __future__ import annotations

from typing import Callable

from job_page import slug_for
from mdtable import check_width, split_raw

PEOPLE_HEADER = "| Role | Name |"


def page_path(job: str, days) -> str:
    """callsheets/NNNN-<campaign-words>.md — the zero-padded form every live page uses.
    slug_for() gives 'job-NNN-<words>', a different filename for the same page that
    silently creates a duplicate if used as the path."""
    full = slug_for(job, days)
    prefix = f"job-{job}-"
    words = full[len(prefix):] if full.startswith(prefix) else full[len(f"job-{job}"):].lstrip("-")
    return f"callsheets/{job.zfill(4)}-{words}.md" if words else f"callsheets/{job.zfill(4)}.md"


def _people_rows(lines: list[str]):
    """Yield (index, cells) for each data row of the People table, width-checked."""
    width = None
    for i, line in enumerate(lines):
        if line.startswith(PEOPLE_HEADER):
            width = len(split_raw(line))
            continue
        if width is None:
            continue
        if not line.startswith("|"):
            return
        if line.startswith("|---"):
            continue
        cells = split_raw(line)
        check_width(cells, width, "People table", line)
        yield i, cells


def wikilink_people(content: str, find_contact: Callable[[str], str | None],
                    aliases: dict[str, str] | None = None) -> str:
    """Link each People-table name to its contact page: an exact-slug match, or a
    human-approved spelling variant from `aliases` (name -> contact slug). Never a
    near miss — an unmatched name stays plain text."""
    aliases = aliases or {}
    lines = content.split("\n")
    for i, cells in list(_people_rows(lines)):
        raw = cells[2].strip()
        if raw.startswith("[["):
            continue
        warn = raw.endswith(" ⚠")
        bare = raw[:-2].strip() if warn else raw
        target = f"contacts/{aliases[bare]}" if bare in aliases else \
            (find_contact(bare) or "").removesuffix(".md")
        if target:
            cells[2] = f" [[{target}]]{' ⚠' if warn else ''} "
            lines[i] = "|".join(cells)
    return "\n".join(lines)


def wikilink_companies(content: str, resolve_company: Callable[[str], str | None]) -> str:
    """Link each People-table company cell to its company page (resolve_company returns a
    slug or None). The `employment` backtick suffix job_page appends stays outside the link."""
    lines = content.split("\n")
    for i, cells in list(_people_rows(lines)):
        raw = cells[3].strip()
        if not raw or raw == "—" or "[[" in raw:
            continue
        name, suffix = raw, ""
        if raw.endswith("`"):
            cut = raw.rfind("`", 0, len(raw) - 1)
            if cut > 0:
                name, suffix = raw[:cut].rstrip(), " " + raw[cut:]
        slug = resolve_company(name)
        if slug:
            cells[3] = f" [[companies/{slug}]]{suffix} "
            lines[i] = "|".join(cells)
    return "\n".join(lines)


def people_links(content: str) -> list[tuple[str, str]]:
    """(contact slug, role) for every linked name in the People table."""
    import re
    out = []
    for _i, cells in _people_rows(content.split("\n")):
        m = re.search(r"\[\[contacts/([^\]|]+)\]\]", cells[2])
        if m:
            out.append((m.group(1), cells[1].strip()))
    return out
