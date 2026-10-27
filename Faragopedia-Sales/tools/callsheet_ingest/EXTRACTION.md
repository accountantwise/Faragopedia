# Callsheet Extraction Runbook

Run this as a Claude Code session after `fetch_callsheets.py` has populated `manifest.json`
and downloaded PDFs into `staging/`.

**This file is the raw archival extract — it keeps everything the callsheet contains.**
Deciding which people and fields reach the Faragopedia wiki page happens later, at
ingestion. Do not filter here; a field dropped at this stage is gone for good.

## Process

**Work `"year": "2026"` entries first, then 2025.** The harvest covers both, but 2026 is
the agreed priority and each callsheet is a separate extraction pass.

For each entry in `manifest.json` under `"files"` with `"status": "pending"`:

1. Read the file at the entry's **`extract_path`** — not `staging_path`. For a PDF they
   are the same file; for a spreadsheet, `extract_path` points at a markdown rendering
   produced at fetch time, because spreadsheets can't be read directly.
   - `"source_format"` tells you which you have.
   - `"alternate_format_of"`, when present, lists the same callsheet exported in another
     format. **Extract it once.** Prefer whichever is more complete — usually the
     spreadsheet, since PDF export sometimes truncates wide contact tables — and mark the
     others `"status": "duplicate"` with `"duplicate_of"` set.
   - `"version_rank"`, when present, ranks version-variants of the same callsheet:
     **0 is the preferred one** (FINAL wins, then UPDATED, then highest V-number, then
     most recently modified). `"version_candidates"` lists the others, and
     `"version_marker"` shows what was detected.

     Extract rank 0 and mark the rest `duplicate` — **unless the content says otherwise.**
     The ranking is mechanical and the grouping is deliberately conservative: Farago
     sometimes rename a callsheet between versions, so genuine variants occasionally fail
     to group and appear as separate rank-less entries. If two "versions" turn out to be a
     fitting and a shoot day, they are different callsheets — extract both.
2. Decide whether it's a real, usable callsheet — it has at least a production/shoot
   identity, plus a schedule, a location, or a contact list.
   - If not: set `"status": "disqualified"` and add `"disqualified_reason": "<one line>"`
     to the entry, save the manifest, and move to the next entry.
   - **Blank templates are the common disqualification.** 29 harvested files carry
     `TEMPLATE` in the name, but the word alone decides nothing:
     `FP CALL SHEET TEMPLATE.xlsx` is empty boilerplate, while
     `534_COS_RECCE_CITY_CALL SHEET TEMPLATE.xlsx` is a real Athens recce that merely
     kept its template's filename.

     The discriminator is the **content**: a blank carries asterisk-wrapped placeholders
     (`*JOB NAME*`, `*DATE* *MONTH* *YEAR*`, `*ADDRESS*`, `*STUDIO NAME (HYPERLINKED)*`)
     and unfilled times (`SUNRISE: X:XX AM`, `0:00 AM`). If those are present and no real
     name, date or address is, disqualify it as `blank template`.
3. **Check whether the file holds more than one callsheet.** A spreadsheet workbook often
   carries one tab per shoot day or shoot type — `PRE-LIGHT - CALL SHEET`,
   `RECCE - CALL SHEET`, `SHOOT DAY - CALL SHEET HK`, `Call Sheet - DAY 1`. **Each such
   tab is its own callsheet and gets its own output file.** One file does not mean one
   record.

   This is not an edge case: **53% of 2026 workbooks are multi-tab (up to 7 tabs), against
   19% in 2025.** Farago moved toward multi-day workbooks, so assume multi-tab for 2026.

   - The tab name usually gives `shoot_type` (recce / fitting / pre-light / shoot day) and
     sometimes a location or group split (`HK`/`SL`, `GROUP 1`/`GROUP 2`). Both belong in
     the record — location in `locations`, group noted in the title.
   - A tab prefixed `OLD` (e.g. `OLD | 17th SHOOT | Call Sheet`) is a superseded version
     **inside** the workbook. Skip it in favour of its live sibling.
   - Tabs that aren't callsheets (rate cards, notes, blank) are skipped, not extracted.
   - `"tab_version_rank"` on the entry ranks version-variants **within** the workbook
     (rank 0 preferred). Check `"tab_version_confidence"` first: `high` means an
     explicit `OLD` marker or V-number decided it and you can trust rank 0; `low`
     means the only signal was a trailing `(2)`, which is Excel's duplicate-sheet
     naming and says nothing about which copy was edited — compare them yourself.

4. Extract into markdown at `callsheets-md/YYYY-MM-DD-<production-slug>.md` using the
   schema below. Use the shoot date from the callsheet itself; if it has none, use the
   entry's `modified` date. Missing fields are written as `unknown`, never omitted.
   Where one file yields several callsheets, suffix the slug to keep filenames unique
   (e.g. `-recce`, `-day-1`, `-fitting`).
5. Set the entry's `"status": "done"`.
6. Save `manifest.json` after every file, not just at the end — this makes the session
   safely resumable if it's stopped partway through.

After the batch, run `python backfill_source_pointers.py` to populate the job-level and
source-pointer fields. Those are derived mechanically, so don't hand-write them.

## Reading the Dropbox path

`job_reference_number`, `category` and `city` come from the path, but **anchor on the
job-number segment — never count directory levels.** Path depth in this archive ranges
from 8 to 13, so fixed-depth parsing breaks.

```
/Sylvia Farago LTD Team Folder/01_Past Shoots/<YEAR>/<CITY>/<CATEGORY>/<JOBNUM_CLIENT>/...
                                                                       ^^^^^^^^^^^^^^
                                     match /^\d{3}[_ -]/, then read upward for the rest
```

