# Callsheet ingest

Turns Farago callsheet extracts (one markdown file per callsheet day, produced per
`EXTRACTION.md`) into one wiki page per job, plus the contact and company pages its
People table links to. Moved here on 2026-10-26 from the frozen
`FaragoProjects-callsheet-migration` folder so there is one maintained, tested copy; see
ADR 0009. Company-page enrichment and notes cleanup live next door in `../wiki_maintenance/`.

## Setup

```
cd Faragopedia-Sales/tools/callsheet_ingest
cp ../wiki_maintenance/.env .env      # same API credentials, then add the lines below
pip install -r requirements.txt
python -m pytest -q tests             # offline, no credentials or data needed
```

`.env` (git-ignored) needs, besides the `FARAGOPEDIA_*` API credentials:

| Variable | What |
| --- | --- |
| `FARAGOPEDIA_WIKI_URL` | browser-facing wiki host, for job-folder links (not the API host) |
| `CALLSHEET_EXTRACTS_DIR` | the `callsheets-md/` extracts — **outside this repo** (real phone numbers) |
| `FARAGO_STAFF_LIST` | Simon's staff list (client HR data) — outside this repo |
| `WIKI_SNAPSHOT_DIR` | where pre-write backups go; default `backups/` here (git-ignored) |

## Pushing a job

```
python push_job.py --job 510                 # dry run: writes out/job-510/, nothing to the wiki
```

Review `out/job-510/`:

- `quarantine.md` — names held back from becoming pages, each with the reason. Common ones:
  a spelling variant of an existing contact, a Farago office as a company, initials-only talent.
- `report.txt` — the filter report and the per-callsheet reconciliation.
- `callsheets/`, `contacts/`, `companies/` — every page that would be written.

Resolve spelling variants and company names with an aliases file (human-approved, never guessed):

```json
{"people": {"Kenta Morikaw": "kenta-morikawa"},
 "companies": {"Farago Projects London": "farago-projects", "YY": "yohji-yamamoto-yy"}}
```

```
python push_job.py --job 510 --aliases aliases-510.json          # re-check the dry run
python push_job.py --job 510 --aliases aliases-510.json --live   # snapshot, write, read back
```

Then, as the command prints: `build_job_links.py`, `rebuild_interaction_history.py --live --only <contacts>`,
`../wiki_maintenance/enrich_companies.py --live --only <companies>`, `../wiki_maintenance/clear_notes.py --live`.

A job that already has a page is refused: replacing it would lose hand fixes. Merge
changes into the live page row by row, or pass `--replace` after checking it.

## Safeguards (2026-10-26)

An escaped `\|` inside a role ("Y3 \| SPOMA") was split as a cell boundary by five private
copies of `split("|")`. Every later column shifted: people became companies, companies and
role labels became contacts, ~80 people silently vanished, and nothing noticed. So:

1. **One parser** — `mdtable.py`. Unescaped pipes only; a row whose cell count differs from
   its header raises `MalformedRow`. Every table reader uses it.
2. **Reconciliation** — `wiki_filter.filter_people`: rows read = kept + dropped with a named
   reason, per callsheet, or `ReconciliationError`. Counts are in `report.txt`.
3. **Quarantine** — `quarantine.py` checks every page about to be created (role labels,
   company names as people, people's names as companies, `\` or `|`, near-duplicates of
   existing contacts, Farago's own offices and staff, initials). Held items are never written.
4. **Lint** — the same checks run in the app's Lint tab (`backend/agent/data_lint.py`),
   tagged "Data rule:" and never handed to the LLM auto-fixer.
5. **Snapshot first** — every `--live` run calls `wiki.require_snapshot()` and stops if the
   full export fails.

## Not here

Harvesting from Dropbox (`fetch_callsheets.py`) and the one-off repair scripts stay in the
callsheet-migration folder as history. Extraction itself is a Claude session per PDF, per
`EXTRACTION.md`.
