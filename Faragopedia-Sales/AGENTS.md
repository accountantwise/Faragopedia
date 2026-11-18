# AGENTS.md — Single Source of Truth

> **This file is the shared context for ALL AI agents working on this project.**
> Both `CLAUDE.md` and `GEMINI.md` point here. Any agent-agnostic context,
> conventions, decisions, and project state should live in this file or in the
> `docs/` directory it references.

---

## Project Identity

| Field        | Value                                                    |
| ------------ | -------------------------------------------------------- |
| **Name**     | Faragopedia-Sales                                        |
| **Repo**     | `github.com/accountantwise/Faragopedia-Sales`            |
| **Phase**    | 🟡 MVP Development / Settings Section + Entity Templates planned, ready to implement |
| **Stack**    | Python/FastAPI + React/Vite                              |
| **Deploy**   | One Portainer stack: OVHcloud VPS (production, `vps-prod-deploy`). The office NUC (dev/test) was retired in Nov 2026; a dev stack on gecko is planned. See [Deployment](#deployment) below and [ADR 0007](docs/decisions/0007-vps-production-deployment.md). |

## Project Vision

Faragopedia-Sales is a ground-up redesign of the original Faragopedia project (a
Wikinote-taking application). The final shape of this project is still being
explored. As decisions are made, they will be recorded in
[`docs/decisions/`](docs/decisions/) and this file will be updated to reflect the
current direction.

### Relationship to Original Faragopedia

- The original project was a Wikinote-taking app with graph-based navigation.
- This project is a **full redesign**, not a fork or incremental update.
- Design learnings from the original should inform — but not constrain — this build.

---

## Architecture & Stack Decisions

| Decision           | Status               | ADR Link |
| ------------------ | -------------------- | -------- |
| Frontend framework | React (Vite)         | —        |
| Backend framework  | FastAPI              | —        |
| AI Framework       | LangChain            | —        |
| Multi-Model Support| OpenAI, Anthropic, Gemini, OpenRouter | —        |
| Database           | File-based (Wiki MD) | —        |
| File Management    | Archive/Trash System | [ADR 0001](docs/decisions/0001-file-management-and-ingestion.md) |
| Search Engine      | Client-side JSON Index| —        |
| Linting System     | AI-powered + Snapshots| —        |
| Tagging System     | Frontmatter + Shared  | —        |
| External API Auth  | Cloudflare Access (Service Token) + backend API-key middleware | [ADR 0003](docs/decisions/0003-external-api-exposure-auth.md) |
| Link View (Graph)  | Single-pass `GET /pages/graph` + hand-rolled SVG (no graph lib) | [ADR 0005](docs/decisions/0005-link-view-graph-architecture.md) |
| Source-doc links   | Key + closed lookup table, `GET /api/job/{key}` -> 302 | [ADR 0006](docs/decisions/0006-source-document-link-resolver.md) |
| Markdown rendering | react-markdown + **remark-gfm** — v9 core is CommonMark, so tables need it | - |
| Wiki data maintenance | `tools/wiki_maintenance/` scripts (external API, dry-run default) + `/.claude/skills/faragopedia-*`; notes/link/status rules | [ADR 0008](docs/decisions/0008-wiki-maintenance-toolkit.md) |
| Callsheet ingest   | `tools/callsheet_ingest/push_job.py` is the only push path; one strict table parser, reconciliation, quarantine, snapshot first; same rules in Lint (`agent/data_lint.py`) | [ADR 0009](docs/decisions/0009-callsheet-ingest-safeguards.md) |
| Hardening baseline | Rename/snapshot-id/zip checks, staged restore, CORS without credentials, API docs off, `/api/health`, nginx headers (CSP Report-Only), pinned deps + Dependabot, nightly backups pulled by gecko (restic, mirrored to yeti; `ops/backup/`) | [ADR 0012](docs/decisions/0012-tier1-hardening.md) |
| VPS access & routing | Browser API same-origin via frontend nginx `/api/` proxy (`VITE_API_BASE_URL=/api`); no public backend hostname; Portainer behind Access (Nick + service token) | [ADR 0010](docs/decisions/0010-vps-same-origin-api-and-portainer-access.md) |

---

## Coding Conventions

### General

- Use clear, descriptive names for files, functions, and variables.
- Prefer small, focused files over monolithic ones.
- Write comments for **why**, not **what**.
- **LLM Wiki Specifics**: Follow the `methodology.md` rules for `index.md`, `log.md`, and page linking.

### Git Workflow

- `main` branch is the deployment branch.
- Feature work happens on feature branches: `feature/<short-description>`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `type(scope): description` (e.g., `feat(ui): add sidebar navigation`).

### Documentation

- Architecture decisions → `docs/decisions/NNNN-title.md` (ADR format).
- Living project status → `docs/status.md`.
- Agent context → this file (`AGENTS.md`).

---

## Current Status

> See [`docs/status.md`](docs/status.md) for the detailed living status document.
| Phase        | 🟡 MVP Development / Feature Complete                  |

...

### Immediate Priorities

1. ~~Initialize project scaffold with shared AI context~~ ✅
2. ~~Implement functional LLM Wiki Prototype with Multi-Provider Support~~ ✅
3. ~~Resolve port conflicts and set up local development workflow~~ ✅
4. ~~Implement interactive [[WikiLinks]] in the frontend~~ ✅
5. ~~Fix ingestion race conditions~~ ✅
6. ~~Implement Backlinks/Linked Mentions~~ ✅
7. ~~Implement Navigation History (back/forward)~~ ✅
8. ~~Add Edit Page capability~~ ✅
9. ~~Implement Sources View (Browse/Read raw data)~~ ✅
10. ~~Implement File Management (Archive, Restore, Delete, Download)~~ ✅
11. ~~Improve Source Ingestion (Manual control, Status tracking)~~ ✅
12. ~~Refine AI maintenance logic (semantic linting)~~ → Superseded by Wiki-Concept Integration
13. ~~Execute Wiki-Concept Integration Plan~~ ✅ — All 12 tasks complete on `big-refactor`; see `docs/superpowers/plans/2026-04-15-wiki-integration-claude.md`
14. ~~Create GitHub repository and push initial commit~~ ✅
| 15. ~~Merge `big-refactor` to `main`~~ ✅
16. ~~Execute Dynamic Folders plan~~ ✅ — all 7 tasks complete; 87 tests passing
17. ~~Merge `dynamic-folders` to `main`~~ ✅
18. ~~Execute Search & Tags plan~~ ✅ — all 8 tasks complete; 111 tests passing
19. ~~Execute Bulk Actions plan (Move, Download)~~ ✅ — 7 tasks complete; 12 tests passing
20. ~~Execute Actionable Lint system (Snapshot, Bulk Fix)~~ ✅ — 7 tasks complete; verified
21. ~~Desktop UI/UX Polish (Consistency, Layout fixes)~~ ✅
22. ~~Setup Wizard (3-step wizard, LLM schema suggestion, reconfigure flow)~~ ✅ (2026-04-21)
23. **Execute Settings Section plan (Tasks 1–13)** 👈 — spec + plan in `docs/superpowers/`; backend → Claude, frontend → Gemini
24. **Execute Entity Type Templates plan (Tasks 1–5)** — pure backend; spec + plan in `docs/superpowers/`; `main` branch
25. **Add "estimated time remaining" to Lint View**
26. **Monitor snapshot storage / add auto-pruning**
27. ~~Implement Graph View~~ ✅ (2026-07-04, merged to `main` + `vps-prod-deploy` and redeployed to production 2026-09-10) — shipped as **Link View** on branch `link-view`: grouped-grid wikilink map (not force-directed), hover/focus connection curves, docked reading panel, content search. Backend `GET /pages/graph` builds the whole graph in one pass (ADR 0005). Verified with 35/35 browser checks in light + dark. Deploy also added CI (none existed before) and fixed 4 flaky backend tests — full detail in `docs/status.md` 2026-09-10 entries.
28. ~~Execute Web Search Sources plan (Faragopedia side)~~ ✅ (2026-05-19) — merged to `main`; 9 new tests passing; Phase 2 smoke test passed end-to-end. Wisecrawler-side `POST /v1/search` deployed with `BRAVE_API_KEY`. Known limitation: JS-rendered/auth-gated URLs (LinkedIn, paywalled sites) fail at Wisecrawler's analyze step — pre-existing crawler behaviour, not a web-search bug.
29. ~~Author + critically review a 10-point growth roadmap~~ ✅ (2026-07-08) — production hardening, security remediation, auth, permissions/sharing, admin dashboard, routing/frontend refactor, version history, collaboration, semantic search/RAG, UX polish. Docs live in `roadmap/` at the repo root (sibling to this folder, not inside it); verdicts and evidence in `roadmap/00-review-log.md`. All 10 approved for build; sequencing in `roadmap/00-overview.md` — **01 (production hardening) and 02 (security remediation) are next**, since prod currently runs the dev server with no auth. Hand each doc to a build session one at a time.
30. ~~Tier 1 hardening + Simon's quick wins~~ ✅ (2026-11-18, PR #24, [ADR 0012](docs/decisions/0012-tier1-hardening.md), deployed) — delivers most of roadmap 01/02: import traversal, staged snapshot restore, snapshot-id and zip checks, CORS without credentials, API docs off, `/api/health` + healthcheck, nginx security headers (CSP Report-Only), pinned deps + Dependabot (grouped minor/patch, #39), nightly backups to gecko + yeti, Uptime Kuma. UI: Home button, homepage disclaimer (draft wording), "Information correct as of". nginx 1.31 (#30) deployed the same day.
31. **Next:** enforce the CSP once the live console shows no reports; Simon's disclaimer wording; gecko dev stack (planned separately); the rest of roadmap 01/02 — rate limits on the LLM-spending endpoints (01-C / 02-H3), backend upload caps (01-E), zip member-count cap (02-M1), error-detail leakage (02-L13), prompt injection (02-L14), secrets rotation (02-H1, see AI-Wise `SECRETS-ROTATION-PLAN.md`). Then roadmap 03+ (identity: read the Cloudflare Access user rather than building local auth).



---

## Deployment

Two separate deployments as of 2026-09-09 — see
[ADR 0007](docs/decisions/0007-vps-production-deployment.md) for the full
rationale. Full operational detail (hostnames, redeploy commands, data
layout) lives in [`docs/deployment.md`](docs/deployment.md#vps-production-stack) —
this section is only the summary an agent needs to orient.

### Dev/test — none right now (NUC retired, Nov 2026)

- The office NUC that ran `main` with the Vite dev server is **retired**. Its
  Portainer (`portainer.accountantwise.uk`) and hostnames are dead.
- **Planned:** a dev stack on gecko (home server, tailnet only) built from
  `docker-compose.prod.yml`, so dev matches prod. Not built yet.
- **Until then, verify locally** before promoting: see
  [`docs/deployment.md` → Testing without a dev stack](docs/deployment.md#testing-without-a-dev-stack).

### VPS — production

- **Host:** OVHcloud VPS, London (4 vCPU / 8GB)
- **Branch:** `vps-prod-deploy` — a long-lived branch, **not** a feature
  branch. Does not track `main` automatically; merge `main` into it and
  redeploy after any merge to `main`, or the VPS serves stale code.
- **Frontend:** `frontend/Dockerfile.prod` — production `vite build`, served
  by nginx. Never edit `frontend/Dockerfile` when the intent is a
  production-facing change — that file was the (retired) NUC's dev server.
- **Networking:** Cloudflare Tunnel, zero open inbound ports beyond SSH. The
  browser reaches the API same-origin through the frontend nginx `/api/` proxy
  (ADR 0010; the old ungated backend hostname is gone). One backend hostname,
  `faragopedia-api-vps`, is for external automation and gated by `X-API-Key`
  (`/api/health` is open on it for monitoring). See ADR 0007 and 0010 before
  changing either path.
- **Promoted here only after local verification** (CI green, plus the checks in
  `docs/deployment.md` → Testing without a dev stack).

### Orchestration

- Portainer, deploying from a GitHub repository stack (no `docker-compose up`
  by hand). Redeploys are asynchronous: stack status 3 while building, 1 when
  done (about 2 minutes); check the containers were recreated.
- `docker-compose.prod.yml` (VPS) is the live definition. `docker-compose.yml`
  was the NUC's and is unused for now.
- **Backups and monitoring:** nightly pull to gecko (restic, mirrored to yeti),
  Uptime Kuma on yeti. See `docs/backup.md` and `docs/deployment.md`.

---

## Agent Collaboration Protocol

### Shared Context Model

```
AGENTS.md          ← You are here. The single source of truth.
├── docs/
│   ├── status.md       ← Living project status
│   └── decisions/      ← Architecture Decision Records (ADRs)
├── CLAUDE.md           ← Claude-specific overrides, points here
└── GEMINI.md           ← Gemini-specific overrides, points here
```

### Rules for AI Agents

1. **Read `AGENTS.md` first** at the start of every session.
2. **Check `docs/status.md`** to understand what has been done and what is in
   progress.
3. **Record decisions** — if you make an architectural or stack choice, create an
   ADR in `docs/decisions/` and update the table above.
4. **Update `docs/status.md`** at the end of any session where meaningful work
   was done.
5. **Do not duplicate context** — agent-specific files (`CLAUDE.md`, `GEMINI.md`)
   should only contain agent-specific configuration, not project context.
6. **Prefer this file** over agent-specific memory systems for anything another
   agent would need to know.
7. **Wiki content work follows `tools/wiki_maintenance/README.md`.** After ANY AI
   processing that writes wiki pages (ingest, enrichment, merges, fixes), run
   `tools/wiki_maintenance/clear_notes.py` — `notes` stays empty except values
   starting `HUMAN:` (a flag for a person to check something). Wikilinks must be
   real paths (`[[contacts/slug]]`, `[[companies/slug]]`), never raw names; never
   merge duplicate pages without a human's confirmation. See ADR 0008.
8. **The local checkout may be in use by another session.** Before committing,
   check `git branch --show-current`; stage explicit paths (never `commit -a`);
   for longer work use your own `git worktree`.
