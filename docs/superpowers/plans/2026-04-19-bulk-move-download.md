# Bulk Move & Bulk Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bulk move (wiki pages between entity-type subdirectories, with wikilink rewriting) and bulk download (wiki pages and sources as ZIP) to both the backend API and frontend UI.

**Architecture:** Three new backend endpoints (`POST /pages/bulk-move`, `POST /pages/bulk-download`, `POST /sources/bulk-download`) follow the existing pattern in `routes.py`. Frontend adds Move/Download buttons to the existing selection toolbars in `WikiView.tsx` and `SourcesView.tsx`, plus a new `MoveDialog.tsx` component for destination picking.

**Tech Stack:** Python/FastAPI (stdlib `zipfile`, `os`, `re`), React/TypeScript, lucide-react icons, pytest/httpx for backend tests, Playwright for smoke tests.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `Faragopedia-Sales/backend/api/routes.py` | Modify | Add 3 new endpoints + `BulkMove` pydantic model |
| `Faragopedia-Sales/backend/tests/test_bulk_operations.py` | Modify | Add unit tests for new endpoints |
| `Faragopedia-Sales/frontend/src/components/MoveDialog.tsx` | Create | Destination picker modal for bulk move |
| `Faragopedia-Sales/frontend/src/components/WikiView.tsx` | Modify | Add Move + Download buttons, handlers, MoveDialog |
| `Faragopedia-Sales/frontend/src/components/SourcesView.tsx` | Modify | Add Download button and handler |
| `scripts/smoke_test_bulk.py` | Modify | Add Playwright tests for move and download |

---

## Task 1: Backend — `POST /pages/bulk-move`

**Files:**
- Modify: `Faragopedia-Sales/backend/api/routes.py`
- Modify: `Faragopedia-Sales/backend/tests/test_bulk_operations.py`

- [ ] **Step 1: Write the failing tests**

Append to `Faragopedia-Sales/backend/tests/test_bulk_operations.py`:

```python
@pytest.mark.asyncio
async def test_bulk_move_pages_success():
    """Pages are renamed and wikilinks are rewritten."""
    moved_calls = []

    def rename_side_effect(src, dst):
        moved_calls.append((src, dst))

    with patch("api.routes.wiki_manager") as mock_wm, \
         patch("api.routes.safe_wiki_filename", side_effect=lambda p: p), \
         patch("api.routes.os.path.exists", return_value=True), \
         patch("api.routes.os.rename", side_effect=rename_side_effect), \
         patch("api.routes.rewrite_wikilinks", return_value={"contacts/john.md": 1}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.post(
                "/pages/bulk-move",
                json={"paths": ["prospects/acme.md"], "destination": "clients"}
            )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["moved"]) == 1
    assert data["errors"] == []
    assert data["links_rewritten"] == {"contacts/john.md": 1}


@pytest.mark.asyncio
async def test_bulk_move_pages_invalid_destination():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
        resp = await ac.post(
            "/pages/bulk-move",
            json={"paths": ["prospects/acme.md"], "destination": "invoices"}
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_bulk_move_pages_destination_exists():
    """If destination file already exists, it's reported as an error."""
    def exists_side_effect(path):
        return "clients/acme.md" in path  # destination file already exists

    with patch("api.routes.wiki_manager") as mock_wm, \
         patch("api.routes.safe_wiki_filename", side_effect=lambda p: p), \
         patch("api.routes.os.path.exists", side_effect=exists_side_effect), \
         patch("api.routes.rewrite_wikilinks", return_value={}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.post(
                "/pages/bulk-move",
                json={"paths": ["prospects/acme.md"], "destination": "clients"}
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["moved"] == []
    assert len(data["errors"]) == 1
    assert data["errors"][0]["path"] == "prospects/acme.md"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_bulk_operations.py::test_bulk_move_pages_success tests/test_bulk_operations.py::test_bulk_move_pages_invalid_destination tests/test_bulk_operations.py::test_bulk_move_pages_destination_exists -v
```

