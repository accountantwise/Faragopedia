# Faragopedia — 10-Point Roadmap

> Authored 2026-07-07 after a full review of the codebase (`Faragopedia-Sales`), the live app at `faragopedia.ai-wise.uk`, a backend security audit, a frontend-architecture review, and competitive research against Outline, BookStack, Wiki.js, Notion, Confluence, Docmost, Slite, AppFlowy, AnyType and Obsidian.
>
> **Critically re-reviewed 2026-07-07**: every code anchor was re-verified against the codebase, every library recommendation checked for 2026 maintenance status, and each doc upgraded or confirmed. All 10 docs are **APPROVED for build**. Per-doc verdicts, corrected claims, and evidence live in [`00-review-log.md`](00-review-log.md).
>
> Each point has a standalone implementation doc in this folder, written to be handed to a Sonnet-based build session. They follow the project's existing conventions (TDD, ADRs in `docs/decisions/` — 0001–0005 exist, next is 0006 — feature branches, status updates in `docs/status.md`).

## Where Faragopedia is today

A capable single-user, file-based, LLM-powered wiki: entity-folder markdown pages with `[[wikilinks]]`, AI ingestion of source docs, AI chat, AI "lint", keyword search + tags, a Link View graph, workspaces, snapshots, import/export, a setup wizard, and a settings drawer (theme/reconfigure/export). Strong foundations.

**The gaps that matter most:** it is deployed to the public internet **with no authentication** and **serving the Vite dev server as production**; it has several exploitable backend vulnerabilities; and it lacks the multi-user, governance, and modern-UX features every comparable 2026 product treats as table stakes.

## The 10 points

| # | Point | Priority | Effort | Why |
|---|-------|----------|--------|-----|
| [01](01-production-hardening.md) | Production deployment & security hardening | **P0** | M | Prod runs the dev server; CORS is `*`+credentials; no rate limits protect open, paid LLM endpoints; no upload caps. |
| [02](02-security-remediation.md) | Security remediation (traversal, zip-slip, secrets, prompt injection) | **P0** | M | 15-finding audit: zip-slip on import/restore, path traversal on import rename, secrets bakeable into the image. Exploitable today. |
| [03](03-authentication-user-management.md) | Authentication & user management | **P0** | L | No login at all. The foundation for 04/05/07/08. Local accounts + OIDC + sessions. |
| [04](04-roles-permissions-sharing.md) | Roles, permissions & workspace/page sharing | **P1** | L | "Sharing" is currently just workspace-switching with no access control. Roles + members + public read-only share links. |
| [05](05-admin-dashboard.md) | Admin dashboard (users, audit logs, **LLM cost**, backups) | **P1** | M–L | No admin surface; the operator is blind to who-did-what and to token spend. |
| [06](06-routing-frontend-architecture.md) | URL routing & frontend architecture refactor | **P1** | L | No router → no deep-links/shareable URLs; `App.tsx`/`WikiView.tsx` are monoliths; 77 raw fetches across 12 files, no tests. |
| [07](07-version-history-diffing.md) | Version history & diffing | **P1** | M | No per-page history/diff/restore; adds optimistic-concurrency edit safety for multi-user. |
| [08](08-collaboration-comments-notifications.md) | Comments, @mentions, notifications & activity feed | **P2** | M–L | No in-app discussion; teams leak context to Slack. |
| [09](09-ai-semantic-search-grounded-qa.md) | Semantic search, grounded Q&A & autolinking | **P1** | M–L | Search is keyword-only; chat spends an LLM relevance pass over the full page catalog every question, uncited (lint is the true whole-wiki prompt). Semantic + RAG with citations is the core differentiator. |
| [10](10-ux-polish-command-palette-accessibility.md) | UX polish: Cmd+K, onboarding, feedback, accessibility | **P2** | M | 20+ unlabeled icon buttons, zero modal focus management, patchy loading feedback, no command palette. Adoption polish. |

## Note on the items you named

- **User Management / Authentication** → 03.
- **Admin dashboard** → 05.
- **Workspace sharing** → 04 (workspace membership + page-level ACLs + public share links).
- **Settings page** → a settings **drawer already exists** (`SettingsDrawer.tsx`: theme, reconfigure, export/import). Rather than rebuild it, the roadmap **elevates** it: settings gets a proper home under the Admin dashboard (05), and the UX doc (10) adds the palette/shortcuts/onboarding around it. If you want a dedicated full-page Settings surface specifically, it's a small carve-out from 05 + 10 — flag it and it can become its own doc.

## Recommended sequencing

Dependencies drive the order more than raw priority:

1. **Security first, together:** **01 + 02** (ship before anything else touches prod).
2. **Identity foundation:** **03** (auth) → unblocks everything multi-user.
3. **In parallel with/after 03:** **06** (routing) — low product risk, unblocks share links and deep-links; land its `credentials: 'include'` with 03.
4. **Team layer:** **04** (permissions/sharing, needs 03+06; its step 0 — replacing the server-global "active workspace" with per-request context — is the hidden prerequisite for all multi-user work) → **05** (admin/audit/cost, needs 03/04).
5. **Content trust & collaboration:** **07** (history) → **08** (comments/notifications, reuses 05's audit infra).
6. **Differentiator:** **09** (semantic search/RAG) — schedule after 05 so its embedding/query spend is visible; independent enough to start earlier if desired.
7. **Continuous:** **10** (UX polish) — the accessibility/feedback quick wins can ride along in every other branch; the command palette wants 06 and is best after 09.

```
01 ─┐
02 ─┴─▶ 03 ─┬─▶ 04 ─▶ 05 ─┬─▶ 08
      06 ───┘   07 ───────┘
                09  (after 05 for cost visibility)
                10  (quick wins throughout; palette after 06+09)
```

## Cross-cutting technical decisions introduced

- **A SQLite datastore** (via SQLModel, single file in a mounted volume) is introduced in 03 and reused by 04/05/07/08 for users, sessions, permissions, audit, LLM usage, revisions, comments, and notifications. Wiki **content stays file-based markdown** — the DB holds only relational metadata. This keeps the "simple to self-host, no external services" ethos.
- **A local vector store** (`sqlite-vec` recommended) is introduced in 09 for embeddings, same ethos.
- Each doc calls out where it needs an **ADR** (`docs/decisions/`) and lists concrete files/routes to touch, a TDD plan, and acceptance criteria.

## How these docs are meant to be used

Hand any one file to a build session. Each is self-contained: problem, current-state code anchors, design, a step-by-step TDD plan, acceptance criteria, and explicit out-of-scope boundaries pointing at sibling docs. Update `docs/status.md` and `AGENTS.md` as items land, per the existing agent protocol.
