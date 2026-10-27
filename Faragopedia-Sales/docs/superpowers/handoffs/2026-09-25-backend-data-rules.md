# Handoff: build the wiki data rules into the backend

**Written:** 2026-09-25, end of the session that cleaned up the production wiki.
**Next task:** make the backend enforce the rules the `tools/wiki_maintenance/` scripts currently
apply after the fact (ADR 0008 "Cons"). Start with a brainstorm/spec with Nick; nothing is
designed yet.

## Where things stand

- Production wiki (VPS) was rebuilt on 2026-09-24/25: 305 company pages on the entity-type
  schema, ~1,165 contacts, duplicates merged, missing pages created, raw-name links repaired,
  `notes` cleaned. Backups: `pre-company-enrichment-2026-09-24.zip`, `pre-correction-pass-2026-09-25.zip`
  in `04_Projects/Client-Projects/FaragoProjects-callsheet-migration/audit-2026-09-22/` (AI-Wise, not
  this repo — they contain PII).
- The scripts, rules and pitfalls are in `tools/wiki_maintenance/` (README first), the skills in
  `/.claude/skills/faragopedia-*`, the decision in `docs/decisions/0008-wiki-maintenance-toolkit.md`.
  Merged to `main` via PR #13; not on `vps-prod-deploy` (tooling only).
- A configured copy of the toolkit (with `.env`, the private correction plan and a warm
  Wikidata cache) sits in the worktree `.worktrees/wiki-maintenance-toolkit` of the local clone
  (`Nextcloud/AI/AI-Wise/04_Projects/Client-Projects/FaragoProjects-Faragopedia`). Nick's main checkout has his own uncommitted work
  on `docs/vps-deployment-handoff` — work in a new worktree, never there.

## The rules to enforce in the app

1. **Notes:** after any AI write (ingest, lint fix, chat-driven edits, import), `notes` on contact
   and company pages is cleared unless it starts `HUMAN:`. Human edits in the UI are not AI
   writes — confirm with Nick whether the rule should touch them at all.
2. **Wikilinks are real paths:** `key_contacts`, contact `company:`, callsheet `client:` etc. must
   be `[[contacts/slug]]` / `[[companies/slug]]`, never `[[Name]]`. Resolve names with the same
   `norm()` + name/`aliases:` matching as `enrich_companies.py`; unresolved stays plain text,
   never a guessed link.
3. **Company resolution in ingest:** "McQueen" -> `alexander-mcqueen` via `aliases:`; joint clients
   ("A / B") credit both; a bracketed parent is dropped. Stops new duplicate pages being created.
4. **Status / farago_history** derived from job dates (18-month Active Client window); non-schema
   status values cleared. Farago's own pages are excluded.
5. **Section schema:** new company pages get the entity-type sections; generated lines must be
   recognisable so a rebuild never duplicates them (see the Meeting History bug in the README).

## Where the backend writes pages (`backend/agent/wiki_manager.py`, main @ 74d7cd2)

- `_write_page()` (~line 536) — used by ingest.
- `ingest_source()` (~line 665) — the LLM ingest; its prompt (~lines 111, 166) already says to use
  `[[subdir/page-name]]`, yet raw `[[Name]]` values reached frontmatter, so enforce in code, not
  prompt. The frontmatter serializer (~line 259) special-cases values starting `[[`.
- `import_pages()` (~line 1407), `save_page_content()` (~line 1590), lint fixes (`lint()` ~865).
- A natural shape: one `data_rules.py` module (normalise frontmatter per entity type, clear notes)
  called from each write path, with unit tests ported from `tools/wiki_maintenance/tests/`.

## Constraints and gotchas

- Backend CI (`backend-tests`) already fails on `main` with 2 tag-suggestion tests in
  `tests/test_search_and_tags.py` (pre-existing since 2026-09-24, likely from `_suggest_tags`
  moving onto the ingest LLM) — fix or at least don't add to it.
- The app's AI runs on OpenRouter models (Gemini etc.), not Claude, so Claude skills don't reach
  it; rules must be in code.
- Deploy: PR -> `main`, then merge `main` -> `vps-prod-deploy` and redeploy the Portainer stack
  over SSH (`docs/deployment.md`, ADR 0007). Never redeploy with `env: []` — it wipes the stack's
  env vars.
- Chat `max_tokens` is still uncapped (known issue from 2026-09-14) — relevant if chat gains
  write paths.

## Open data items (need a human, not code)

CRM rows: "Acme Group / Jane Smith" (template), "Art Director / Sarah Bassett" and "Photo Agent /
Chris Boales" (role in the company column), Byredo filed as "Byredo HQ". Callsheets 428, 466, 470,
471 have client "unknown". Eight `HUMAN:` notes on the wiki await a person (6 surname spellings,
Kirsty Wilson's surname, Ida Walle's title) plus two on company pages (Invisible Dynamics match,
Harper's Bazaar edition).