Expected: FAIL — `404 Not Found` (endpoint doesn't exist yet), or import errors for `rewrite_wikilinks`.

- [ ] **Step 3: Add the `BulkMove` model and `rewrite_wikilinks` helper to `routes.py`**

In `Faragopedia-Sales/backend/api/routes.py`, add after the existing pydantic models (after line ~22, after `class BulkPaths`):

```python
class BulkMove(BaseModel):
    paths: List[str]
    destination: str
```

Then add the `rewrite_wikilinks` helper function after `get_valid_entity_subdirs()` (around line 46):

```python
def rewrite_wikilinks(old_paths: List[str], path_map: dict) -> dict:
    """Scan all .md files in WIKI_DIR and rewrite wikilinks for moved pages.
    
    old_paths: list of original paths e.g. ["prospects/acme.md"]
    path_map: {old_path: new_path} e.g. {"prospects/acme.md": "clients/acme.md"}
    Returns: {file_path: count_of_rewrites}
    """
    links_rewritten = {}
    for root, dirs, files in os.walk(WIKI_DIR):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            full = os.path.join(root, fname)
            try:
                with open(full, "r", encoding="utf-8") as f:
                    original = f.read()
            except OSError:
                continue
            updated = original
            count = 0
            for old_path, new_path in path_map.items():
                # Strip .md for wikilink format: [[subdir/page-name]]
                old_link = old_path[:-3] if old_path.endswith(".md") else old_path
                new_link = new_path[:-3] if new_path.endswith(".md") else new_path
                pattern = r'\[\[' + re.escape(old_link) + r'\]\]'
                replacement = f'[[{new_link}]]'
                new_text, n = re.subn(pattern, replacement, updated)
                updated = new_text
                count += n
            if count > 0 and updated != original:
                with open(full, "w", encoding="utf-8") as f:
                    f.write(updated)
                # Use relative path from WIKI_DIR for the key
                rel = os.path.relpath(full, WIKI_DIR).replace("\\", "/")
                links_rewritten[rel] = count
    return links_rewritten
```

- [ ] **Step 4: Add the `POST /pages/bulk-move` endpoint to `routes.py`**

Add this endpoint after the `DELETE /pages/bulk` endpoint (around line 386):

```python
@router.post("/pages/bulk-move")
async def bulk_move_pages(payload: BulkMove):
    valid_destinations = get_valid_entity_subdirs()
    if payload.destination not in valid_destinations:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid destination '{payload.destination}'. Must be one of: {sorted(valid_destinations)}"
        )
    moved = []
    errors = []
    path_map = {}
    for path in payload.paths:
        try:
            safe_path = safe_wiki_filename(path)
        except ValueError as e:
            errors.append({"path": path, "error": str(e)})
            continue
        filename = safe_path.split("/")[1]  # e.g. "acme.md"
        new_path = f"{payload.destination}/{filename}"
        src = os.path.join(WIKI_DIR, safe_path.replace("/", os.sep))
        dst = os.path.join(WIKI_DIR, new_path.replace("/", os.sep))
        if os.path.exists(dst):
            errors.append({"path": path, "error": "destination already exists"})
            continue
        try:
            os.rename(src, dst)
            moved.append(f"{safe_path} → {new_path}")
            path_map[safe_path] = new_path
        except OSError as e:
            errors.append({"path": path, "error": str(e)})
    links_rewritten = rewrite_wikilinks(list(path_map.keys()), path_map) if path_map else {}
    return {"moved": moved, "errors": errors, "links_rewritten": links_rewritten}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_bulk_operations.py::test_bulk_move_pages_success tests/test_bulk_operations.py::test_bulk_move_pages_invalid_destination tests/test_bulk_operations.py::test_bulk_move_pages_destination_exists -v
```

Expected: PASS (all 3 green).

- [ ] **Step 6: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2"
git add Faragopedia-Sales/backend/api/routes.py Faragopedia-Sales/backend/tests/test_bulk_operations.py
git commit -m "feat: add POST /pages/bulk-move endpoint with wikilink rewriting"
```

---

## Task 2: Backend — `POST /pages/bulk-download`

**Files:**
- Modify: `Faragopedia-Sales/backend/api/routes.py`
- Modify: `Faragopedia-Sales/backend/tests/test_bulk_operations.py`

- [ ] **Step 1: Write the failing tests**

Append to `Faragopedia-Sales/backend/tests/test_bulk_operations.py`:

```python
@pytest.mark.asyncio
async def test_bulk_download_pages_success():
    """Returns a ZIP with the requested pages."""
    import io, zipfile as zf

    fake_content = b"# Acme\nSome content"

    def open_side_effect(path, *args, **kwargs):
        import io as _io
        return _io.open.__new__(type(open(os.devnull, "rb")))  # placeholder

    with patch("api.routes.safe_wiki_filename", side_effect=lambda p: p), \
         patch("api.routes.os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=fake_content)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.post(
                "/pages/bulk-download",
                json={"paths": ["clients/acme.md"]}
            )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "pages-export.zip" in resp.headers["content-disposition"]
    # Verify it's a valid ZIP
    buf = io.BytesIO(resp.content)
    with zf.ZipFile(buf) as z:
        assert "clients/acme.md" in z.namelist()


@pytest.mark.asyncio
async def test_bulk_download_pages_missing_file():
    """Returns 404 if any requested page doesn't exist."""
    with patch("api.routes.safe_wiki_filename", side_effect=lambda p: p), \
         patch("api.routes.os.path.exists", return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.post(
                "/pages/bulk-download",
                json={"paths": ["clients/missing.md"]}
            )
    assert resp.status_code == 404
```

Add `from unittest.mock import mock_open` to the imports at the top of the test file (it's already imported via `unittest.mock` — just add `mock_open` to the existing import line):

```python
from unittest.mock import AsyncMock, patch, MagicMock, mock_open
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_bulk_operations.py::test_bulk_download_pages_success tests/test_bulk_operations.py::test_bulk_download_pages_missing_file -v
```

Expected: FAIL — `404 Not Found` (endpoint doesn't exist yet).

- [ ] **Step 3: Add the `POST /pages/bulk-download` endpoint to `routes.py`**

Add this import at the top of `routes.py` with the other imports:

```python
import zipfile
import io
```

Add this endpoint after `bulk_move_pages`:

```python
@router.post("/pages/bulk-download")
async def bulk_download_pages(payload: BulkPaths):
    # Validate and resolve all paths first (fail fast)
    resolved = []
    for path in payload.paths:
        try:
            safe_path = safe_wiki_filename(path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        full_path = os.path.join(WIKI_DIR, safe_path.replace("/", os.sep))
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail=f"Page not found: {path}")
        resolved.append((safe_path, full_path))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for safe_path, full_path in resolved:
            with open(full_path, "rb") as f:
                zf.writestr(safe_path, f.read())
    buf.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="pages-export.zip"'}
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_bulk_operations.py::test_bulk_download_pages_success tests/test_bulk_operations.py::test_bulk_download_pages_missing_file -v
```

Expected: PASS (both green).

- [ ] **Step 5: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2"
git add Faragopedia-Sales/backend/api/routes.py Faragopedia-Sales/backend/tests/test_bulk_operations.py
git commit -m "feat: add POST /pages/bulk-download endpoint"
```

---

## Task 3: Backend — `POST /sources/bulk-download`

**Files:**
- Modify: `Faragopedia-Sales/backend/api/routes.py`
- Modify: `Faragopedia-Sales/backend/tests/test_bulk_operations.py`

- [ ] **Step 1: Write the failing tests**

Append to `Faragopedia-Sales/backend/tests/test_bulk_operations.py`:

```python
@pytest.mark.asyncio
async def test_bulk_download_sources_success():
    """Returns a ZIP with the requested source files."""
    import io, zipfile as zf

    fake_content = b"PDF content here"

    with patch("api.routes.os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=fake_content)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.post(
                "/sources/bulk-download",
                json={"filenames": ["brief-2026-01.pdf"]}
            )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "sources-export.zip" in resp.headers["content-disposition"]
    buf = io.BytesIO(resp.content)
    with zf.ZipFile(buf) as z:
        assert "brief-2026-01.pdf" in z.namelist()


@pytest.mark.asyncio
async def test_bulk_download_sources_missing_file():
    with patch("api.routes.os.path.exists", return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.post(
                "/sources/bulk-download",
                json={"filenames": ["missing.pdf"]}
            )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_bulk_operations.py::test_bulk_download_sources_success tests/test_bulk_operations.py::test_bulk_download_sources_missing_file -v
```

Expected: FAIL — `404 Not Found`.

- [ ] **Step 3: Add the `POST /sources/bulk-download` endpoint to `routes.py`**

Add after `bulk_download_pages`:

```python
@router.post("/sources/bulk-download")
async def bulk_download_sources(payload: BulkFilenames):
    # Validate and resolve all filenames first (fail fast)
    resolved = []
    for filename in payload.filenames:
        safe_name = os.path.basename(filename)
        full_path = os.path.join(SOURCES_DIR, safe_name)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail=f"Source not found: {filename}")
        resolved.append((safe_name, full_path))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for safe_name, full_path in resolved:
            with open(full_path, "rb") as f:
                zf.writestr(safe_name, f.read())
    buf.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="sources-export.zip"'}
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_bulk_operations.py::test_bulk_download_sources_success tests/test_bulk_operations.py::test_bulk_download_sources_missing_file -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite to catch regressions**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2"
git add Faragopedia-Sales/backend/api/routes.py Faragopedia-Sales/backend/tests/test_bulk_operations.py
git commit -m "feat: add POST /sources/bulk-download endpoint"
```

---

## Task 4: Frontend — `MoveDialog.tsx`

**Files:**
- Create: `Faragopedia-Sales/frontend/src/components/MoveDialog.tsx`

- [ ] **Step 1: Create the component**

Create `Faragopedia-Sales/frontend/src/components/MoveDialog.tsx`:

```tsx
import React, { useState } from 'react';
import { MoveRight } from 'lucide-react';

const ENTITY_TYPES = ['clients', 'contacts', 'photographers', 'productions', 'prospects'] as const;
type EntityType = typeof ENTITY_TYPES[number];

type Props = {
  selectedCount: number;
  initialDestination?: EntityType;
  onConfirm: (destination: EntityType) => void;
  onClose: () => void;
};

const MoveDialog: React.FC<Props> = ({ selectedCount, initialDestination, onConfirm, onClose }) => {
  const [destination, setDestination] = useState<EntityType>(initialDestination ?? 'clients');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full mx-4 animate-fade-in border border-gray-100">
        <h2 className="text-gray-900 font-semibold text-base mb-1">Move {selectedCount} page{selectedCount !== 1 ? 's' : ''}</h2>
        <p className="text-gray-500 text-sm mb-5">Select a destination entity type.</p>
        <div className="flex flex-col gap-2 mb-6">
          {ENTITY_TYPES.map((type) => (
            <label
              key={type}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer border transition-all ${
                destination === type
                  ? 'border-blue-500 bg-blue-50 text-blue-700 font-medium'
                  : 'border-gray-200 hover:bg-gray-50 text-gray-700'
              }`}
            >
              <input
                type="radio"
                name="destination"
                value={type}
                checked={destination === type}
                onChange={() => setDestination(type)}
                className="accent-blue-600"
              />
              <span className="capitalize text-sm">{type}</span>
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors font-medium"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(destination)}
            className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 rounded-lg hover:bg-blue-500 transition-colors font-bold"
          >
            <MoveRight className="w-4 h-4" />
            Move {selectedCount} page{selectedCount !== 1 ? 's' : ''}
          </button>
        </div>
      </div>
    </div>
  );
};