**`city` is the Farago office that ran the job, not where the shoot happened.** Jobs filed
under `.../2026/London/...` shoot in Athens, Milan, Paris, Tokyo and Dubai. Take the actual
shoot location from the sheet into `locations`, and never present the path-derived `city`
as the shoot location.

Everything *below* the job segment is unreliable — `PRODUCTION/`, `*WRAP DOC/`,
`PRODUCTION_525_ADIDAS HYPERBOOST/`, day folders named `1 APRIL`, `DAY 1 - 7TH APRIL`,
`16TH - RECCE/FINALS`. Never parse it for structure, but **do read it as a hint**: those
folder names often disclose the shoot type (recce / fitting / shoot day / company move)
more clearly than the PDF does. Record what it tells you in `shoot_type`.

## Output schema

```markdown
---
production: <full name as written on the sheet, or "unknown">
campaign: <the campaign within the job — see below>
shoot_date: YYYY-MM-DD
shoot_day: <e.g. "1 of 2", or "unknown">
shoot_type: <shoot | fitting | recce | pre-light | company move | event | unknown>
client: <client/brand name, or "unknown">
production_company: <or "unknown">
locations: [<address or venue name>, ...]
job_reference_number: <derived — leave to backfill script>
category: <derived — leave to backfill script>
city: <derived — leave to backfill script>
job_folder_key: <derived — leave to backfill script>
job_folder: <derived — leave to backfill script>
source_doc: <derived — leave to backfill script>
source_filename: <derived — leave to backfill script>
source_md5: <derived — leave to backfill script>
source_size_bytes: <derived — leave to backfill script>
source_path: <the entry's dropbox_path>
---

# <Production Name> — Callsheet (<Shoot Date>)

## Schedule
<call times, key schedule beats>

## Locations
- <name/address, with parking/access notes if present>

## Contacts

| Canonical role | Role (verbatim) | Name | Company / agency | On set | Phone | Email |
|----------------|-----------------|------|------------------|--------|-------|-------|
| ...            | ...             | ...  | ...              | yes/no | ...   | ...   |

## Production services
<hospital, medic, catering, equipment hire, couriers — organisations, not people>

## Notes
<weather, wardrobe, travel, special instructions, anything else on the sheet>
```

## Campaign, production, shoot type and day

These four are routinely jammed into one string on the sheet — `COS - High Summer, Shoot
Day 1 of 2` is a campaign, a shoot type and a day number in a single line. Split them out.

- **`production`** — the full name as written. Keep it verbatim, like `role_raw`.
- **`campaign`** — the production with the shoot-type and day suffixes stripped:
  `COS - High Summer, Shoot Day 1 of 2` → `COS - High Summer`. For most jobs there is only
  one campaign and it equals the production name; write it anyway.
- **`shoot_type`** / **`shoot_day`** — what was stripped off.

**A job can hold more than one campaign.** Job 534 covers *COS Summer in the City*
(13–15 Mar) and *COS High Summer* (16–18 Mar) with a different photographer on each. That
is still **one job and one wiki page** — but the campaign must be recorded, because a
job-wide people roster otherwise shows two photographers on disjoint days with nothing
explaining why.

Do not infer a campaign split from a change of personnel. Read it from the name.

Role labels on real callsheets are wildly inconsistent — the existing 39-file corpus
contains **331 distinct role labels, 51% of which appear exactly once**. Resolve them
here, while you still have the PDF's layout, section headings and column context in
front of you. That context is gone by the time anyone sees a bare string.

- **`Role (verbatim)`** — copy exactly as printed. Never lose it; it is the audit trail.
- **`Canonical role`** — map to an entry in `roles.yml`. If nothing fits, write `other`
  and leave the verbatim value to be reviewed later. Never guess at a near-match:
  `Photo Assistant` is not a `photographer`, and `Producer (Photographer)` is the
  photographer's producer, not the photographer.
- **Do not treat these as part of the role** — they are separate columns:
  - `(not on set)` → `On set` = no
  - `(Client)` / `(Client - Adidas)` → the person is client-side; put the brand in
    `Company / agency`
  - `, Farago Projects` / `, MM` → that's a company, not a role
- **A `PRODUCTION | FARAGO PROJECTS` heading does NOT mean the person is Farago staff.**
  It groups the production team for that job, and most of them are freelance — on the
  McQueen 23 Jan sheet only 1 of 7 under that heading is on the staff list. Record the
  role from the heading; leave employment status to `staff_list.py`, which checks the
  list Simon supplied.
- **Relational roles** — `Agent (Photographer)`, `Photographer Agent` and
  `Agent (for Joe Bazalgette)` are all one role. Use canonical `agent` and name who they
  represent in `Company / agency`, e.g. `agent for Joe Bazalgette (Photographer)`.
  **Naming the principal is not optional.** The wiki keeps an agent only when the person
  they represent is kept, and merges them onto that person's row as "contact via" — so
  an agent recorded without a principal cannot be placed, and will be dropped. Across the
  corpus 45% of agent rows carry a phone against 3% of principal rows, so losing the link
  loses the only usable contact for that person.
- **Compound roles** — `Photographer/Director`, `Photographer + Director` and
  `Director/Photographer` are one person wearing two hats. List the canonical roles
  separated by `+`, e.g. `photographer + director`.
- **Organisations are not people.** `Hospital`, `Catering`, `Medic`, `Lighting EQ` and
  similar belong under **Production services**, not in the Contacts table.

## Slug rules

- Lowercase, spaces to hyphens, strip punctuation.
- If the production name is unknown, use the original filename's stem instead.

## When done

Report a summary: total entries processed, `done` count, `disqualified` count (with
reasons), any entries still stuck in `error` status from phase 1, and — importantly —
**every role you had to mark `other`**, so the controlled vocabulary in `roles.yml` can
be extended rather than silently drifting.
