---
title: Bulk Move & Bulk Download
date: 2026-04-19
status: approved
---

# Bulk Move & Bulk Download

Extends the existing bulk operations feature with two new actions: moving wiki pages between entity-type subdirectories (with automatic wikilink rewriting), and downloading selected pages or sources as a ZIP archive.

---

## Scope

- **Bulk Move**: Wiki pages only. Moves selected pages from their current entity-type subdirectory to a chosen destination subdirectory, then rewrites all wikilinks across the wiki that referenced the old paths.
- **Bulk Download**: Both wiki pages and sources. Downloads selected items as a single ZIP file assembled server-side.

---

## Backend

### `POST /pages/bulk-move`

**Request body:**
```json
{ "paths": ["prospects/acme.md", "prospects/beta.md"], "destination": "clients" }
```

**Behavior:**
1. Validate `destination` is one of the 5 known entity types: `clients`, `prospects`, `contacts`, `photographers`, `productions`.
2. Validate all paths pass existing path-safety checks (no traversal).
3. For each path, rename the file to `<destination>/<filename>`. If a file already exists at the destination, return an error for that item and skip it.
4. After all moves complete, scan every `.md` file in the wiki directory for wikilinks matching any of the old paths. Rewrite in-place (read → replace → write). Wikilink format: `[[subdir/page-name]]`.
5. Return summary.

**Response:**
```json
{
  "moved": ["prospects/acme.md → clients/acme.md"],
  "errors": [{ "path": "prospects/beta.md", "error": "destination already exists" }],
  "links_rewritten": { "contacts/john.md": 2, "productions/2026-01-acme-shoot.md": 1 }
}
```

**Status codes:** `200` (partial success included in body), `400` (invalid destination or body), `500` (unexpected error).

---

### `POST /pages/bulk-download`

**Request body:**
```json
{ "paths": ["clients/acme.md", "productions/2026-01-acme-shoot.md"] }
```

**Behavior:**
1. Validate all paths pass path-safety checks.
2. For any path that doesn't exist on disk, return `404` immediately (fail fast — no partial ZIPs).
3. Read each file and assemble a ZIP in memory using Python's built-in `zipfile`, preserving subdirectory structure inside the archive.
4. Stream response with headers: `Content-Type: application/zip`, `Content-Disposition: attachment; filename="pages-export.zip"`.

---

### `POST /sources/bulk-download`

**Request body:**
```json
{ "filenames": ["brief-2026-01.pdf", "notes.docx"] }
```

**Behavior:** Same as `/pages/bulk-download` but reads from the sources directory. Files are placed flat in the ZIP (no subdirectory structure, since sources have none). Returns `404` fast if any file is missing. Filename: `sources-export.zip`.

---

## Frontend

### WikiView changes

**Toolbar (existing):** Add "Move" and "Download" buttons alongside the existing "Archive" button. Buttons appear when `selectedPages.size > 0`.

**Move flow:**
1. User clicks "Move" → `MoveDialog` opens.
2. `MoveDialog` shows the destination picker (radio buttons for the 5 entity types; the current entity type of the first selected page is pre-selected but all options are enabled).
3. User selects destination and clicks "Move X pages" → `POST /pages/bulk-move`.
4. On success: toast message `"Moved X pages to [destination]. Y wikilinks updated."` Selection clears, wiki list refreshes.
5. On partial error: toast lists failed items.

**Download flow:**
1. User clicks "Download" → fetch `POST /pages/bulk-download` with `blob()` response.
2. Programmatically create `<a href=objectURL download="pages-export.zip">` and click it.
3. No confirmation dialog (non-destructive).
4. On error: toast with message.

### SourcesView changes

**Toolbar:** Add "Download" button alongside "Ingest" and "Archive".

**Download flow:** Same programmatic download pattern, calls `POST /sources/bulk-download`, filename `sources-export.zip`.

### New component: `MoveDialog.tsx`

```
MoveDialog
  props: { selectedCount: number, onConfirm: (destination: string) => void, onClose: () => void }
  state: destination (string, one of 5 entity types)
  UI: modal overlay (reuse existing modal styles), radio group, "Move X pages" confirm button, Cancel button
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Destination file already exists (move) | Skip that file, include in `errors`, continue others |
| Path not found (download) | Return `404` immediately, show error toast |
| Invalid destination type (move) | Return `400` |
| Partial move success | `200` with errors listed in body, toast shows both moved and failed counts |

---

## Testing

- Extend `smoke_test_bulk.py` with Playwright tests:
  - Move: select pages, open MoveDialog, pick destination, confirm, verify pages appear under new entity type, verify old paths gone
  - Move wikilink rewriting: verify a known wikilink in another page is updated post-move
  - Download (pages): click Download, verify a `.zip` file is received by the browser
  - Download (sources): same for sources toolbar
- Backend unit tests for `bulk_move` path-safety, missing-file errors, wikilink rewrite regex

---

## Out of Scope

- Moving sources between folders (sources have no subdirectory hierarchy)
- Merging pages during move (if destination file exists, it's an error, not a merge)
- Conflict resolution UI for move errors
- Download progress indicator (in-memory ZIP is fast enough at this scale)