export default MoveDialog;
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/frontend"
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2"
git add Faragopedia-Sales/frontend/src/components/MoveDialog.tsx
git commit -m "feat: add MoveDialog component for bulk page move"
```

---

## Task 5: Frontend — WikiView bulk Move and Download

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/components/WikiView.tsx`

### 5a — Import and state

- [ ] **Step 1: Add MoveDialog import and new state variables**

In `WikiView.tsx`, find the existing imports block. Add `MoveDialog` import after `ConfirmDialog`:

```tsx
import MoveDialog from './MoveDialog';
```

Also add `MoveRight` and `Download` to the lucide-react import line (they're not currently imported):

```tsx
import { FileText, ChevronRight, Loader2, ArrowLeft, ArrowRight, Edit3, Save, X, Trash2, Download, Plus, MoreVertical, MessageSquare, FolderPlus, Pencil, Search, MoveRight } from 'lucide-react';
```

(`Download` is already imported — just add `MoveRight`.)

In the component body, find the existing state declarations and add two new ones right after `const [showConfirm, setShowConfirm] = useState(false)` (search for that line):

```tsx
const [showMoveDialog, setShowMoveDialog] = useState(false);
const [moveError, setMoveError] = useState<string | null>(null);
```

### 5b — Handlers

- [ ] **Step 2: Add `handleBulkMove` and `handleBulkDownloadPages` handlers**

Find `handleBulkArchivePages` in `WikiView.tsx`. Add these two handlers immediately after it:

```tsx
const handleBulkMove = async (destination: string) => {
  setShowMoveDialog(false);
  try {
    const res = await fetch(`${API_BASE}/pages/bulk-move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: Array.from(selectedPages), destination }),
    });
    const data = await res.json();
    const movedCount = data.moved?.length ?? 0;
    const linkCount = Object.values(data.links_rewritten ?? {}).reduce((a: number, b) => a + (b as number), 0);
    if (data.errors?.length) {
      setError(`Moved ${movedCount} page(s). Failed: ${data.errors.map((e: { path: string }) => e.path).join(', ')}`);
    }
    if (movedCount > 0) {
      const linkMsg = linkCount > 0 ? ` ${linkCount} wikilink(s) updated.` : '';
      // Use existing error state as toast (consistent with rest of component)
      if (!data.errors?.length) {
        setError(`Moved ${movedCount} page(s) to ${destination}.${linkMsg}`);
      }
    }
    clearPageSelection();
    fetchPages();
  } catch {
    setError('Failed to move selected pages');
  }
};

