# Bulk Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bulk ingest (sources) and bulk archive (sources + wiki pages) with hover-reveal checkboxes, a floating selection toolbar, confirmation dialogs, and per-source completion toasts.

**Architecture:** Three new backend endpoints fan out to existing per-item logic. The metadata poll moves from `SourcesView` to `App.tsx` so status persists across navigation. Selection state lives locally in each view; a shared `ConfirmDialog` component handles confirmation.

**Tech Stack:** FastAPI (Python), React + TypeScript, Tailwind CSS, Lucide React icons, Pydantic

---

## ⚡ Handoff Status (2026-04-19)

**Claude completed:** Tasks 1 and 2 (all backend work). Commits: `a185c12`, `89c5a9f`.

**Gemini to complete:** Tasks 3–6 (all frontend work). See task details below.

**Claude returns for:** Tasks 7 and 8 (smoke test + full test suite). Do NOT run these — hand back to Claude when Tasks 3–6 are done.

### What Gemini MUST NOT touch
- `backend/` — all backend work is done and tested. Do not modify any backend files.
- `backend/tests/` — 5 tests are passing. Do not modify.

### What Gemini implements (Tasks 3–6)
- `frontend/src/components/ConfirmDialog.tsx` — create new file (Task 3)
- `frontend/src/App.tsx` — lift metadata poll, add toast state (Task 4)
- `frontend/src/components/SourcesView.tsx` — remove internal metadata poll, accept prop, add bulk selection UI (Tasks 4 + 5)
- `frontend/src/components/WikiView.tsx` — add bulk selection UI for wiki pages (Task 6)

### Key facts Gemini needs
- API base URL is imported from `frontend/src/config.ts` as `API_BASE`
- The app router prefix is `/api` — all fetch calls use `${API_BASE}/sources/bulk-ingest`, `${API_BASE}/sources/bulk` (DELETE), `${API_BASE}/pages/bulk` (DELETE)
- `SourcesView` currently owns a `metadata` state + `fetchMetadata` function + a `setInterval(fetchMetadata, 5000)` inside a `useEffect` — all of this moves to `App.tsx` in Task 4
- After Task 4, `SourcesView` receives `sourcesMetadata` as a prop instead of owning it internally
- The `filteredSources` variable in `SourcesView` is the correct list to use for "select all" — it's already computed in the component
- `pageTree` in `WikiView` is `Record<string, string[]>` — `Object.values(pageTree).flat()` gives all page paths for "select all"
- `fetchPages` is the function to call after bulk archiving wiki pages to refresh the list
- `fetchSources` is the function to call after bulk archiving sources to refresh the list
- Verify TypeScript compiles (`npx tsc --noEmit`) after each task before committing

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/api/routes.py` | Modify | Add 3 bulk endpoints |
| `frontend/src/App.tsx` | Modify | Lift metadata poll up; pass `metadata` + `onIngestComplete` toast callback to `SourcesView` |
| `frontend/src/components/SourcesView.tsx` | Modify | Receive metadata as prop; add selection state + bulk toolbar + bulk ingest/archive handlers |
| `frontend/src/components/WikiView.tsx` | Modify | Add selection state on page leaves + bulk archive handler |
| `frontend/src/components/ConfirmDialog.tsx` | Create | Reusable modal: message + Cancel/Confirm buttons |
| `backend/tests/test_bulk_operations.py` | Create | API-level tests for the 3 new endpoints |

---

## Task 1: Backend — `POST /sources/bulk-ingest`

**Files:**
- Modify: `Faragopedia-Sales/backend/api/routes.py`
- Create: `Faragopedia-Sales/backend/tests/test_bulk_operations.py`

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_bulk_operations.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app


@pytest.mark.asyncio
async def test_bulk_ingest_returns_202():
    with patch("api.routes.wiki_manager") as mock_wm, \
         patch("api.routes.asyncio.create_task") as mock_task, \
         patch("api.routes.os.path.exists", return_value=True):
        mock_wm.ingest_source = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/sources/bulk-ingest", json={"filenames": ["a.pdf", "b.txt"]})
    assert resp.status_code == 202
    assert resp.json()["queued"] == ["a.pdf", "b.txt"]


@pytest.mark.asyncio
async def test_bulk_ingest_skips_missing_files():
    def exists_side_effect(path):
        return "a.pdf" in path

    with patch("api.routes.wiki_manager") as mock_wm, \
         patch("api.routes.asyncio.create_task"), \
         patch("api.routes.os.path.exists", side_effect=exists_side_effect), \
         patch("api.routes.os.path.join", side_effect=lambda *a: "/".join(a)):
        mock_wm.ingest_source = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/sources/bulk-ingest", json={"filenames": ["a.pdf", "missing.txt"]})
    assert resp.status_code == 202
    data = resp.json()
    assert "a.pdf" in data["queued"]
    assert "missing.txt" in data["skipped"]
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_bulk_operations.py::test_bulk_ingest_returns_202 -v
```
Expected: FAIL — endpoint does not exist yet.

