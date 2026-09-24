# 07 — Version History & Diffing

| Field | Value |
| --- | --- |
| Priority | P1 — table stakes; also the safety net for multi-user editing |
| Effort | M (2–3 sessions) |
| Dependencies | 03 (for author attribution); complements existing snapshot system |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/version-history` |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — write-path anchors verified; revision capture extended to lint-fix/ingest/delete paths the original plan missed; optimistic concurrency switched from revision-id to content-hash (covers never-edited pages); no-op saves excluded. See `00-review-log.md`. |

## Problem

Every mainstream KB keeps full per-page edit history with author, timestamp, restore, and a diff view (Wiki.js commits to Git; Confluence/Notion/BookStack store revisions). Faragopedia has **workspace-wide snapshots** (zip of the whole wiki — created automatically before lint-fix, verified wiki_manager.py:976; list/restore/delete routes at routes.py:518-546) but **no per-page history and no diff UI**. Users can't see what changed, who changed it, or revert a single page. Once multiple people edit (04), this becomes essential for trust and conflict recovery.

## Design

### Storage: per-page revision log

The wiki is file-based markdown; keep that as the working copy and add an **append-only revision store** rather than adopting full Git (simpler to reason about in the container, no libgit2 dependency; Git remains a reasonable alternative if the team prefers — note the tradeoff in an ADR).

**Recommended: revision files + index.** On every content-changing write, store the *previous* content at `revisions/<workspace>/<entity>/<slug>/<timestamp>-<userid>.md` and append a row to a `page_revisions` table (03's SQLite): `(id, workspace_id, page_path, ts, user_id, action, byte_size, content_hash, revision_file)`. Cheap, greppable, easy to prune. (Git-backed was considered; rejected for v1.)

**Verified write paths to hook — all inside `WikiManager`, all already serialized by `self._write_lock` (wiki_manager.py:188):**
- `save_page_content` (:1548) — user edits. **Skip no-op saves** (compare `content_hash` first; a save with unchanged content must not mint a revision). Note this method also fires an LLM call (`_suggest_tags`) after the write — put the revision capture inside the locked block, before that.
- `move_page` (:1188) / `rename_page` (:1215) — record as `move`/`rename` actions (content unchanged; store the old path in the row).
- Ingest page writes (the locked block around :728) — attributed to the requesting user (or the service user for Trigger.dev ingests).
- **Lint-fix bulk writes** (`apply_lint_fixes`) — the original plan missed these; attribute to the invoking user with `action='lint_fix'`.
- **Delete/archive** — capture the final content as a `delete` revision so deletion is recoverable per-page, not only via snapshots.

Add a `revisions` volume (or put it under the 03 `data/` volume) in `docker-compose.yml`. Retention policy (keep last N per page or last M days; configurable) to bound disk — reuse the "monitor snapshot storage" concern already noted in status.md.

### Diffing

- Backend computes diffs on demand with Python `difflib` between any two revisions (or a revision and current). Return structured hunks the frontend can render side-by-side or inline.
- Frontend renders from the structured hunks — hand-rolled is fine and dependency-free; if a library is preferred, `react-diff-view` (lighter) or `react-diff-viewer-continued` (both verified maintained/React-18-compatible). Respect dark mode.

### Attribution

Every write route has `user` (from 03) — record `user_id` on each revision; AI/automation writes attribute to the service/system user. First time a page is written post-deploy with no prior revision, seed a baseline revision from the pre-write content.

### Concurrency / conflict safety (lightweight)

This doc also delivers the **minimum edit-safety** the competitive research flagged (real-time CRDT is out of scope): optimistic concurrency via **content hash** rather than revision id — pages that have never been edited post-deploy have no revision row, but they always have a hash. `GET` page responses include `content_hash`; `PUT` (save) accepts `base_hash`; if the current file's hash ≠ `base_hash`, return **409 Conflict** with both versions so the frontend shows a merge/diff dialog instead of silently overwriting. This is the pragmatic alternative to edit-locking or CRDTs.

### Backend routes

- `GET /api/pages/{path}/revisions` — list (ts, author, action, size).
- `GET /api/pages/{path}/revisions/{rev_id}` — fetch a revision's content.
- `GET /api/pages/{path}/diff?from=REV&to=REV|current` — structured diff.
- `POST /api/pages/{path}/revisions/{rev_id}/restore` — restore (which itself creates a new revision).
- Page save route gains optional `base_hash` → 409 on mismatch.

### Frontend

- A **History** panel on a page (icon in the page toolbar): revision list with author + action + relative time; click a revision → diff vs current; "Restore this version" (confirm dialog).
- Conflict dialog on 409: "This page changed since you started editing" → show diff → keep-mine / take-theirs / open-both.
- Attribution line on pages: "Last edited by X, <time>".

## Implementation plan (TDD)

1. **`page_revisions` table + revision-file writer**; hook into `save_page_content`, ingest write, move, rename, lint-fix, delete. Tests: an edit creates a revision file + row with correct author/action; a no-op save creates nothing; move/rename/lint-fix/delete recorded.
2. **List + fetch revision routes.** Tests: revisions listed newest-first; fetch returns exact historical content.
3. **Diff endpoint** (`difflib` → structured hunks). Tests: known before/after → expected hunks; identical → empty.
4. **Restore route** (creates a new revision, doesn't destroy history). Test: restore brings back old content and is itself logged.
5. **Optimistic concurrency**: `base_hash` on save; 409 on stale. Tests: stale write → 409 with both versions; fresh write → 200; page with no revision history still conflicts correctly.
6. **Retention/pruning** job + config. Test: over-limit revisions pruned oldest-first; baseline revision never pruned while page exists.
7. **Frontend History panel + diff viewer + conflict dialog**; dark-mode aware. Verify with webapp-testing: edit twice as two users → history shows both, diff correct, restore works, concurrent edit → conflict dialog.

## Acceptance criteria

- Editing a page creates a timestamped, attributed revision; saving unchanged content does not.
- A lint-fix run and a page delete both leave recoverable revisions.
- History panel lists revisions; selecting one shows a correct diff vs current.
- Restore returns the page to a prior version and records the restore.
- Two overlapping edits produce a 409 + conflict dialog, not a silent overwrite — including on pages never edited before.
- Disk stays bounded by the retention policy.

## Out of scope

- Real-time collaborative editing / live cursors (CRDT) — deliberately deferred; optimistic concurrency is the chosen safety model.
- Cross-page/workspace-wide history views — per-page is enough for v1 (snapshots still cover whole-wiki rollback).
