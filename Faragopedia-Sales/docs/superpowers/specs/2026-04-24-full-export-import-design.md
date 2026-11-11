# Wiki Export & Import — Design Spec

**Date:** 2026-04-24  
**Status:** Approved

## Overview

Replace the existing partial bundle export (5 files) with a full-fidelity export/import system offering two modes:

- **Full** — complete migration of all wiki data, sources, archive, snapshots, and schema to a new server; wizard is bypassed entirely
- **Template** — schema and folder structure only; on import the user is dropped into the wizard at the schema review step (pre-populated from the bundle) so they can finalize entity types before the wiki is initialized

Environment-specific settings (API keys, model config, port config) are excluded from all bundles.

---

## Bundle Contents by Mode

### Full Bundle (`faragopedia-full-YYYYMMDD-HHmmss.zip`)

```
manifest.json              ← version, type: "full", exported_at
schema/
  SCHEMA.md
  SCHEMA_TEMPLATE.md
  company_profile.md
  wiki_config.json
wiki/
  index.md
  log.md
  search-index.json
  {entity_type}/
    _type.yaml
    {page}.md
sources/
  .metadata.json           ← ingestion status (ingested, ingested_at, tags)
  {uploaded files}
archive/
  pages/
    {deleted pages}.md
  sources/
    {deleted sources}
snapshots/
  {snapshot-id}.zip
```

### Template Bundle (`faragopedia-template-YYYYMMDD-HHmmss.zip`)

```
manifest.json              ← version, type: "template", exported_at
schema/
  SCHEMA.md
  SCHEMA_TEMPLATE.md
  company_profile.md
  wiki_config.json         ← used to read entity types; not written to disk on import
wiki/
  {entity_type}/
    _type.yaml             ← folder structure only, no page files
```

Note: `wiki_config.json` is included so the import handler can read entity type definitions without parsing YAML files, but it is not written to disk. The wizard writes its own `wiki_config.json` after the user confirms.

Template imports seed the schema files and entity type folders on disk, then hand control to the setup wizard at the schema review step. The wizard is pre-populated with the imported entity types and company profile. The user can modify them, then confirms to complete setup — at which point `wiki_config.json` is written and fresh `index.md` and `log.md` are generated (same as a normal first-time setup). No sources, archive, snapshots, or wiki page content is included.

### manifest.json

```json
{
  "version": 1,
  "type": "full",
  "exported_at": "2026-04-24T10:00:00Z",
  "app_version": "1.0.0"
}
```

The `type` field (`"full"` or `"template"`) tells the import handler which restoration path to take. The `version` field enables forward compatibility checks.

### Ingestion Status Preservation (Full only)

`sources/.metadata.json` maps each filename to its ingestion state:

```json
{
  "document.pdf": {
    "ingested": true,
    "ingested_at": "2026-04-20 14:32:01",
    "tags": ["client", "contract"]
  }
}
```

Including this file ensures sources show as "already ingested" on the new server — the user will not be prompted to re-ingest them. If the file is missing from an older bundle, sources default to `ingested: false` (safe fallback).

---

## Export

### Backend

**Two endpoints** (or a single endpoint with a `?type=full|template` query param — prefer two explicit endpoints for clarity):

- `GET /api/export/bundle/full` — Full export
- `GET /api/export/bundle/template` — Template export

Both:
1. Generate `manifest.json` in memory with correct `type`, timestamp, and app version
2. Stream a ZIP to the response (do not buffer in memory)
3. Set `Content-Disposition` with the appropriate filename

**Full** walks `schema/`, `wiki/`, `sources/`, `archive/`, `snapshots/` recursively.  
**Template** walks `schema/` fully and `wiki/` but only includes `_type.yaml` files (skips `.md` pages and `search-index.json`).

Excluded from all bundles: `.env`, API keys, port config.

### Frontend

In `SettingsDrawer.tsx`, add an **Export** section with two buttons:

- **Export Full** — "Download everything: all wiki pages, sources, archive, and snapshots. Use this to migrate to a new server."
- **Export Template** — "Download your schema and folder structure only, with no content. Use this to share your setup as a starting point for others."

Each button triggers a direct download (anchor click to the respective endpoint). No confirmation dialog needed (non-destructive).

---