- [ ] **Step 3: Add `BulkFilenames` model and `POST /sources/bulk-ingest` endpoint**

In `backend/api/routes.py`, after the existing `TagsUpdate` model near line 15:

```python
class BulkFilenames(BaseModel):
    filenames: List[str]

class BulkPaths(BaseModel):
    paths: List[str]
```

After the existing `POST /sources/{filename}/ingest` endpoint (around line 196):

```python
@router.post("/sources/bulk-ingest")
async def bulk_ingest_sources(payload: BulkFilenames):
    queued = []
    skipped = []
    for filename in payload.filenames:
        safe_name = os.path.basename(filename)
        if os.path.exists(os.path.join(SOURCES_DIR, safe_name)):
            asyncio.create_task(wiki_manager.ingest_source(safe_name))
            queued.append(safe_name)
        else:
            skipped.append(safe_name)
    return JSONResponse(status_code=202, content={"queued": queued, "skipped": skipped})
```

Also add `JSONResponse` to the FastAPI imports at the top of `routes.py`:

```python
from fastapi.responses import FileResponse, JSONResponse
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_bulk_operations.py::test_bulk_ingest_returns_202 tests/test_bulk_operations.py::test_bulk_ingest_skips_missing_files -v
```
Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add Faragopedia-Sales/backend/api/routes.py Faragopedia-Sales/backend/tests/test_bulk_operations.py
git commit -m "feat: add POST /sources/bulk-ingest endpoint"
```

---

## Task 2: Backend — `DELETE /sources/bulk` and `DELETE /pages/bulk`

**Files:**
- Modify: `Faragopedia-Sales/backend/api/routes.py`
- Modify: `Faragopedia-Sales/backend/tests/test_bulk_operations.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_bulk_operations.py`:

```python
@pytest.mark.asyncio
async def test_bulk_archive_sources():
    with patch("api.routes.wiki_manager") as mock_wm:
        mock_wm.archive_source = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.request(
                "DELETE", "/sources/bulk",
                json={"filenames": ["a.pdf", "b.txt"]}
            )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["archived"]) == {"a.pdf", "b.txt"}
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_bulk_archive_sources_partial_failure():
    async def archive_side_effect(name):
        if name == "bad.pdf":
            raise FileNotFoundError("not found")

    with patch("api.routes.wiki_manager") as mock_wm:
        mock_wm.archive_source = AsyncMock(side_effect=archive_side_effect)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.request(
                "DELETE", "/sources/bulk",
                json={"filenames": ["good.pdf", "bad.pdf"]}
            )
    assert resp.status_code == 200
    data = resp.json()
    assert "good.pdf" in data["archived"]
    assert "bad.pdf" in data["errors"]


@pytest.mark.asyncio
async def test_bulk_archive_pages():
    with patch("api.routes.wiki_manager") as mock_wm, \
         patch("api.routes.safe_wiki_filename", side_effect=lambda p: p):
        mock_wm.archive_page = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.request(
                "DELETE", "/pages/bulk",
                json={"paths": ["clients/acme.md", "contacts/bob.md"]}
            )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["archived"]) == {"clients/acme.md", "contacts/bob.md"}
    assert data["errors"] == []
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_bulk_operations.py::test_bulk_archive_sources tests/test_bulk_operations.py::test_bulk_archive_pages -v
```
Expected: FAIL — endpoints don't exist yet.

- [ ] **Step 3: Add `DELETE /sources/bulk` and `DELETE /pages/bulk` endpoints**

In `backend/api/routes.py`, after the `bulk_ingest_sources` endpoint added in Task 1:

```python
@router.delete("/sources/bulk")
async def bulk_archive_sources(payload: BulkFilenames):
    archived = []
    errors = []
    for filename in payload.filenames:
        safe_name = os.path.basename(filename)
        try:
            await wiki_manager.archive_source(safe_name)
            archived.append(safe_name)
        except Exception:
            errors.append(safe_name)
    return {"archived": archived, "errors": errors}


