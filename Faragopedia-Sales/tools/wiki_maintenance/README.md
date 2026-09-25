# Wiki maintenance toolkit

Scripts that keep a live Faragopedia wiki's **company and contact pages** correct and
enriched, run from any machine that can reach the wiki's external API. Built and proven on
Farago's production wiki in September 2026 (305 company pages, ~1,165 contacts). The
Claude Code skills in `/.claude/skills/faragopedia-*` drive these scripts; any other agent
should read this file first.

| Script | What it does |
| --- | --- |
| `enrich_companies.py` | Rebuilds company pages onto the entity-type schema from the wiki's own data, free public data and (optionally) researched news. Idempotent. |
| `correction_pass.py` | Applies a human-verified plan: create missing companies/contacts, merge duplicates, repair links. |
| `clear_notes.py` | Clears the `notes` field on contacts/companies, keeping `HUMAN:` notes. Run after any AI pass. |
| `wikiapi.py`, `faragopedia_client.py` | List/read/write/archive/backup over the external API (curl, retries: Cloudflare resets are normal). |
| `merge_history.json` | Every company merge ever done (loser -> survivor). Old links are repointed from it on every run. |

## Setup

```
cd Faragopedia-Sales/tools/wiki_maintenance
cp .env.example .env        # fill in API + CRM spreadsheet credentials
pip install -r requirements.txt
python -m pytest -q tests   # offline, no credentials needed
```

Every script is a **dry run by default** and writes rendered pages + diffs to `out/`.
Pass `--live` to write. Before any live run take a backup: `wikiapi.export_backup(Path("backups/<date>.zip"))`
(`POST /api/export/import` restores it).

## How a company page is built

The schema is whatever `GET /api/entity-types` says for `companies` (sections: Company
Overview, Recent News & Social Activity, Contacts, Meeting History, Job History,
Competitor Production Companies, Industry Connections).

1. **Wiki data (no network beyond the wiki):** `key_contacts` resolved to real
   `[[contacts/slug]]` links; Contacts section with job titles plus everyone from the
   company seen on a callsheet; Job History from every callsheet (the `client:` field makes
   a client job; people in the People table make a non-client appearance); `last_job_date`,
   `farago_history`, `status`.
2. **Free public data:** Wikidata, accepted only when its official-website (P856) domain
   matches the page's `website` **and** the entity isn't a human; HQ country taken from the HQ
   city, not the company. Wikipedia summary for the Overview; the site's own meta description
   and social links as a fallback. Only fills empty fields. Cached in `enrichment-cache/`.
3. **Meeting History:** the CRM's Outreach Log, read-only, plus any `outreach/` or `meetings/`
   pages targeting the company, plus a "Converted" line when a client job followed outreach.
4. **Researched news/websites (optional, costs tokens):** `--research file.json`
   (`{slug: {website, news: [{date, headline, summary, url, source}]}}`) produced by the
   research step in the `faragopedia-enrich-companies` skill.

Human prose is never overwritten: a Company Overview is only regenerated when it is empty, a
stub ("Production company or agency."), or our own earlier output (it carries a `_Sources:`
line). Lines the script generates are recognised by `GENERATED_MEETING` / `GENERATED_CONTACT`
and rebuilt each run; anything else a person typed is kept.

## Rules decided by Nick (Farago) — do not change without asking

- **No RocketReach** for enrichment (protects the paid quota; its revenue figures were also
  wrong: USD mislabelled, implausible values).
- **Status:** Active Client if a client job ended within the last **18 months**, else Lapsed;
  Prospect if only outreach; any non-schema value (e.g. `Vendor`) is cleared to blank when no
  rule applies — supplier-only agencies stay blank.
- **Industry is never changed by the scripts.** New pages follow the precedent of comparable
  pages in the approved taxonomy (high-street fashion folds into `fashion-luxury`); magazines
  currently have no industry.
- **`parent_group` is plain text**, never a link to a page that may not exist.
- **Farago's own pages** (`farago-projects*`) are skipped entirely; they are hand-maintained.
- **Notes:** after ANY AI processing, run `clear_notes.py`. Only notes starting `HUMAN:` survive.
  Write a `HUMAN:` note whenever something needs a person (guessed surname, title conflict,
  spelling that disagrees with an email, match by name only).
- **Duplicates are merged only after a human verifies them.** The scripts flag candidates
  (`possible duplicate` in the report), never merge on their own.

## Matching rules

- Names match through `norm()`: case, accents, punctuation and `&`/"and" are ignored
  ("Ace & Tate" = `ace-and-tate`, "Catherine O'Tool" = `catherine-otool`). Also each company's
  `name` and `aliases:`. An ambiguous key matches nothing.
- Joint clients ("Y-3 / Mercedes", "Rimowa / Another Man China") credit every part; a bracketed
  parent is dropped ("Johnnie Walker (Diageo)").
- Never link a near miss. Unresolved values are reported and left as plain text.
- New page slugs always come from `wikiapi.slugify()`.

## Pitfalls we actually hit

- `PUT` accepts anything with a 200 — check structure after writing, not the status code.
- Some frontmatter is invalid YAML (`name: & Other Stories`, `off---white.com` breaks naive
  `split('---')`); use `split_page()`.
- A cleanup that assumed single-line `notes:` left orphaned lines and broke YAML on several pages.
- A resolver that stripped everything before the last `/` turned "Rimowa / Another Man China"
  into "Another Man China". Only strip a real `companies/` or `contacts/` prefix.
- Meeting History once re-kept its own output and duplicated on every run. **Prove idempotence
  on pages that have outreach entries** (e.g. run twice on Vuori/Mango and expect "same").
- Haiku research output needs filtering: it produced a hallucinated domain, subpages of a
  parent company's site (y-3 -> adidas.com would match Adidas in Wikidata), dates outside the
  window, self-descriptions posing as news, and namesakes. The skill lists the filters.
- The CRM's "(+6 more)" in a Key Contacts cell is literal text; the full list is in the
  Contacts tab.

## Known open items (2026-09-25)

- CRM rows needing a human: "Acme Group / Jane Smith" (template example), role typed in the
  company column ("Art Director / Sarah Bassett", "Photo Agent / Chris Boales"), Byredo filed as
  "Byredo HQ". Four callsheets have client "unknown" (jobs 428, 466, 470, 471).
- The backend itself does not yet enforce any of the rules above; that is the follow-up
  (see ADR 0008).
