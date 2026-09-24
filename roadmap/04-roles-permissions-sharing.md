# 04 — Roles, Permissions & Workspace/Page Sharing

| Field | Value |
| --- | --- |
| Priority | P1 — the payoff of auth; enables real multi-user collaboration |
| Effort | L (3–5 sessions) — effort raised at review: per-request workspace context is a prerequisite (see Design, step 0) |
| Dependencies | 03 (needs `User` + session), 06 helps (routing for share links) |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/permissions` |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — added the load-bearing discovery that the backend's "active workspace" is **server-global module state** (multi-user sharing is impossible until workspace resolution becomes per-request); share tokens now hashed at rest; explicit `can()` action map; anchors verified. See `00-review-log.md`. |

## Problem

Today "sharing" is workspace-switching with no access control — every visitor sees everything. Mainstream KBs (BookStack cascading Shelf→Book→Chapter→Page permissions, Confluence/Notion object ACLs, AppFlowy Can View/Can Edit, public read-only links) offer at least: three roles, workspace membership, and public share links. This is what turns Faragopedia from a single-user tool into a team tool.

**Verified blocker found in review:** `backend/agent/workspace_manager.py` keeps the active workspace in **module-level globals** (`_active_workspace_id`, `_active_dirs`); every path helper (`get_wiki_dir()` etc.) reads that global, and "switching workspace" mutates it **for the whole server**. Two users in different workspaces would flip each other's context on every switch. Per-workspace permissions are meaningless until this is fixed — hence step 0 below.

## Design

### Step 0 (prerequisite): per-request workspace context

Replace the global active-workspace state with request-scoped resolution:

- The frontend sends the target workspace explicitly — an `X-Workspace-Id` header set by the API client (06) or a `workspace_id` path/query param on workspace-scoped routes.
- A FastAPI dependency `get_workspace(request, user) -> Workspace` validates the id against the registry (`workspaces/registry.json` — ids are slugs, verified) **and** the user's membership, and yields a `WorkspaceContext` object carrying the per-workspace dirs (what `get_wiki_dir()` etc. currently compute from globals).
- `WikiManager` instances become per-workspace (a small cache keyed by workspace id) instead of one global bound to the mutable active dirs. The existing per-manager `asyncio.Lock` write serialization carries over per workspace.
- The old "active workspace" becomes a **client-side** preference (localStorage / user prefs), not server state. Keep `set_active_workspace` only for single-user backward compat during the transition, then remove.

This is the bulk of the added effort and touches most routes — do it as its own PR with behavior-preserving tests before any permission logic.

### Roles (global + per-workspace)

- **Global role** (on `User`, from 03): `admin` (manages users, all workspaces), `member`, `service`.
- **Per-workspace membership** — new table (03's SQLite, via its migration runner):
```
workspace_members (id, workspace_id, user_id, role)   # role: owner | editor | viewer
```
`workspace_id` is the registry slug. An admin sees all; a member sees only workspaces they belong to. On migration, grant the first admin `owner` on all existing workspaces.

### Permission resolution

A single `can(user, action, workspace_id, page_path=None) -> bool` function is the chokepoint. Explicit action map (so build sessions don't have to guess):

| Action | viewer | editor | owner | global admin |
|---|---|---|---|---|
| `read` (pages, sources, graph, search, chat*) | ✓ | ✓ | ✓ | ✓ |
| `write` (save/move/rename pages, upload, ingest, lint/fix, scrape) | | ✓ | ✓ | ✓ |
| `delete` (pages, sources, snapshots restore/delete) | | ✓ | ✓ | ✓ |
| `manage_members` / share links | | | ✓ | ✓ |
| `workspace admin` (rename/duplicate/archive/delete workspace, reconfigure) | | | ✓ | ✓ |

\* chat reads content but **spends LLM tokens** — default it to `editor`+ with a config flag (`CHAT_MIN_ROLE=viewer|editor`) so an operator can open it to viewers deliberately.

Start workspace-level (simplest, matches current data model), with an **optional per-page override** table for later:
```
page_permissions (id, workspace_id, page_path, role_required)   # phase 2 — sparse overrides
```
BookStack-style inheritance: page override wins if present, else workspace role. Keep phase 1 to workspace-level to ship faster.

### Public share links

- New table:
```
share_links (id, workspace_id, page_path NULL, token_hash, scope, expires_at, created_by, revoked_at)
# scope: 'page' | 'workspace'; page_path null => whole workspace (read-only)
```
- Tokens are `secrets.token_urlsafe(32)`, **stored hashed** (sha256, same pattern as 03's sessions) — a DB leak must not leak live share URLs. Lookup is by hash; revoked/expired/unknown all return the same 404.
- `GET /api/share/{token}` resolves to a **read-only** context that bypasses auth but is scoped to an explicit **allowlist of read endpoints** — page content, the page list of the shared scope, and rendered backlinks. Nothing else: no LLM routes, no sources, no graph, no search (add scoped search later if wanted). Enumerate the allowlist in code as a distinct router so scope creep is visible in review.
- Frontend: a "Share" button on a page → generates a link (`/share/{token}` route, needs 06) → read-only viewer (reuse the WikiView render path in a locked mode).
- Rate-limited via 01's limiter (token guessing).

### Workspace membership UI

- Workspace switcher (`WorkspaceSwitcher.tsx`, verified: switch/rename/duplicate/archive/delete with a type-name confirm modal on delete — confirmations exist, **authorization doesn't**) gains a "Members" panel (owner/admin only): invite existing users, set role, remove. Invitations reuse 03's flow, scoped to a workspace.

### Backend

- Guard every route through `can(...)`. 03 already added `Depends(get_current_user)` at router level; this layers `get_workspace` + the action check per route group.
- New routes: `GET/POST/DELETE /api/workspaces/{id}/members`, `POST /api/share`, `GET /api/share` (list mine), `DELETE /api/share/{id}`, public `GET /api/share/{token}` (+ its allowlisted sub-fetches).

### Frontend

- `PermissionsContext` derived from `me` + active workspace membership: exposes `canWrite`, `canManage`, `canAdmin`. Hide/disable edit, delete, move, ingest, folder, and reconfigure controls when `!canWrite`.
- Read-only share viewer route + "Share" affordance on pages and the workspace.

## Implementation plan (TDD)

1. **Step 0: per-request workspace context** — `get_workspace` dependency, per-workspace `WikiManager` cache, remove global mutation. Tests: two clients addressing different workspaces in interleaved requests never cross-contaminate; existing suite green (fixtures pass an explicit workspace).
2. **Membership model + `can()`** — tables via migration, resolution function + action map. Tests: owner can write, viewer cannot, admin bypasses, non-member → 403, chat gated by `CHAT_MIN_ROLE`.
3. **Wire `can()` into all write/delete/LLM routes.** Update route tests to seed memberships.
4. **Members API + UI** in `WorkspaceSwitcher`. Tests: invite/list/change-role/remove; only owner/admin may manage.
5. **Share-link model + create/list/revoke API.** Tests: create page link, token resolves read-only, revoked/expired/unknown all → identical 404, DB holds hashes only.
6. **Public read-only viewer** (needs 06 routing `/share/:token`). Verify no write/LLM/source route is reachable with a share token (test the allowlist exhaustively: iterate all 72 routes, assert only the allowlisted ones answer).
7. **Frontend permission gating** — hide/disable controls by capability. Verify with webapp-testing as viewer vs editor vs owner.
8. **(Phase 2, optional) page-level overrides** — `page_permissions` + inheritance in `can()`.

## Acceptance criteria

- Two users in different workspaces can work simultaneously without affecting each other's context.
- A viewer sees pages but every edit/delete/ingest control is hidden/disabled and the API returns 403 if forced.
- An owner can invite a user as editor; that user can edit only that workspace.
- A page share link opens a read-only view for a logged-out visitor; a scripted sweep of all other endpoints with that token returns 401/403/404.
- Revoking a share link makes it 404 immediately.
- Admin can access all workspaces.

## Out of scope

- The audit trail of permission changes → **05**.
- Auth itself → **03**.