@router.delete("/pages/bulk")
async def bulk_archive_pages(payload: BulkPaths):
    archived = []
    errors = []
    for path in payload.paths:
        try:
            safe_path = safe_wiki_filename(path)
            await wiki_manager.archive_page(safe_path)
            archived.append(path)
        except Exception:
            errors.append(path)
    return {"archived": archived, "errors": errors}
```

**Important:** These new `DELETE /sources/bulk` and `DELETE /pages/bulk` routes must be placed **before** the existing `DELETE /sources/{filename}` and `DELETE /pages/{path:path}` routes in the file. FastAPI matches routes in order — if the catch-all path route comes first, it will swallow `/bulk`.

- [ ] **Step 4: Run all bulk tests**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_bulk_operations.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add Faragopedia-Sales/backend/api/routes.py Faragopedia-Sales/backend/tests/test_bulk_operations.py
git commit -m "feat: add DELETE /sources/bulk and DELETE /pages/bulk endpoints"
```

---

## Task 3: Frontend — `ConfirmDialog` component

**Files:**
- Create: `Faragopedia-Sales/frontend/src/components/ConfirmDialog.tsx`

- [x] **Step 1: Create the component**

```tsx
import React from 'react';

type Props = {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: string;
};

const ConfirmDialog: React.FC<Props> = ({ message, onConfirm, onCancel, confirmLabel = 'Confirm' }) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
    <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full mx-4">
      <p className="text-gray-800 text-base mb-6">{message}</p>
      <div className="flex justify-end gap-3">
        <button
          onClick={onCancel}
          className="px-4 py-2 rounded-lg text-gray-600 hover:bg-gray-100 transition-colors text-sm font-medium"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className="px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors text-sm font-medium"
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  </div>
);

export default ConfirmDialog;
```

- [x] **Step 2: Verify it compiles**

```bash
cd Faragopedia-Sales/frontend
npx tsc --noEmit
```
Expected: No errors.

- [x] **Step 3: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/ConfirmDialog.tsx
git commit -m "feat: add reusable ConfirmDialog component"
```

---

## Task 4: Frontend — Lift metadata poll to `App.tsx`

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/App.tsx`
- Modify: `Faragopedia-Sales/frontend/src/components/SourcesView.tsx`

The goal: metadata polling currently lives inside `SourcesView`. Moving it to `App` means the status persists when the user navigates away and back. We'll also wire up toast notifications for completed ingestions.

- [x] **Step 1: Add metadata state and poll to `App.tsx`**

In `App.tsx`, add these imports at the top:

```tsx
import { useEffect, useState, useRef, useCallback } from 'react';
// (replace the existing React import line)
import React, { useState, useRef, useEffect, useCallback } from 'react';
```

Add these state declarations inside `App` (after existing state):

```tsx
type SourceMetadata = Record<string, { ingested: boolean; ingested_at: string | null; tags: string[] }>;

const [sourcesMetadata, setSourcesMetadata] = useState<SourceMetadata>({});
const prevMetadataRef = useRef<SourceMetadata>({});
const [toasts, setToasts] = useState<{ id: number; message: string }[]>([]);
```

Add the poll effect inside `App` (after existing effects):

```tsx
const addToast = useCallback((message: string) => {
  const id = Date.now();
  setToasts(prev => [...prev, { id, message }]);
  setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
}, []);

useEffect(() => {
  const fetchMetadata = async () => {
    try {
      const res = await fetch(`${API_BASE}/sources/metadata`);
      if (!res.ok) return;
      const data: SourceMetadata = await res.json();
      // Fire toast for any source that just became ingested
      const prev = prevMetadataRef.current;
      Object.entries(data).forEach(([filename, meta]) => {
        if (meta.ingested && prev[filename] && !prev[filename].ingested) {
          addToast(`"${filename}" ingested successfully.`);
        }
      });
      prevMetadataRef.current = data;
      setSourcesMetadata(data);
    } catch {}
  };
  fetchMetadata();
  const interval = setInterval(fetchMetadata, 5000);
  return () => clearInterval(interval);
}, [addToast]);
```

Add toast rendering at the bottom of the `App` return JSX, just before the closing `</div>`:

