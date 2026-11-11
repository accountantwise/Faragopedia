# Search & Tags — Design Spec

**Date:** 2026-04-18
**Status:** Approved
**Branch:** dynamic-folders

---

## Overview

Add keyword search (per-view, client-side) and a free-form tag system (shared vocabulary across wiki pages and sources) to Faragopedia-Sales. Tags serve three purposes simultaneously: navigation/filtering, search enhancement, and AI context.

---

## Decisions

| Question | Decision |
|---|---|
| Search scope | Per-view (WikiView searches pages; SourcesView searches sources) |
| Search mechanism | Keyword/full-text, client-side against a JSON index — no AI involved |
| Tag assignment | AI suggests on write; user can accept, dismiss, add, or remove |
| Tag scope | Shared vocabulary across wiki pages and sources |
| Tag type | Free-form — vocabulary grows organically from use |
| Tag purposes | Navigation/filtering + search enhancement + AI context |

---

## Data Model

### Search Index — `wiki/search-index.json`

Maintained by `WikiManager`. Rebuilt on every page write or source ingest. If the file is missing or stale on startup, `WikiManager.__init__` triggers a full rebuild.

```json
{
  "generated_at": "2026-04-18T10:00:00Z",
  "pages": [
    {
      "path": "clients/acme-corp.md",
      "title": "Acme Corp",
      "entity_type": "clients",
      "tags": ["wedding", "VIP"],
      "frontmatter": { "tier": "A", "status": "active" },
      "content_preview": "First 500 characters of page body (stripped of markdown syntax)."
    }
  ],
  "sources": [
    {
      "filename": "acme-brief-2024.pdf",
      "display_name": "Acme Corp Brief",
      "tags": ["brief", "wedding"],
      "metadata": { "ingested": true, "upload_date": "2026-03-01" }
    }
  ]
}
```

### Tags Storage

- **Wiki pages** — `tags:` field in YAML frontmatter (list of strings)
- **Sources** — `tags` key in the existing per-source metadata JSON
- **Shared vocabulary** — derived at read-time by collecting all unique tags from both; no separate registry file

---

## Backend

### New API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/search/index` | Returns full `search-index.json` for client-side search |
| `GET` | `/tags` | Returns all unique tags with counts (pages + sources combined) |
| `PATCH` | `/pages/{path}/tags` | Replace tag list on a wiki page |
| `PATCH` | `/sources/{filename}/tags` | Replace tag list on a source file |
| `POST` | `/search/rebuild` | Force full index rebuild (manual recovery) |

### WikiManager Changes

**New private methods:**

- `_rebuild_index_entry(path: str)` — updates a single page's entry in `search-index.json` after any write; if the file doesn't exist yet, writes a fresh index
- `_rebuild_full_index()` — walks all pages and sources, rebuilds the entire index from scratch; called on startup if index is missing/stale, and via `POST /search/rebuild`
- `_suggest_tags(content: str, entity_type: str) -> list[str]` — single LLM call returning 3–5 tag suggestions based on page/source content and entity type

**Hooks into existing methods** (add index rebuild + tag suggestion after each write):

- `create_page` — suggest tags, write to frontmatter, rebuild index entry
- `update_page` — re-suggest tags on every update (suggestions only prompt the user for tags not already present on the item), rebuild index entry
- `delete_page` — remove entry from index
- `archive_page` / `restore_page` — remove/restore index entry
- `ingest_source` — suggest tags, write to source metadata, rebuild index entry (sources section)

**Sync contract:** the index is always written *after* the Markdown/metadata file. A future write to any page triggers a full rebuild if the index is detected as stale (missing entries). The frontend can also force a rebuild via `POST /search/rebuild`.

---

## Frontend

### Search UI (WikiView + SourcesView)

Both views follow the same pattern — scoped to their own data:

- **Search bar** spans the full view width, positioned above the content area
- Filters live as the user types (no submit required); results update on every keystroke with ~150ms debounce
- **Results panel** appears below the search bar when a query is active, showing:
  - Page/source title
  - Entity type label (e.g., `clients`, `source`)
  - Tag chips for that result
  - Content preview with keyword matches highlighted
- When the query is cleared, the view returns to its normal state (entity tree for wiki, file list for sources)

### Tag UI

**Inline on each page/source:**
- Tags displayed as blue chips below the page title / file name
- `+ add tag` control opens a small text input with autocomplete from the existing tag vocabulary
- Click a tag chip to remove it (with confirmation)

**Filter row (visible when searching):**
- Appears above search results showing all tags present in the current result set
- Active filter tags show `×` to remove; inactive tags can be clicked to add as filter
- Multiple tag filters are ANDed (result must have all selected tags)

**AI tag suggestions:**
- After a page is saved or a source is ingested, if the AI suggested tags that aren't already on the item, a small inline prompt appears: `✓ AI suggested: "X" — Accept · Dismiss`
- Accepting appends the tag to the item's tag list and triggers an index rebuild
- Dismissing hides the suggestion for that item permanently (stored in local state, not persisted server-side)

---

## Error Handling

- If `/search/index` fails to load, the search bar shows a disabled state with "Search unavailable" tooltip; the rest of the view functions normally
- If a tag write (`PATCH`) fails, the UI reverts the optimistic update and shows an error toast
- Index rebuild failures are logged server-side; the stale index continues to serve until a successful rebuild

---

## Out of Scope

- Global cross-view search (one bar searching pages + sources simultaneously) — could be added later
- Semantic/AI search — the existing chat `query()` flow already covers this
- Tag hierarchies or parent/child relationships
- Tag colors or icons
- Full page content search (only previews are indexed) — can be added later via a backend grep endpoint

---

## Testing

- Unit: `_rebuild_index_entry`, `_rebuild_full_index`, `_suggest_tags` on WikiManager
- Unit: `PATCH /pages/{path}/tags` and `PATCH /sources/{filename}/tags` endpoints
- Integration: ingest a source → verify tags appear in index + `/tags` response
- Integration: delete a page → verify its entry is removed from index
- Frontend: search filters results correctly client-side; tag filter row appears/disappears; AI suggestion accept/dismiss works
