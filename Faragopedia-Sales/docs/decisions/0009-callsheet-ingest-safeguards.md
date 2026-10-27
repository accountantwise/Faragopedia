# ADR-0009: Callsheet ingest in the repo, with import safeguards

> **Status:** Accepted
> **Date:** 2026-10-26
> **Decided by:** Nick + Claude

## Context

Simon reported people filed as companies (`companies/jordan-example`) and companies filed
as people (`contacts/adidas`). The cause: callsheet extracts escape a pipe inside a cell as
`\|` ("Y3 \| SPOMA"), and five scripts each split table rows with a plain `split("|")`. The
escaped pipe became an extra cell, every later column shifted by one, and the role fragment
was read as the name and the name as the company. Across the 81 pushed jobs this created
14 fake company pages and 18 junk contacts, and ~80 people never reached the wiki at all —
with nothing in the pipeline reporting it. The data was repaired the same day (backups,
row-by-row callsheet merges, 82 contacts created, 32 pages archived, scan clean).

The pipeline that did it lived only in the "frozen" callsheet-migration folder outside this
repo, while job 510 and a ~95-file 2026 backlog still need it.

## Decision

1. Move the ingest pipeline into `tools/callsheet_ingest/` (with its tests). Extracts and
   the staff list stay outside the repo (`CALLSHEET_EXTRACTS_DIR`, `FARAGO_STAFF_LIST`):
   they hold real contact details and HR data, and this repo is public.
2. `push_job.py` is the only supported push path. The old bulk `main()` of
   `push_to_faragopedia.py` is retired (wrong filenames, no wikilinks, overwrote pages).
3. Safeguards, each on that path:
   - one escape-aware, width-checked table parser (`mdtable.py`), used by every reader;
   - per-callsheet reconciliation: rows in = kept + dropped-with-a-reason, or the run stops;
   - a quarantine for pages about to be created (role labels, company names as people,
     people's names as companies, near-duplicates of existing contacts, Farago's own
     offices/staff, initials) — held items are never written;
   - an existing job page is never overwritten without `--replace`;
   - a full snapshot before any `--live` write, or no write.
4. The same data rules run in the app's Lint tab (`backend/agent/data_lint.py`), before the
   LLM pass, tagged "Data rule:" and excluded from the LLM auto-fix.

## Consequences

### Pros

- The failure that reached production now stops the run at three separate points (parse,
  reconcile, quarantine), and anything that slips past shows up in Lint.
- One maintained copy of the parser, tested with the incident's own rows.

### Cons

- A quarantined name stays plain text until a person resolves it (aliases file or by hand)
  — slower than auto-creating, deliberately.
- `data_lint.py` and `quarantine.py` encode overlapping rules in two places (backend vs
  tools). The backend data-rules work (handoff 2026-09-25) is the place to unify them.