```tsx
{/* Global ingestion toasts */}
<div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none">
  {toasts.map(t => (
    <div key={t.id} className="bg-gray-900 text-white text-sm px-4 py-3 rounded-xl shadow-lg animate-fade-in">
      {t.message}
    </div>
  ))}
</div>
```

Pass `sourcesMetadata` to `SourcesView`:

```tsx
case 'Sources':
  return <SourcesView sourcesMetadata={sourcesMetadata} />;
```

- [x] **Step 2: Update `SourcesView` to accept metadata as prop**

At the top of `SourcesView.tsx`, update the component signature:

```tsx
type Props = {
  sourcesMetadata: Record<string, { ingested: boolean; ingested_at: string | null; tags: string[] }>;
};

const SourcesView: React.FC<Props> = ({ sourcesMetadata }) => {
```

Remove the internal `metadata` state declaration:
```tsx
// DELETE this line:
const [metadata, setMetadata] = useState<Record<string, { ingested: boolean, ingested_at: string | null; tags: string[] }>>({});
```

Replace every reference to `metadata` with `sourcesMetadata` throughout the file (there should be ~3-5 references — check with a search).

Remove the `fetchMetadata` function and its `setInterval` call from the internal `useEffect` in `SourcesView`.

- [x] **Step 3: Verify compilation**

```bash
cd Faragopedia-Sales/frontend
npx tsc --noEmit
```
Expected: No errors.

- [x] **Step 4: Commit**

```bash
git add Faragopedia-Sales/frontend/src/App.tsx Faragopedia-Sales/frontend/src/components/SourcesView.tsx
git commit -m "feat: lift metadata poll to App.tsx with ingestion completion toasts"
```

---

## Task 5: Frontend — Bulk selection UI in `SourcesView`

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/components/SourcesView.tsx`

- [x] **Step 1: Add selection state and hover state**

Inside `SourcesView`, add:

```tsx
const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
const [hoveredItem, setHoveredItem] = useState<string | null>(null);
const [showConfirm, setShowConfirm] = useState(false);
```

Add `ConfirmDialog` import at the top:

```tsx
import ConfirmDialog from './ConfirmDialog';
```

- [x] **Step 2: Add checkbox toggle helper**

```tsx
const toggleSelection = (filename: string) => {
  setSelectedItems(prev => {
    const next = new Set(prev);
    if (next.has(filename)) next.delete(filename); else next.add(filename);
    return next;
  });
};

const selectAll = () => {
  const visible = filteredSources.map(s => s.filename); // or whatever the current list is
  setSelectedItems(new Set(visible));
};

const clearSelection = () => setSelectedItems(new Set());
```

- [x] **Step 3: Add checkboxes to each source list item**

In the JSX where each source item is rendered (find the `<div>` or `<button>` that wraps a single source row in the sidebar list), wrap it to add hover tracking and a checkbox:

```tsx
<div
  key={filename}
  className="relative group flex items-center"
  onMouseEnter={() => setHoveredItem(filename)}
  onMouseLeave={() => setHoveredItem(null)}
>
  {/* Checkbox — visible on hover OR when in selection mode */}
  {(hoveredItem === filename || selectedItems.size > 0) && (
    <input
      type="checkbox"
      checked={selectedItems.has(filename)}
      onChange={() => toggleSelection(filename)}
      onClick={e => e.stopPropagation()}
      className="absolute left-2 z-10 w-4 h-4 accent-blue-600 cursor-pointer"
    />
  )}
  {/* Existing item content — shift left padding when checkbox visible */}
  <div
    className={`flex-1 ${(hoveredItem === filename || selectedItems.size > 0) ? 'pl-8' : 'pl-2'} ...existing classes...`}
    onClick={() => fetchSourceContent(filename)}
  >
    {/* existing content */}
  </div>
