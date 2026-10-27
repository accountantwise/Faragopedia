# ADR-0008: Wiki maintenance toolkit and data-quality rules

> **Status:** Accepted
> **Date:** 2026-09-25
> **Decided by:** Nick + Claude

## Context

In September 2026 Farago's production wiki (~305 companies, ~1,165 contacts, 81 callsheets)
was cleaned up and enriched by scripts run from a separate client-projects repo, against the
external API. That work found systemic data problems the app itself created or never
prevented: `key_contacts` and contact `company:` fields holding raw-name links (`[[Very]]`)
that point nowhere; 274 of 291 company pages on an old section template; `notes` growing into
a drifting copy of Overview after every AI pass; duplicates from name variants; callsheet
clients with no company page. The scripts and the rules agreed along the way lived outside
this repo, so no future agent working here would know them.

## Decision

1. Keep the proven scripts in this repo at `tools/wiki_maintenance/` (external-API clients,
   dry-run by default, offline tests in CI), with the rules and pitfalls in its README.
2. Ship Claude Code skills in `/.claude/skills/faragopedia-*` that drive them
   (`enrich-companies`, `fix-and-merge`, `notes-cleanup`). `.gitignore` now ignores
   `.claude/*` except `.claude/skills/`.
3. Adopt these data rules (see the toolkit README for the full list): notes are cleared after
   any AI processing except `HUMAN:` notes; wikilinks must be real paths
   (`[[contacts/slug]]`, `[[companies/slug]]`); name matching ignores case/accents/punctuation
   and honours `aliases:`, never guesses; status is derived from job dates (18-month Active
   Client window); duplicates are merged only after human verification.

## Consequences

### Pros

- Any agent in this repo (Claude via skills, Gemini/others via AGENTS.md + the README) can
  repeat the enrichment and cleanup with the same safeguards.
- Tests pin the bugs that already broke production data once.

### Cons

- The rules are enforced by scripts run after the fact, not by the backend. The app's own
  ingest/chat (OpenRouter models, not Claude) can still write raw-name links or long notes.
  Porting the rules into `backend/agent/` (post-write notes cleanup, link normalisation,
  alias-aware company resolution in ingest) is the planned follow-up.
- The scripts talk to the API over the network, so they need API + CRM credentials in a local
  `.env` and are not run by the backend itself.

## Alternatives Considered

### Implement everything in the backend now

- Right long-term home, but needs design, tests and a redeploy; would have left the proven
  scripts and their lessons outside the repo in the meantime.

### Leave the scripts in the client-projects repo

- No change needed, but invisible to anyone working in this repo, which is exactly how the
  lessons were getting lost.
