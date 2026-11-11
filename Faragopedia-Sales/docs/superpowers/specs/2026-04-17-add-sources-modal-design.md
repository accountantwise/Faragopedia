# Add Sources Modal — Design Spec
**Date:** 2026-04-17
**Branch:** big-refactor
**Status:** Approved

---

## Overview

Replace the single-file `+` upload button in `SourcesView` with an "Add Sources" modal that supports three source types: multi-file upload, URL crawl via WiseCrawler, and paste text.

---

## Architecture & Components

### New Frontend File

**`Faragopedia-Sales/frontend/src/components/AddSourcesModal.tsx`**

Self-contained modal with three tabs. Manages its own state: active tab, queued files, URL textarea value, paste content/name, per-tab loading and error state. Accepts an `onSourceAdded` callback which the parent calls to refresh the sources list after a successful add.

### Modified Frontend File

**`Faragopedia-Sales/frontend/src/components/SourcesView.tsx`**

- Replace the `<label>` / hidden `<input type="file">` upload button with a `<button>` that sets `showModal = true`
- Render `<AddSourcesModal open={showModal} onClose={...} onSourceAdded={fetchSources} />`

### New Backend File

**`Faragopedia-Sales/backend/agent/wisecrawler.py`**

WiseCrawler API client. Three async functions:

| Function | Description |
|---|---|
| `start_crawl(url: str) -> str` | `POST /v1/crawl` → returns `job_id` |
| `poll_until_done(job_id: str) -> dict` | `GET /v1/crawl/{job_id}` every 3s until `status == "completed"` |
| `analyze_crawl(job_id: str, prompt: str) -> str` | `POST /v1/crawl/analyze` → returns `analysis` string |

Reads `WISECRAWLER_BASE_URL` (required) and `WISECRAWLER_API_KEY` (optional) from environment. Sends `Authorization: Bearer {WISECRAWLER_API_KEY}` header when key is set.

Default analyze prompt:
> "Extract and summarize all key information, facts, names, and details from this website. Be thorough."

### Modified Backend File

**`Faragopedia-Sales/backend/api/routes.py`**

Two new endpoints (see Data Flow section).

---

## Modal UI

Three tabs inside a centred overlay modal opened by the `+` button:

### Tab 1 — Files
- Drag-and-drop zone + "Browse files" button
- Supports multiple files selected at once
- Selected files shown as a dismissible list below the drop zone
- Submit uploads each file to existing `POST /upload?ingest=false` (one request per file, sequentially)

### Tab 2 — URL
- Multi-line textarea: one URL per line
- Helper text: *"Each URL will be crawled and analyzed. Sources appear in the list when ready (~30–60s)."*
- "Start Crawl" button calls `POST /scrape-urls`
- Modal closes immediately with a `202 Accepted` — sources appear asynchronously via the existing 5s metadata poll

### Tab 3 — Paste Text
- Optional name input (auto-generated filename if blank)
- Large textarea for content
- Empty content rejected client-side before submit
- "Save as Source" calls `POST /paste`
- Modal closes on success

---

## Data Flow

### File Upload
1. User selects/drops files → queued in modal UI
2. On submit: `POST /upload?ingest=false` called once per file
3. Modal closes; `onSourceAdded` triggers source list refresh

### URL Crawl
1. User enters URLs (one per line) → clicks "Start Crawl"
2. `POST /scrape-urls` with `{ urls: ["https://..."] }`
3. Backend returns `202 Accepted` immediately
4. One `BackgroundTask` per URL:
   - `start_crawl(url)` → `job_id`
   - `poll_until_done(job_id)` (polls every 3s)
   - `analyze_crawl(job_id, prompt)` → `analysis`
   - Save analysis to `sources/{sanitized-domain}-{YYYYMMDD-HHMMSS}.md`
5. Modal closes; frontend's existing 5s metadata poll discovers new source when ready

**Filename format:** domain with dots/slashes replaced by hyphens + timestamp.
Example: `https://accountantwise.uk/about` → `accountantwise-uk-20260417-143022.md`

### Paste Text
1. User fills optional name + textarea → "Save as Source"
2. `POST /paste` with `{ content: string, name?: string }`
3. Backend saves to `sources/{name or "paste-{YYYYMMDD-HHMMSS}"}.txt`
4. Returns `{ filename }` → modal closes, source list refreshes

---

## New API Endpoints

### `POST /scrape-urls`
```
Request:  { "urls": ["https://..."] }
Response: 202 { "message": "Started N crawl job(s)" }
Errors:   503 if WISECRAWLER_BASE_URL is not configured
          422 if urls list is empty
```

### `POST /paste`
```
Request:  { "content": "string", "name": "optional string" }
Response: 200 { "filename": "paste-20260417-143022.txt" }
Errors:   422 if content is empty
```

---

## Configuration

Two new environment variables in `.env`:

| Variable | Required | Description |
|---|---|---|
| `WISECRAWLER_BASE_URL` | Yes | Base URL of WiseCrawler instance, e.g. `https://wisecrawler.accountantwise.uk` |
| `WISECRAWLER_API_KEY` | No | Bearer token for WiseCrawler auth (maps to WiseCrawler's `API_KEY`) |

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| File upload fails | Error toast shown; other files in batch continue |
| Crawl job fails (WiseCrawler error) | Background task logs error; no source file created; user sees nothing (acceptable for v1) |
| WiseCrawler unreachable | `POST /scrape-urls` returns `503` with descriptive message |
| `WISECRAWLER_BASE_URL` not set | `POST /scrape-urls` returns `503` |
| Paste with empty content | Rejected client-side before request |
| URL textarea empty | "Start Crawl" button disabled |

---

## Testing

### `backend/tests/test_sources.py` (extend)
- `POST /paste` happy path — file created with correct content
- `POST /paste` with custom name — filename respected
- `POST /paste` with empty content — 422 returned
- `POST /scrape-urls` with empty list — 422 returned
- `POST /scrape-urls` with `WISECRAWLER_BASE_URL` unset — 503 returned

### `backend/tests/test_wisecrawler.py` (new)
- `start_crawl` sends correct request, returns `job_id`
- `poll_until_done` retries until status is `completed`
- `analyze_crawl` sends `crawl_id` and prompt, returns analysis string
- Non-200 responses raise appropriate exceptions

---

## Out of Scope (v1)

- Web search (finding URLs via a search query)
- Per-job progress UI for in-flight crawl jobs
- Crawl failure notifications to the user
- Saving raw crawl markdown alongside the analysis
