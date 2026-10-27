"""Stage 4 collection: filter callsheet extracts and group them into one Day list per job.

`collect()` is what every push path starts from. Pushing itself is `push_job.py`.

The extracts are read from CALLSHEET_EXTRACTS_DIR (never written to). They hold real
phone numbers and emails for freelancers and talent, so they live outside this public
repo — in Nextcloud, at 04_Projects/Client-Projects/FaragoProjects-callsheet-migration/
callsheets-md/ — and the path is set in .env.

Files that predate the schema rework are skipped and listed. They cannot be filtered —
without a canonical role column there is no keep/drop decision to make — and a partly
filtered page would silently omit most of a job's crew.

This module used to have a bulk-import main() (`python push_to_faragopedia.py`). It was
retired when the pipeline moved into this repo (2026-10-26): it named pages with
slug_for()'s `job-NNN-...` form instead of the live `NNNN-...` convention (duplicates),
skipped the People-table wikilinking, and overwrote existing pages, losing hand fixes.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

from job_page import Day
from staff_list import StaffList
from wiki_filter import FilterReport, RoleVocabulary, filter_people, parse_callsheet

HERE = Path(__file__).parent
# Tests set this; otherwise CALLSHEET_EXTRACTS_DIR is read on each call (.env is loaded by
# wiki.py, which every live script imports — not here, so importing this stays side-effect free).
EXTRACTS: Path | None = None

FOLDER = "callsheets"
FOLDER_DISPLAY = "Callsheets"
FOLDER_SINGULAR = "callsheet"
FOLDER_DESCRIPTION = (
    "Production callsheets from the Dropbox archive, one page per job reference number. "
    "A page aggregates every callsheet for that job — recce, fitting, pre-light, company "
    "move and shoot days — grouped by campaign where a job spans more than one."
)

# category and city are strings, not enums: category drifts in casing between years and
# the pre-2024 archive is not yet harvested, so a fixed value list would strand a real
# value behind a dropdown that cannot represent it.
FOLDER_FIELDS = [
    {"name": "type", "type": "string", "default": "callsheet"},
    {"name": "name", "type": "string", "required": True,
     "description": "Campaign name as printed on the callsheet"},
    {"name": "job_reference_number", "type": "string", "required": True,
     "description": "Farago job number, unique across the archive and the page key"},
    {"name": "client", "type": "string", "description": "Client or brand on the sheet"},
    {"name": "category", "type": "string", "description": "Advertising or Editorial, as filed"},
    {"name": "city", "type": "string",
     "description": "Farago office that ran the job, NOT where the shoot happened"},
    {"name": "campaigns", "type": "list", "default": "[]",
     "description": "One job can carry several campaigns with different crews"},
    {"name": "shoot_start", "type": "date", "description": "Earliest callsheet date on the job"},
    {"name": "shoot_end", "type": "date", "description": "Latest callsheet date on the job"},
    {"name": "job_folder_key", "type": "string",
     "description": "Stable key for the source job folder, resolved via a lookup table"},
]
FOLDER_SECTIONS = ["Overview", "Shoot Days", "People", "Source"]


def collect(job_filter=None):
    env_dir = os.environ.get("CALLSHEET_EXTRACTS_DIR")
    extracts = EXTRACTS or (Path(env_dir) if env_dir else None)
    if extracts is None or not extracts.is_dir():
        raise RuntimeError(
            "CALLSHEET_EXTRACTS_DIR is not set or not a folder. Point it at the callsheets-md/ "
            "extracts (kept outside the repo: they contain real contact details).")
    vocab = RoleVocabulary.load()
    try:
        staff = StaffList.load()
    except RuntimeError as e:
        print(f"WARNING: staff list unavailable, employment status will be omitted — {e}")
        staff = None

    report = FilterReport()
    by_job: dict[str, list[Day]] = defaultdict(list)
    for path in sorted(extracts.glob("*.md")):
        sheet = parse_callsheet(path)
        if sheet is None:
            report.schema_skipped.append((path.name, "no canonical-role column (pre-rework schema)"))
            continue
        if job_filter and sheet.job != job_filter:
            continue
        by_job[sheet.job].append(Day(sheet, filter_people(sheet, vocab, staff, report)))
    return by_job, report, staff


if __name__ == "__main__":
    sys.exit("Retired: use `python push_job.py --job N` (dry run) / `--live`. See README.md.")