</div>
```

Note: preserve all existing class names on the inner div — only add the conditional `pl-8` / `pl-2` switching.

- [x] **Step 4: Add bulk action toolbar**

At the bottom of the sources sidebar list panel (just before the closing div of the list panel), add:

```tsx
{selectedItems.size > 0 && (
  <div className="border-t border-gray-200 bg-white px-3 py-2 flex items-center gap-2 flex-wrap">
    <span className="text-xs text-gray-500 flex-1">{selectedItems.size} selected</span>
    <button
      onClick={selectAll}
      className="text-xs text-blue-600 hover:underline"
    >
      Select all
    </button>
    <button
      onClick={handleBulkIngest}
      className="text-xs px-2 py-1 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
    >
      Ingest selected
    </button>
    <button
      onClick={() => setShowConfirm(true)}
      className="text-xs px-2 py-1 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
    >
      Archive selected
    </button>
    <button onClick={clearSelection} className="text-gray-400 hover:text-gray-600">
      <X className="w-4 h-4" />
    </button>
  </div>
)}
```

- [x] **Step 5: Add bulk ingest and bulk archive handlers**

```tsx
const handleBulkIngest = async () => {
  try {
    await fetch(`${API_BASE}/sources/bulk-ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filenames: Array.from(selectedItems) }),
    });
    clearSelection();
  } catch {
    setError('Failed to start bulk ingestion');
  }
};

const handleBulkArchive = async () => {
  setShowConfirm(false);
  try {
    const res = await fetch(`${API_BASE}/sources/bulk`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filenames: Array.from(selectedItems) }),
    });
    const data = await res.json();
    if (data.errors?.length) {
      setError(`Failed to archive: ${data.errors.join(', ')}`);
    }
    clearSelection();
    fetchSources();
  } catch {
    setError('Failed to archive selected sources');
  }
};
```

- [x] **Step 6: Add Escape key handler and ConfirmDialog render**

Add to an existing `useEffect` or create a new one:

```tsx
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') clearSelection();
  };
  window.addEventListener('keydown', handleKeyDown);
  return () => window.removeEventListener('keydown', handleKeyDown);
}, []);
```

Add `ConfirmDialog` in the JSX (at the root of the component return, alongside `ErrorToast`):

```tsx
{showConfirm && (
  <ConfirmDialog
    message={`Archive ${selectedItems.size} source${selectedItems.size === 1 ? '' : 's'}? This can be undone from the Archive view.`}
    confirmLabel="Archive"
    onConfirm={handleBulkArchive}
    onCancel={() => setShowConfirm(false)}
  />
)}
```

- [x] **Step 7: Verify compilation**

```bash
cd Faragopedia-Sales/frontend
npx tsc --noEmit
```
Expected: No errors.

- [x] **Step 8: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/SourcesView.tsx
git commit -m "feat: add bulk selection UI and bulk ingest/archive to SourcesView"
```

---

## Task 6: Frontend — Bulk selection UI in `WikiView`

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/components/WikiView.tsx`

- [x] **Step 1: Add selection state**

Inside `WikiView`, add:

```tsx
const [selectedPages, setSelectedPages] = useState<Set<string>>(new Set());
const [hoveredPage, setHoveredPage] = useState<string | null>(null);
const [showConfirm, setShowConfirm] = useState(false);
```

Add imports:

```tsx
import ConfirmDialog from './ConfirmDialog';
// Add Checkbox icon or use <input type="checkbox"> directly
```

- [x] **Step 2: Add toggle helpers**

```tsx
const togglePageSelection = (path: string) => {
  setSelectedPages(prev => {
    const next = new Set(prev);
    if (next.has(path)) next.delete(path); else next.add(path);
    return next;
  });
};

const selectAllPages = () => {
  const allPaths: string[] = Object.values(pageTree).flat();
  setSelectedPages(new Set(allPaths));
};

const clearPageSelection = () => setSelectedPages(new Set());
```

- [x] **Step 3: Add checkboxes to page leaf nodes in the wiki tree**

Find where each page leaf is rendered inside the tree (the `<div>` or `<button>` that renders an individual page inside a section). Wrap it similarly to Task 5 Step 3:

```tsx
<div
  key={page}
  className="relative group flex items-center"
  onMouseEnter={() => setHoveredPage(page)}
  onMouseLeave={() => setHoveredPage(null)}
>
  {(hoveredPage === page || selectedPages.size > 0) && (
    <input
      type="checkbox"
      checked={selectedPages.has(page)}
      onChange={() => togglePageSelection(page)}
      onClick={e => e.stopPropagation()}
      className="absolute left-2 z-10 w-4 h-4 accent-blue-600 cursor-pointer"
    />
  )}
  <div
    className={`flex-1 ${(hoveredPage === page || selectedPages.size > 0) ? 'pl-8' : 'pl-2'} ...existing classes...`}
    onClick={() => fetchPageContent(page)}
  >
    {/* existing page label */}
  </div>
</div>
```

Do **not** add checkboxes to folder/entity-type headers — only to page leaf items.

- [x] **Step 4: Add bulk action toolbar to wiki sidebar**

At the bottom of the wiki sidebar list panel:

```tsx
{selectedPages.size > 0 && (
  <div className="border-t border-gray-200 bg-white px-3 py-2 flex items-center gap-2 flex-wrap">
    <span className="text-xs text-gray-500 flex-1">{selectedPages.size} selected</span>
    <button onClick={selectAllPages} className="text-xs text-blue-600 hover:underline">
      Select all
    </button>
    <button
      onClick={() => setShowConfirm(true)}
      className="text-xs px-2 py-1 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
    >
      Archive selected
    </button>
    <button onClick={clearPageSelection} className="text-gray-400 hover:text-gray-600">
      <X className="w-4 h-4" />
    </button>
  </div>
)}
```

- [x] **Step 5: Add bulk archive handler**

```tsx
const handleBulkArchivePages = async () => {
  setShowConfirm(false);
  try {
    const res = await fetch(`${API_BASE}/pages/bulk`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: Array.from(selectedPages) }),
    });
    const data = await res.json();
    if (data.errors?.length) {
      setError(`Failed to archive: ${data.errors.join(', ')}`);
    }
    // If currently selected page was archived, clear it
    if (selectedPage && selectedPages.has(selectedPage)) {
      setSelectedPage(null);
      setContent(null);
    }
    clearPageSelection();
    fetchPages();
  } catch {
    setError('Failed to archive selected pages');
  }
};
```

- [x] **Step 6: Add Escape key handler and ConfirmDialog render**

```tsx
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') clearPageSelection();
  };
  window.addEventListener('keydown', handleKeyDown);
  return () => window.removeEventListener('keydown', handleKeyDown);
}, []);
```

```tsx
{showConfirm && (
  <ConfirmDialog
    message={`Archive ${selectedPages.size} page${selectedPages.size === 1 ? '' : 's'}? This can be undone from the Archive view.`}
    confirmLabel="Archive"
    onConfirm={handleBulkArchivePages}
    onCancel={() => setShowConfirm(false)}
  />
)}
```

- [x] **Step 7: Verify compilation**

```bash
cd Faragopedia-Sales/frontend
npx tsc --noEmit
```
Expected: No errors.

- [x] **Step 8: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/WikiView.tsx
git commit -m "feat: add bulk selection UI and bulk archive to WikiView"
```

---

## Task 7: Manual smoke test

- [x] **Step 1: Start the backend**

```bash
cd Faragopedia-Sales/backend
uvicorn main:app --reload
```

- [x] **Step 2: Start the frontend**

```bash
cd Faragopedia-Sales/frontend
npm run dev
```

- [x] **Step 3: Test bulk ingest**
  1. Upload 2-3 source files without ingesting them
  2. Hover over a source — checkbox should appear
  3. Check 2 sources — both checkboxes stay visible, toolbar appears at bottom
  4. Click "Ingest selected"
  5. Navigate to Wiki view, then back to Sources
  6. Verify the sources show "Pending" and eventually "Ingested" (within ~15 seconds)
  7. Verify a toast fires for each source as it finishes

- [x] **Step 4: Test bulk archive sources**
  1. Check 2 sources
  2. Click "Archive selected"
  3. Confirm dialog should appear with correct count
  4. Click "Archive"
  5. Sources should disappear from the list
  6. Navigate to Archive view — verify they appear there

- [x] **Step 5: Test bulk archive wiki pages**
  1. Go to Wiki view
  2. Hover over a page leaf — checkbox should appear
  3. Select 2 pages — toolbar appears
  4. Click "Archive selected"
  5. Confirm, verify pages disappear from tree
  6. Navigate to Archive view — verify they appear

- [x] **Step 6: Test Escape key**
  - Select some items, press Escape — selection should clear

- [x] **Step 7: Commit any fixes found during smoke test**

```bash
git add -p
git commit -m "fix: smoke test corrections for bulk operations"
```

---

## Task 8: Run full test suite

- [x] **Step 1: Run all backend tests**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/ -v
```
Expected: All tests pass.

- [x] **Step 2: Run frontend type check**

```bash
cd Faragopedia-Sales/frontend
npx tsc --noEmit
```
Expected: No errors.

- [x] **Step 3: Commit if any final fixes were needed**

```bash
git add .
git commit -m "fix: final bulk operations corrections"
```