const handleBulkDownloadPages = async () => {
  try {
    const res = await fetch(`${API_BASE}/pages/bulk-download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: Array.from(selectedPages) }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setError(err.detail ?? 'Failed to download pages');
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'pages-export.zip';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch {
    setError('Failed to download selected pages');
  }
};
```

### 5c — Toolbar buttons

- [ ] **Step 3: Add Move and Download buttons to the bulk action toolbar**

Find the bulk action toolbar in `WikiView.tsx`. It currently looks like:

```tsx
<button
  onClick={() => setShowConfirm(true)}
  className="flex items-center justify-center gap-2 text-xs py-2 bg-red-600 text-white rounded-lg hover:bg-red-500 shadow-sm transition-all font-bold"
>
  <Trash2 className="w-4 h-4" />
  Archive Selection
</button>
```

Replace the `<div className="flex flex-col gap-2">` contents (the Select All button and Archive button) with:

```tsx
<button
  onClick={selectAllPages}
  className="w-full text-[10px] py-1 bg-white/10 text-gray-300 rounded hover:bg-white/20 transition-all font-medium uppercase tracking-tight"
>
  Select {searchResults ? 'matching' : 'all'}
</button>
<div className="grid grid-cols-3 gap-2">
  <button
    onClick={() => setShowMoveDialog(true)}
    className="flex items-center justify-center gap-2 text-xs py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 shadow-sm transition-all font-bold"
  >
    <MoveRight className="w-3.5 h-3.5" />
    Move
  </button>
  <button
    onClick={handleBulkDownloadPages}
    className="flex items-center justify-center gap-2 text-xs py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-500 shadow-sm transition-all font-bold"
  >
    <Download className="w-3.5 h-3.5" />
    Download
  </button>
  <button
    onClick={() => setShowConfirm(true)}
    className="flex items-center justify-center gap-2 text-xs py-2 bg-red-600 text-white rounded-lg hover:bg-red-500 shadow-sm transition-all font-bold"
  >
    <Trash2 className="w-3.5 h-3.5" />
    Archive
  </button>
</div>
```

### 5d — Render MoveDialog

- [ ] **Step 4: Render `MoveDialog` in the JSX**

Find where `ConfirmDialog` is rendered in `WikiView.tsx` (search for `showConfirm &&`). Add `MoveDialog` immediately after the `ConfirmDialog` block:

```tsx
{showMoveDialog && (
  <MoveDialog
    selectedCount={selectedPages.size}
    initialDestination={
      selectedPages.size > 0
        ? (Array.from(selectedPages)[0].split('/')[0] as any)
        : undefined
    }
    onConfirm={handleBulkMove}
    onClose={() => setShowMoveDialog(false)}
  />
)}
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/frontend"
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 6: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2"
git add Faragopedia-Sales/frontend/src/components/WikiView.tsx
git commit -m "feat: add bulk Move and Download to WikiView"
```

---

## Task 6: Frontend — SourcesView bulk Download

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/components/SourcesView.tsx`

- [ ] **Step 1: Add `handleBulkDownloadSources` handler**

In `SourcesView.tsx`, find `handleBulkArchive`. Add this handler immediately after it:

```tsx
const handleBulkDownloadSources = async () => {
  try {
    const res = await fetch(`${API_BASE}/sources/bulk-download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filenames: Array.from(selectedItems) }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setError(err.detail ?? 'Failed to download sources');
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sources-export.zip';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch {
    setError('Failed to download selected sources');
  }
};
```

- [ ] **Step 2: Add Download button to the bulk action toolbar**

In `SourcesView.tsx`, find the bulk action toolbar. It currently has a `grid grid-cols-2 gap-2` div with Ingest and Archive buttons. Change it to `grid grid-cols-3 gap-2` and add a Download button between Ingest and Archive:

```tsx
<div className="grid grid-cols-3 gap-2">
  <button
    onClick={handleBulkIngest}
    className="flex items-center justify-center gap-2 text-xs py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 shadow-sm transition-all font-bold"
  >
    <Database className="w-3.5 h-3.5" />
    Ingest
  </button>
  <button
    onClick={handleBulkDownloadSources}
    className="flex items-center justify-center gap-2 text-xs py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-500 shadow-sm transition-all font-bold"
  >
    <Download className="w-3.5 h-3.5" />
    Download
  </button>
  <button
    onClick={() => setShowConfirm(true)}
    className="flex items-center justify-center gap-2 text-xs py-2 bg-red-600 text-white rounded-lg hover:bg-red-500 shadow-sm transition-all font-bold"
  >
    <Trash2 className="w-3.5 h-3.5" />
    Archive
  </button>
</div>
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/frontend"
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2"
git add Faragopedia-Sales/frontend/src/components/SourcesView.tsx
git commit -m "feat: add bulk Download to SourcesView"
```

---

## Task 7: Smoke Tests

**Files:**
- Modify: `scripts/smoke_test_bulk.py`

- [ ] **Step 1: Read the existing smoke test to understand its structure**

```bash
cat "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/scripts/smoke_test_bulk.py"
```

- [ ] **Step 2: Add smoke tests for bulk move and bulk download**

Append to `scripts/smoke_test_bulk.py`:

```python
def test_bulk_move_wiki_pages(page: Page, base_url: str):
    """Select a wiki page and move it to a different entity type."""
    page.goto(f"{base_url}/wiki")
    page.wait_for_load_state("networkidle")

    # Hover over first page to reveal checkbox
    first_page = page.locator('[data-testid="wiki-page-item"]').first
    first_page.hover()
    checkbox = first_page.locator('input[type="checkbox"]')
    expect(checkbox).to_be_visible()
    checkbox.click()

    # Bulk action toolbar should appear
    toolbar = page.locator('text=Selected').first
    expect(toolbar).to_be_visible()

    # Click Move button
    page.locator('button', has_text='Move').click()

    # MoveDialog should open
    dialog = page.locator('text=Move').filter(has_text='page')
    expect(dialog).to_be_visible()

    # Select a destination (pick 'clients' radio)
    page.locator('input[type="radio"][value="clients"]').click()

    # Confirm
    page.locator('button', has_text='Move 1 page').click()

    # Dialog closes and selection clears
    expect(page.locator('text=Move 1 page')).not_to_be_visible()


def test_bulk_download_wiki_pages(page: Page, base_url: str):
    """Select wiki pages and trigger a ZIP download."""
    page.goto(f"{base_url}/wiki")
    page.wait_for_load_state("networkidle")

    # Select first page
    first_page = page.locator('[data-testid="wiki-page-item"]').first
    first_page.hover()
    first_page.locator('input[type="checkbox"]').click()

    # Wait for download when clicking Download button
    with page.expect_download() as download_info:
        page.locator('button', has_text='Download').click()

    download = download_info.value
    assert download.suggested_filename == "pages-export.zip"


def test_bulk_download_sources(page: Page, base_url: str):
    """Select sources and trigger a ZIP download."""
    page.goto(f"{base_url}/sources")
    page.wait_for_load_state("networkidle")

    # Select first source
    first_source = page.locator('[data-testid="source-item"]').first
    first_source.hover()
    first_source.locator('input[type="checkbox"]').click()

    # Wait for download
    with page.expect_download() as download_info:
        page.locator('button', has_text='Download').click()

    download = download_info.value
    assert download.suggested_filename == "sources-export.zip"
```

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2"
git add scripts/smoke_test_bulk.py
git commit -m "test: add smoke tests for bulk move and download"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** `POST /pages/bulk-move` ✓, `POST /pages/bulk-download` ✓, `POST /sources/bulk-download` ✓, MoveDialog ✓, WikiView toolbar ✓, SourcesView toolbar ✓, wikilink rewriting ✓, fail-fast on missing files for download ✓, partial-success for move ✓
- [x] **No placeholders:** All steps contain complete code
- [x] **Type consistency:** `BulkMove` model used in Task 1; `BulkPaths` reused for pages download; `BulkFilenames` reused for sources download; `EntityType` used in `MoveDialog` matches what `handleBulkMove` receives; `StreamingResponse` imported inline in both download endpoints
- [x] **`rewrite_wikilinks` defined in Task 1 Step 3 and referenced in Task 1 Step 4** ✓
- [x] **`zipfile` and `io` imports added in Task 2 Step 3, used by both Task 2 and Task 3** ✓
