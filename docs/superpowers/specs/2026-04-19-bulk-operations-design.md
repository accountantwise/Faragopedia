# Bulk Operations Design

**Date:** 2026-04-19  
**Branch:** search-and-tags  
**Scope:** Bulk ingest for sources; bulk archive for sources and wiki pages

---

## Overview

Allow users to select multiple sources or wiki pages and act on them in a single operation — either triggering ingestion for multiple sources at once, or archiving multiple items at once.

---

## Backend

### New Endpoints

**`POST /sources/bulk-ingest`**
- Body: `{ "filenames": ["a.pdf", "b.txt"] }`
- Loops over each filename, triggers the existing background ingest task for each
- Returns `202 Accepted` immediately
- Each source's status is tracked in `.metadata.json` and surfaced via the existing `GET /sources/metadata` poll — no new status infrastructure needed

**`DELETE /sources/bulk`**
- Body: `{ "filenames": ["a.pdf", "b.txt"] }`
- Calls `archive_source()` for each filename
- Returns `{ "archived": ["a.pdf", "b.txt"], "errors": [] }`

**`DELETE /pages/bulk`**
- Body: `{ "paths": ["clients/acme.md", "contacts/bob.md"] }`
- Calls `archive_page()` for each path
- Returns `{ "archived": ["clients/acme.md"], "errors": ["contacts/bob.md"] }`

All three endpoints are thin wrappers over existing per-item logic. The existing `_write_lock` in `wiki_manager.py` already serializes LLM writes for ingest.

---

## Selection UI

### Hover-Reveal Checkboxes

- Each item in the sources list and wiki page tree shows a checkbox on the left **on hover**
- Checking any one item enters **selection mode**: all checkboxes become persistently visible
- Clicking a checked item's checkbox deselects it
- Clicking the item row itself (not the checkbox) navigates to that item normally, even in selection mode
- In the wiki tree, checkboxes appear on **leaf nodes (pages) only** — not on folder/entity-type headers

### Selection Mode Toolbar

When 1+ items are selected, a floating action bar appears at the bottom of the list panel:

- `X selected` count
- **Select All** button — selects all visible items
- **Ingest Selected** button (sources only)
- **Archive Selected** button (both sources and wiki)

### Exiting Selection Mode

- Click the X in the action bar
- Press Escape
- Deselect all items manually

---

## Ingest Status & Feedback

### Per-Source Status Persistence

- The existing `Pending`/`Ingested` badge + 5-second poll on `GET /sources/metadata` handles all status display
- Bulk ingest simply flips multiple sources to `Pending` simultaneously; the poll detects each completion
- **The poll must be lifted from `SourcesView` to `App.tsx`** so status persists when the user navigates away and returns

### Completion Toasts

- When a source flips from `Pending` → `Ingested`, a toast fires: *"[filename] ingested successfully."*
- One toast per source, firing as each finishes — not a single combined toast
- This gives the user incremental visibility into a long-running bulk job

---

## Archive Confirmation

- Before archiving, a confirmation modal appears: *"Archive N items? This can be undone from the Archive view."*
- Buttons: **Cancel** / **Archive**
- If any items fail to archive, a follow-up error toast lists the failures
- Successful archives remove the items from the list immediately

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/api/routes.py` | Add 3 new bulk endpoints |
| `backend/agent/wiki_manager.py` | Expose `archive_source` / `archive_page` for batch use if needed |
| `frontend/src/App.tsx` | Lift metadata poll up from SourcesView; pass status + toast trigger down |
| `frontend/src/components/SourcesView.tsx` | Add checkbox state, selection toolbar, bulk ingest/archive handlers |
| `frontend/src/components/WikiView.tsx` | Add checkbox state on page leaves, selection toolbar, bulk archive handler |
| `frontend/src/components/ConfirmDialog.tsx` | New reusable confirmation modal component |

---

## Out of Scope

- Bulk restore from archive
- Bulk tagging
- Bulk permanent delete
- Job queue / progress bar (per-source poll is sufficient)
