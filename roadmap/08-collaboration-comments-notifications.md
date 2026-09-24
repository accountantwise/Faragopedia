# 08 — Collaboration: Comments, @Mentions, Notifications & Activity Feed

| Field | Value |
| --- | --- |
| Priority | P2 — team-velocity layer; do after auth/permissions/history land |
| Effort | M–L (3–4 sessions) |
| Dependencies | 03 (users), 04 (permissions), 05 (audit infra reused) |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/collaboration` |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — confirmed zero existing comment/notification code; SSE verified workable through the Cloudflare tunnel (promoted from "optional" to recommended, polling as fallback); `OperationToastContext` reuse corrected (its API is ingest/crawl-specific and needs a generic variant); notification fan-out debounced. See `00-review-log.md`. |

## Problem

There's no way to discuss content in-app (verified: no comment/notification/mention code anywhere; the only "Mentions" string is the backlinks header) — teams fall back to Slack, losing context. Mainstream KBs ship threaded comments with @mentions (Confluence inline + page comments, Notion/Slite threads, Wiki.js comments module) plus notifications and activity feeds (MediaWiki watchlist/pings, XWiki activity streams). This turns Faragopedia from a document store into a collaboration space.

## Design

### Comments

New tables (03's SQLite, via its migration runner):
```
comments (id, workspace_id, page_path, user_id, parent_id NULL, body, anchor NULL, created_at, updated_at, resolved_at, resolved_by NULL)
```
- **Page-level threads** first (parent_id enables replies). **Inline/anchored comments** (`anchor` = a text-range/heading reference) are a documented phase 2 — anchoring to markdown ranges is fiddly and breaks on edits, so ship page-level threads first.
- Resolve/reopen a thread (`resolved_at`). Edit/delete own comments; admins moderate.
- Permissions via 04's `can()`: anyone with `read` on the page can comment (configurable); share-link viewers cannot (the share router's endpoint allowlist simply doesn't include comment routes — verify in 04's allowlist test).
- **Page rename/move gotcha:** comments key on `page_path` — 07's move/rename hooks must also update `comments.page_path` (and `subscriptions.page_path`), or threads orphan. Add to the move/rename transaction.

### @Mentions

- Parse a picker-inserted stable token `@[Name](user:id)` in comment bodies (don't regex bare `@username` — display names collide and rename). The composer autocompletes from workspace members (04).
- On mention, create a notification for the mentioned user (only if they can read the page) and subscribe them to the thread.

### Notifications

```
notifications (id, user_id, type, actor_id, workspace_id, page_path, comment_id NULL, created_at, read_at NULL)
# type: mention | reply | page_updated | comment_added | invited | role_changed
subscriptions (id, user_id, workspace_id, page_path, kind)   # kind: page | workspace ; "watch"
```
- Users auto-subscribe to pages they create/edit/comment on; can watch/unwatch a page or workspace.
- **Debounce `page_updated`:** at most one notification per (subscriber, page, editor) per ~15 minutes — otherwise a ten-save editing session spams ten rows. Implement as "skip insert if an unread `page_updated` for the same tuple exists".
- Never notify the actor about their own action.
- Delivery: **in-app** (bell icon + dropdown + unread count). Transport: **SSE recommended** (`GET /api/notifications/stream`) — verified to pass cleanly through cloudflared with no special config; keep a 60s polling fallback in the client for when the stream drops (reconnect with backoff). If the build session wants to ship faster, polling-only first is acceptable — SSE is an enhancement, not a foundation.
- **Email digests** are phase 2 (needs SMTP config — env `SMTP_*`); wire the hook but gate on config.

### Activity feed

- Reuse the `audit_events` table from **05** (don't build a parallel log). A per-workspace **Activity** view renders human-readable events ("X edited Acme", "Y commented on Beta"). Filter by user/type/date. Comment actions therefore also emit audit events (`comment.create/resolve/delete`).

### Backend routes

- `GET/POST /api/pages/{path}/comments`, `PATCH/DELETE /api/comments/{id}`, `POST /api/comments/{id}/resolve`.
- `GET /api/notifications`, `POST /api/notifications/read` (bulk or per-id), `GET /api/notifications/stream` (SSE).
- `GET/POST/DELETE /api/subscriptions`.
- `GET /api/workspaces/{id}/activity` (reads `audit_events`).

### Frontend

- **Comments panel** on a page (toolbar toggle, like History from 07): threaded list, composer with @mention autocomplete (workspace members from 04), resolve/reopen, relative timestamps, dark-mode aware.
- **Notification bell** in the top bar: unread badge, dropdown list, mark-read, click → deep-link to the page/comment (needs 06 routing).
- **Activity view**: a workspace-level feed (nav entry or a tab).
- Toasts for new mentions while the app is open. **Note (verified):** `OperationToastContext` exposes only ingest/crawl-specific operations (`startIngest`/`completeCrawl`/…) — add a generic `notify(message, kind)` to it (or a sibling context) rather than shoehorning mentions into the ingest shape.

## Implementation plan (TDD)

1. **Comments model + CRUD routes** (page-level threads, replies, resolve). Tests: post/reply/list ordered, resolve toggles, only author/admin edits/deletes, permission-gated, share-token cannot reach comment routes.
2. **@mention token parsing + notification creation.** Tests: mentioning a user creates a `mention` notification; mentioned user without read access gets nothing; malformed token ignored.
3. **Notifications model + list/read routes + auto-subscribe rules + debounce.** Tests: reply to a watched thread notifies subscribers, not the actor; ten rapid edits → one unread `page_updated`; mark-read works.
4. **Subscriptions** watch/unwatch. Tests: watch a page → `page_updated` on someone else's edit; unwatch stops it.
5. **Move/rename path sync** — comments/subscriptions follow the page. Test: rename a commented page → thread still attached.
6. **Activity feed route** over `audit_events` (+ comment events emitted). Test: recent events returned, filterable.
7. **SSE stream + client reconnect/polling fallback.** Test: event pushed on notification insert (TestClient streaming); client falls back cleanly when stream unavailable.
8. **Frontend**: comments panel + @mention autocomplete; notification bell + dropdown; activity view; generic toast. Verify with webapp-testing: comment → mention teammate → they see a badge → click → lands on the comment.
9. **(Phase 2, gated)** email digests via SMTP; inline/anchored comments.

## Acceptance criteria

- A user can start a thread on a page, reply, and resolve it.
- @mentioning a teammate creates a notification they see in the bell (live via SSE or within one poll cycle) with an unread badge.
- Editing a watched page notifies its subscribers (but not the editor), at most once per burst.
- Renaming a page keeps its comment threads.
- The Activity view shows a readable, filterable event stream per workspace including comment activity.
- Comment access respects page permissions; share-link viewers can't comment.

## Out of scope

- Real-time collaborative editing (07 covers conflict safety; live cursors are out).
- Email/Slack delivery beyond the gated SMTP hook (Slack webhooks live in a future integrations effort; the audit/event model here is the foundation for it).