## Import

### Backend

**Single endpoint:** `POST /api/export/import` (replaces existing two-step flow)

Steps:
1. Receive ZIP as multipart upload, stream to a temp file on disk
2. Open ZIP, validate `manifest.json` exists, `version` is compatible, `type` is `"full"` or `"template"`
3. Unpack all contents to a temporary staging directory
4. Validate staging has required structure (`schema/wiki_config.json` must be present)
5. Clear existing target directories:
   - **Full:** clear `wiki/`, `sources/`, `archive/`, `snapshots/`, `schema/`
   - **Template:** clear `wiki/`, `schema/` only (leave sources/archive/snapshots untouched)
6. Move staged contents to final locations
   - **Template:** do NOT write `wiki_config.json` — it is written later by `POST /api/setup/complete` after the user confirms in the wizard
7. Clean up temp staging directory
8. **Full only:** reinitialize `WikiManager`, rebuild search index via `_rebuild_search_index()`
9. Return:
   - Full: `{"status": "ok", "type": "full"}`
   - Template: `{"status": "ok", "type": "template", "folders": [...entity type names...], "company_profile": "...content..."}`

The existing `POST /api/export/import/finalize` endpoint is deprecated and removed.

### Setup-Complete Behavior by Type

| | **Full Import** | **Template Import** |
|---|---|---|
| `wiki_config.json` written | Immediately (from bundle) | After user confirms in wizard |
| Wizard shown after import | No — wiki is ready immediately | Yes — lands on schema review step, pre-populated |
| Wiki content created | Restored from bundle | Generated fresh after wizard confirms |

**Full import:** `wiki_config.json` is restored from the bundle, so `GET /api/setup/status` returns setup-complete and the wizard is skipped on next load.

**Template import:** The backend writes schema files and `_type.yaml` files to disk but does NOT write `wiki_config.json`. It returns `{"status": "ok", "type": "template", "folders": [...], "company_profile": "..."}` — the frontend uses this payload to jump the wizard directly to the schema review screen, pre-populated. The user confirms (or edits), then `POST /api/setup/complete` fires as normal, writing `wiki_config.json` and initializing the wiki.

### Frontend

**Two entry points, same upload flow:**

1. **Settings Drawer** (`SettingsDrawer.tsx`) — Import section alongside Export. Single "Import" button opens a `.zip` file picker, uploads to `/api/export/import`, shows a spinner. On success, reloads the app (Full) or transitions to wizard schema review (Template).

2. **Setup Wizard** (`SetupWizard.tsx`) — "Already have a Faragopedia export? Import it instead." visible on the wizard's first screen. Same file picker + upload flow. Full import reloads; Template import jumps to schema review within the wizard.

Both share the same upload helper function. The response `type` field determines which post-import path to take.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Missing `manifest.json` | Return 400; no files written |
| Incompatible `manifest.version` | Return 400 with version mismatch message; no files written |
| Unknown `manifest.type` | Return 400; no files written |
| Missing `schema/wiki_config.json` | Return 400; no files written |
| Failure during unpack/move | Clean up temp dir; existing data untouched; return 500 |
| Missing `sources/.metadata.json` (Full import) | Import proceeds; sources default to `ingested: false` |
| Large bundle | Streamed to disk, not held in memory; no size limit imposed |

---

## Files Changed

### Backend
- `api/export_routes.py` — Add `GET /bundle/full` and `GET /bundle/template`; replace two-step import with single atomic `POST /import`
- `wiki_manager.py` — Add `reinitialize()` method to reload state after import; add method to generate fresh `index.md` and `log.md` for template imports

### Frontend
- `src/components/SettingsDrawer.tsx` — Add Export (Full + Template buttons with descriptions) and Import sections
- `src/components/SetupWizard.tsx` — Add "Import existing export" entry point on first screen

### Removed
- `POST /api/export/import/finalize` — Removed; single-step import replaces the two-step flow
- `GET /api/export/bundle` — Replaced by `/bundle/full` and `/bundle/template`

---

## Out of Scope

- Merging two Faragopedia instances (import is a full replace)
- Incremental/differential exports
- Scheduled or automated exports
- Authentication / access control on export endpoints
- Environment config (`.env`, API keys, model settings) — user re-enters these on new server
