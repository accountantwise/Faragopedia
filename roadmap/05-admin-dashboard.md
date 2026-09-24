# 05 — Admin Dashboard (Users, Audit Logs, Usage/Cost Analytics, Backups)

| Field | Value |
| --- | --- |
| Priority | P1 — governance + cost visibility; the operator's control panel |
| Effort | M–L (2–4 sessions) |
| Dependencies | 03 (users), 04 (roles); benefits from 01 (rate-limit IP helper reused) |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/admin-dashboard` |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — LLM call-site names verified exact (all five exist); added the critical `with_structured_output` token-usage gotcha (`include_raw=True`) the original plan would have tripped on; confirmed zero usage tracking exists today; price table made config-driven with unknown-model fallback. See `00-review-log.md`. |

## Problem

There is no admin surface. Confluence/BookStack/Notion all give admins a user roster, audit logs (who did what, when), usage/analytics, and backup status. For a **self-hosted, LLM-backed** app the killer addition is **LLM cost/usage tracking** — the owner pays per token and currently flies blind (verified: no `usage_metadata`/token-count code exists anywhere in the backend). This dashboard is where the settings drawer's ad-hoc controls (reconfigure, export/import — `SettingsDrawer.tsx`, verified) get a proper home.

## Design

### Audit log

New table (03's SQLite, via its migration runner):
```
audit_events (id, ts, user_id, workspace_id, action, target_type, target_path, metadata_json, ip)
```
Emit from a tiny helper `record_event(user, action, ...)` called in write/delete/move/ingest/lint/permission/auth routes. Keep it cheap (one insert; never let an audit failure fail the request — log and continue). Actions: `page.create/edit/delete/move/rename`, `source.upload/ingest/delete`, `lint.run/fix`, `auth.login/logout/login_failed`, `member.add/remove/role_change`, `share.create/revoke`, `workspace.create/delete`. Include **failed logins** — that's the security-relevant row. IP comes from 01's `get_client_ip()` helper (trusted-proxy-aware). Add a retention setting (e.g. 365 days, pruned by the same job as 07's revisions).

### LLM usage & cost tracking

New table:
```
llm_usage (id, ts, user_id, workspace_id, operation, provider, model, input_tokens, output_tokens, cache_read_tokens, cost_estimate)
```
Instrument the **five verified `WikiManager` call sites** (names and lines confirmed): `_suggest_tags` (wiki_manager.py:434), `_run_ingest_llm` (:635), `_run_query_llm` (:759), `_run_lint_llm` (:851), `_run_fix_llm` (:951). Note `query()` also makes a **relevance-pass call** (~:813) before `_run_query_llm` — instrument that too, or chat costs will read ~half of reality.

**Implementation gotcha (this is the part that stalls a build session):** three of these sites use `.with_structured_output(PydanticModel)` (verified :661, :858, :961), which returns the parsed object and **discards the response metadata that carries token usage**. Two working options:
1. `.with_structured_output(Model, include_raw=True)` — returns `{"raw": AIMessage, "parsed": Model, "parsing_error": ...}`; read `raw.usage_metadata` (`input_tokens`/`output_tokens`, plus `input_token_details.cache_read` when Anthropic prompt caching is active — the codebase enables `cache_control` for ingest, verified :649-656).
2. LangChain's `get_usage_metadata_callback()` context manager around the call.
Prefer (1) — explicit, per-call, testable. For plain `.ainvoke()` sites, `response.usage_metadata` is available directly.

Maintain a small **config-driven price table** (`backend/config/model_prices.json`, editable without code changes): `{provider, model_prefix, input_per_mtok, output_per_mtok, cache_read_per_mtok}`. Unknown model → record tokens with `cost_estimate = NULL` and surface "unpriced" in the UI rather than silently guessing. This directly answers the still-open status.md question of whether Haiku-4.5 ingest holds up vs cost.

### Analytics (derived, not stored)

Compute on request from the above + wiki scan: total pages/sources per workspace, pages created/edited over time, most-active users, ingest volume, **cost per day/week and per operation/model**. Log searches to a lightweight counter if top-searches are wanted (optional).

### Backups

- `POST /api/admin/backup` produces a full bundle (reuse `export_routes` full-bundle logic) covering wiki + sources + archive + snapshots + schema **+ the SQLite DB** (use SQLite's `VACUUM INTO` or the backup API for a consistent copy — don't zip a live DB file mid-write), streamed as a dated zip.
- Show last-backup time; document (in `docs/deployment.md`) a cron/Portainer approach for scheduled off-site copies. Optionally add a scheduled internal job later.

### Backend

- `backend/api/admin_routes.py` under `/api/admin`, all gated `require_role('admin')`:
  - `GET /users`, `PATCH /users/{id}` (role, activate/deactivate), `DELETE /users/{id}`, `POST /users/invite`
  - `GET /audit` (filter by user/action/date, paginated)
  - `GET /usage` (LLM cost/usage, grouped by day/model/operation)
  - `GET /analytics` (workspace/content/activity stats)
  - `POST /backup`, `GET /backup/status`
  - MFA management (if deferred from 03): enroll/reset per user

### Frontend

- New `AdminDashboard.tsx` (admin-only nav entry, hidden otherwise), tabbed:
  - **Users** — roster table, role dropdown, invite, deactivate.
  - **Audit Log** — filterable, paginated table.
  - **Usage & Cost** — charts (read the `dataviz` skill before building any chart): cost over time, tokens by model, spend by operation, top users; "unpriced" models shown distinctly.
  - **Analytics** — pages/sources counts, activity sparklines, top pages.
  - **Backups** — trigger backup, last-run, restore instructions.
- Fold **Settings** (theme, reconfigure, export/import from `SettingsDrawer`) into a Settings tab or keep the drawer and cross-link. (This satisfies the "settings page" ask — the drawer exists; the dashboard elevates it.)

## Implementation plan (TDD)

1. **Audit table + `record_event` helper** (fail-open); call from a representative set of routes incl. failed login. Tests: an edit inserts an event with correct fields; an audit-write failure doesn't fail the request.
2. **`llm_usage` table + instrumentation** at the six call sites (five methods + the relevance pass) using `include_raw=True`; price table + `cost_estimate`. Tests: a mocked LLM response with known `usage_metadata` records exact token counts + cost; unknown model → NULL cost; cache-read tokens captured when present.
3. **Admin routes** (users/audit/usage/analytics/backup), all `require_role('admin')`. Tests: non-admin → 403; filters work; pagination works.
4. **AdminDashboard.tsx** with the five tabs; charts per `dataviz` skill; admin-only nav gating.
5. **Backup endpoint** reusing export logic incl. a consistent DB copy. Test: bundle contains expected members incl. the DB.
6. **Docs**: backup/restore runbook in `docs/deployment.md`; ADR for the audit/usage design (next free number after 03/04's — check `docs/decisions/`, 0001–0005 existed pre-roadmap).
7. **Verify**: log in as admin → see real audit rows from your own actions and real cost numbers after an ingest/chat (chat should show **two** usage rows or a combined row covering both calls).

## Acceptance criteria

- Admin can list users and change a user's role; the change appears in the audit log.
- Every write/LLM action produces an audit event; failed logins are logged.
- After a chat and an ingest, the Usage tab shows nonzero token counts (chat includes the relevance pass) and a cost estimate broken down by model/operation; unpriced models are visible, not dropped.
- Non-admin cannot reach `/api/admin/*` (403) or see the nav entry.
- `POST /api/admin/backup` returns a zip containing wiki + a consistent DB copy.

## Out of scope

- Real-time streaming metrics — periodic/refresh-on-load is fine.
- External billing integration — internal estimate only.
