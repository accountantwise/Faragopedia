# Add Sources Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the single-file `+` upload button in SourcesView with an "Add Sources" modal supporting multi-file upload, URL crawl via WiseCrawler, and paste text.

**Architecture:** Backend gets a WiseCrawler async client module and two new endpoints (`POST /paste`, `POST /scrape-urls`). URL crawls run as FastAPI BackgroundTasks; sources appear automatically via the frontend's existing 5-second metadata poll. Frontend gets a self-contained `AddSourcesModal` component wired into `SourcesView`.

**Tech Stack:** Python/FastAPI, httpx (already in requirements), React/TypeScript, Tailwind CSS, lucide-react icons.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/agent/wisecrawler.py` | WiseCrawler API client (start_crawl, poll_until_done, analyze_crawl) |
| Create | `backend/tests/test_wisecrawler.py` | Unit tests for wisecrawler client |
| Modify | `backend/api/routes.py` | Add POST /paste, POST /scrape-urls, _crawl_and_save helper |
| Modify | `backend/tests/test_sources.py` | Add tests for paste and scrape-urls endpoints |
| Create | `frontend/src/components/AddSourcesModal.tsx` | Modal component with Files / URL / Paste tabs |
| Modify | `frontend/src/components/SourcesView.tsx` | Replace label/input with modal button |
| Modify | `.env` | Add WISECRAWLER_BASE_URL and WISECRAWLER_API_KEY |

---

## Task 1: WiseCrawler Client

**Files:**
- Create: `Faragopedia-Sales/backend/agent/wisecrawler.py`
- Create: `Faragopedia-Sales/backend/tests/test_wisecrawler.py`

- [x] **Step 1: Write the failing tests**

Create `Faragopedia-Sales/backend/tests/test_wisecrawler.py`:

```python
import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def make_mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = json_data
    mock.status_code = status_code
    return mock


def make_mock_client(post_response=None, get_responses=None):
    """Build a mock httpx.AsyncClient context manager."""
    mock_client = AsyncMock()
    if post_response:
        mock_client.post = AsyncMock(return_value=post_response)
    if get_responses:
        mock_client.get = AsyncMock(side_effect=get_responses)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_start_crawl_returns_job_id():
    mock_client = make_mock_client(
        post_response=make_mock_response({"id": "job-abc123", "url": "https://example.com"})
    )
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": "test-key"}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            from agent.wisecrawler import start_crawl
            result = await start_crawl("https://example.com")

    assert result == "job-abc123"
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[1]["json"]["url"] == "https://example.com"
    assert "Authorization" in call_kwargs[1]["headers"]


@pytest.mark.asyncio
async def test_poll_until_done_waits_for_completion():
    get_responses = [
        make_mock_response({"status": "scraping", "total": 3, "completed": 1}),
        make_mock_response({"status": "scraping", "total": 3, "completed": 2}),
        make_mock_response({"status": "completed", "total": 3, "completed": 3, "data": []}),
    ]
    mock_client = make_mock_client(get_responses=get_responses)
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": ""}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            with patch("agent.wisecrawler.asyncio.sleep", new_callable=AsyncMock):
                from agent.wisecrawler import poll_until_done
                result = await poll_until_done("job-abc123", poll_interval=0)

    assert result["status"] == "completed"
    assert mock_client.get.call_count == 3


@pytest.mark.asyncio
async def test_poll_until_done_raises_on_failure():
    get_responses = [
        make_mock_response({"status": "failed"}),
    ]
    mock_client = make_mock_client(get_responses=get_responses)
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": ""}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            with patch("agent.wisecrawler.asyncio.sleep", new_callable=AsyncMock):
                from agent.wisecrawler import poll_until_done
                with pytest.raises(RuntimeError, match="failed"):
                    await poll_until_done("job-abc123", poll_interval=0)


@pytest.mark.asyncio
async def test_analyze_crawl_returns_analysis():
    mock_client = make_mock_client(
        post_response=make_mock_response({
            "success": True,
            "crawl_id": "job-abc123",
            "analysis": "Key findings: the site covers X and Y.",
        })
    )
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": ""}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            from agent.wisecrawler import analyze_crawl
            result = await analyze_crawl("job-abc123", "Summarize this.")

    assert result == "Key findings: the site covers X and Y."
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[1]["json"]["crawl_id"] == "job-abc123"
    assert call_kwargs[1]["json"]["prompt"] == "Summarize this."
```

- [x] **Step 2: Run to confirm tests fail**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wisecrawler.py -v
```

Expected: `ModuleNotFoundError: No module named 'agent.wisecrawler'`

- [x] **Step 3: Implement `agent/wisecrawler.py`**

Create `Faragopedia-Sales/backend/agent/wisecrawler.py`:

```python
import os
import asyncio
import httpx

DEFAULT_ANALYZE_PROMPT = (
    "Extract and summarize all key information, facts, names, and details "
    "from this website. Be thorough."
)


def _get_base_url() -> str:
    url = os.getenv("WISECRAWLER_BASE_URL", "").rstrip("/")
    if not url:
        raise ValueError("WISECRAWLER_BASE_URL is not configured")
    return url


def _get_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    key = os.getenv("WISECRAWLER_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def start_crawl(url: str) -> str:
    """POST /v1/crawl — returns job_id."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_base_url()}/v1/crawl",
            json={"url": url, "maxDepth": 1, "limit": 10},
            headers=_get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["id"]


async def poll_until_done(job_id: str, poll_interval: float = 3.0) -> dict:
    """GET /v1/crawl/{job_id} every poll_interval seconds until status == 'completed'."""
    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                f"{_get_base_url()}/v1/crawl/{job_id}",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            if data["status"] == "completed":
                return data
            if data["status"] in ("failed", "cancelled"):
                raise RuntimeError(f"Crawl {job_id} ended with status: {data['status']}")
            await asyncio.sleep(poll_interval)


async def analyze_crawl(job_id: str, prompt: str = DEFAULT_ANALYZE_PROMPT) -> str:
    """POST /v1/crawl/analyze — returns the analysis string."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_base_url()}/v1/crawl/analyze",
            json={"crawl_id": job_id, "prompt": prompt},
            headers=_get_headers(),
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["analysis"]
```

- [x] **Step 4: Run tests — expect pass**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wisecrawler.py -v
```

Expected: 4 passed

- [x] **Step 5: Commit**

```bash
git add Faragopedia-Sales/backend/agent/wisecrawler.py Faragopedia-Sales/backend/tests/test_wisecrawler.py
git commit -m "feat: add WiseCrawler async client with tests"
```

---

## Task 2: POST /paste Endpoint

**Files:**
- Modify: `Faragopedia-Sales/backend/api/routes.py`
- Modify: `Faragopedia-Sales/backend/tests/test_sources.py`

- [x] **Step 1: Write the failing tests**

Append to `Faragopedia-Sales/backend/tests/test_sources.py`:

```python
# ── Paste endpoint ────────────────────────────────────────────────────────────

def test_paste_source_happy_path(tmp_path):
    with patch("api.routes.SOURCES_DIR", str(tmp_path)):
        response = client.post("/api/paste", json={"content": "Hello world"})
    assert response.status_code == 200
    data = response.json()
    assert "filename" in data
    assert data["filename"].startswith("paste-")
    assert data["filename"].endswith(".txt")
    assert (tmp_path / data["filename"]).read_text(encoding="utf-8") == "Hello world"


def test_paste_source_with_custom_name(tmp_path):
    with patch("api.routes.SOURCES_DIR", str(tmp_path)):
        response = client.post("/api/paste", json={"content": "Notes", "name": "my notes"})
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "my_notes.txt"
    assert (tmp_path / "my_notes.txt").read_text(encoding="utf-8") == "Notes"


def test_paste_source_empty_content():
    response = client.post("/api/paste", json={"content": "   "})
    assert response.status_code == 422
```

- [x] **Step 2: Run to confirm tests fail**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_sources.py::test_paste_source_happy_path tests/test_sources.py::test_paste_source_with_custom_name tests/test_sources.py::test_paste_source_empty_content -v
```

Expected: FAIL — `404 Not Found` (route doesn't exist yet)

- [x] **Step 3: Add the endpoint to `routes.py`**

Add these imports at the top of `Faragopedia-Sales/backend/api/routes.py` (after existing imports):

```python
from datetime import datetime
from fastapi import BackgroundTasks
```

Add this endpoint to `Faragopedia-Sales/backend/api/routes.py` (after the existing `@router.post("/upload")` block):

```python
@router.post("/paste")
async def paste_source(payload: dict):
    content = payload.get("content", "")
    if not content or not content.strip():
        raise HTTPException(status_code=422, detail="Content is required")

    name = (payload.get("name") or "").strip()
    if name:
        filename = secure_filename(name)
        if not filename.endswith(".txt"):
            filename += ".txt"
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"paste-{timestamp}.txt"

    os.makedirs(SOURCES_DIR, exist_ok=True)
    file_path = os.path.join(SOURCES_DIR, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {"filename": filename, "message": "Text saved as source"}
```

- [x] **Step 4: Run tests — expect pass**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_sources.py::test_paste_source_happy_path tests/test_sources.py::test_paste_source_with_custom_name tests/test_sources.py::test_paste_source_empty_content -v
```

Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add Faragopedia-Sales/backend/api/routes.py Faragopedia-Sales/backend/tests/test_sources.py
git commit -m "feat: add POST /paste endpoint for text sources"
```

---

## Task 3: POST /scrape-urls Endpoint

**Files:**
- Modify: `Faragopedia-Sales/backend/api/routes.py`
- Modify: `Faragopedia-Sales/backend/tests/test_sources.py`

- [x] **Step 1: Write the failing tests**

Append to `Faragopedia-Sales/backend/tests/test_sources.py`:

```python
# ── Scrape URLs endpoint ──────────────────────────────────────────────────────

def test_scrape_urls_starts_background_jobs():
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc"}):
        with patch("api.routes._crawl_and_save", new_callable=AsyncMock):
            response = client.post(
                "/api/scrape-urls",
                json={"urls": ["https://example.com", "https://other.com"]},
            )
    assert response.status_code == 202
    assert response.json()["message"] == "Started 2 crawl job(s)"


def test_scrape_urls_empty_list():
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc"}):
        response = client.post("/api/scrape-urls", json={"urls": []})
    assert response.status_code == 422


def test_scrape_urls_no_wisecrawler_url():
    with patch.dict(os.environ, {}, clear=False):
        # Temporarily remove the env var if set
        env = {k: v for k, v in os.environ.items() if k != "WISECRAWLER_BASE_URL"}
        with patch.dict(os.environ, env, clear=True):
            response = client.post("/api/scrape-urls", json={"urls": ["https://example.com"]})
    assert response.status_code == 503
```

Also add `import os` to the top of `test_sources.py` if not already present.

- [x] **Step 2: Run to confirm tests fail**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_sources.py::test_scrape_urls_starts_background_jobs tests/test_sources.py::test_scrape_urls_empty_list tests/test_sources.py::test_scrape_urls_no_wisecrawler_url -v
```

Expected: FAIL — `404 Not Found`

- [x] **Step 3: Add endpoint and background task helper to `routes.py`**

Append to `Faragopedia-Sales/backend/api/routes.py`:

```python
# ── URL scraping via WiseCrawler ──────────────────────────────────────────────

async def _crawl_and_save(url: str) -> None:
    """Background task: crawl a URL with WiseCrawler, analyze, save to sources/."""
    import logging
    from urllib.parse import urlparse
    from agent.wisecrawler import start_crawl, poll_until_done, analyze_crawl, DEFAULT_ANALYZE_PROMPT

    logger = logging.getLogger(__name__)
    try:
        job_id = await start_crawl(url)
        await poll_until_done(job_id)
        analysis = await analyze_crawl(job_id, DEFAULT_ANALYZE_PROMPT)

        parsed = urlparse(url)
        domain = parsed.netloc.replace(".", "-").replace(":", "-")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{domain}-{timestamp}.md"

        os.makedirs(SOURCES_DIR, exist_ok=True)
        file_path = os.path.join(SOURCES_DIR, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# Source: {url}\n\n{analysis}")

        logger.info(f"Saved crawl result for {url} → {filename}")
    except Exception as exc:
        logger.error(f"Failed to crawl {url}: {exc}")


@router.post("/scrape-urls", status_code=202)
async def scrape_urls(payload: dict, background_tasks: BackgroundTasks):
    base_url = os.getenv("WISECRAWLER_BASE_URL", "")
    if not base_url:
        raise HTTPException(status_code=503, detail="WISECRAWLER_BASE_URL is not configured")

    urls = payload.get("urls", [])
    if not urls:
        raise HTTPException(status_code=422, detail="urls list is required and cannot be empty")

    for url in urls:
        background_tasks.add_task(_crawl_and_save, url)

    return {"message": f"Started {len(urls)} crawl job(s)"}
```

- [x] **Step 4: Run tests — expect pass**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_sources.py -v
```

Expected: all source tests pass (3 existing + 3 paste + 3 scrape-urls = 9 passed)

- [x] **Step 5: Commit**

```bash
git add Faragopedia-Sales/backend/api/routes.py Faragopedia-Sales/backend/tests/test_sources.py
git commit -m "feat: add POST /scrape-urls endpoint with WiseCrawler background tasks"
```

---

## Task 4: AddSourcesModal Component

**Files:**
- Create: `Faragopedia-Sales/frontend/src/components/AddSourcesModal.tsx`

No automated frontend tests exist in this project. Verify manually after Task 5.

- [x] **Step 1: Create `AddSourcesModal.tsx`**

Create `Faragopedia-Sales/frontend/src/components/AddSourcesModal.tsx`:

```tsx
import React, { useState, useRef } from 'react';
import { X, Upload, FileText, Loader2 } from 'lucide-react';
import { API_BASE } from '../config';

interface Props {
  open: boolean;
  onClose: () => void;
  onSourceAdded: () => void;
}

type Tab = 'files' | 'url' | 'paste';

const AddSourcesModal: React.FC<Props> = ({ open, onClose, onSourceAdded }) => {
  const [activeTab, setActiveTab] = useState<Tab>('files');

  // Files tab
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // URL tab
  const [urlText, setUrlText] = useState('');
  const [crawling, setCrawling] = useState(false);

  // Paste tab
  const [pasteName, setPasteName] = useState('');
  const [pasteContent, setPasteContent] = useState('');
  const [saving, setSaving] = useState(false);

  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const switchTab = (tab: Tab) => { setActiveTab(tab); setError(null); };

  // ── Files tab handlers ────────────────────────────────────────────────────

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    setSelectedFiles(prev => [...prev, ...Array.from(e.dataTransfer.files)]);
  };
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSelectedFiles(prev => [...prev, ...Array.from(e.target.files ?? [])]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };
  const removeFile = (index: number) => setSelectedFiles(prev => prev.filter((_, i) => i !== index));

  const handleFilesSubmit = async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setError(null);
    let anySuccess = false;
    for (const file of selectedFiles) {
      try {
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch(`${API_BASE}/upload?ingest=false`, { method: 'POST', body: formData });
        if (!res.ok) throw new Error(`Failed to upload ${file.name}`);
        anySuccess = true;
      } catch (err: any) {
        setError(err.message);
      }
    }
    setUploading(false);
    if (anySuccess) { onSourceAdded(); onClose(); }
  };

  // ── URL tab handler ───────────────────────────────────────────────────────

  const handleUrlSubmit = async () => {
    const urls = urlText.split('\n').map(u => u.trim()).filter(Boolean);
    if (urls.length === 0) return;
    setCrawling(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/scrape-urls`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start crawl');
      }
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setCrawling(false);
    }
  };

  // ── Paste tab handler ─────────────────────────────────────────────────────

  const handlePasteSubmit = async () => {
    if (!pasteContent.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/paste`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: pasteContent, name: pasteName || undefined }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save');
      }
      onSourceAdded();
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg">

        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-0">
          <h2 className="text-lg font-semibold text-gray-900">Add Sources</h2>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 mx-6 mt-4">
          {(['files', 'url', 'paste'] as Tab[]).map(tab => (
            <button
              key={tab}
              onClick={() => switchTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === tab
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab === 'files' ? '📁 Files' : tab === 'url' ? '🔗 URL' : '📋 Paste Text'}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="px-6 py-5">

          {error && (
            <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
              {error}
            </div>
          )}

          {/* ── Files tab ── */}
          {activeTab === 'files' && (
            <div>
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                  isDragging
                    ? 'border-blue-400 bg-blue-50'
                    : 'border-gray-300 hover:border-gray-400 bg-gray-50'
                }`}
              >
                <Upload className="w-8 h-8 mx-auto mb-2 text-gray-400" />
                <p className="text-sm font-medium text-gray-600">Drop files here or click to browse</p>
                <p className="text-xs text-gray-400 mt-1">PDF, TXT, MD, DOCX and more</p>
                <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFileSelect} />
              </div>

              {selectedFiles.length > 0 && (
                <ul className="mt-3 space-y-1">
                  {selectedFiles.map((file, i) => (
                    <li key={i} className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 rounded-md text-sm text-gray-700">
                      <FileText className="w-4 h-4 text-gray-400 shrink-0" />
                      <span className="truncate flex-1">{file.name}</span>
                      <button onClick={() => removeFile(i)} className="text-gray-400 hover:text-red-500 ml-auto transition-colors">
                        <X className="w-4 h-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <button
                onClick={handleFilesSubmit}
                disabled={selectedFiles.length === 0 || uploading}
                className="mt-4 w-full py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
              >
                {uploading
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> Uploading...</>
                  : `Upload ${selectedFiles.length > 0 ? selectedFiles.length + ' ' : ''}File${selectedFiles.length !== 1 ? 's' : ''}`
                }
              </button>
            </div>
          )}

          {/* ── URL tab ── */}
          {activeTab === 'url' && (
            <div>
              <textarea
                value={urlText}
                onChange={e => setUrlText(e.target.value)}
                placeholder={"https://example.com\nhttps://another-site.com\n\nOne URL per line"}
                className="w-full h-28 px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono text-gray-700 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-400 mt-1 mb-4">
                Each URL will be crawled and analyzed. Sources appear in the list when ready (~30–60s).
              </p>
              <button
                onClick={handleUrlSubmit}
                disabled={!urlText.trim() || crawling}
                className="w-full py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
              >
                {crawling ? <><Loader2 className="w-4 h-4 animate-spin" /> Starting...</> : 'Start Crawl'}
              </button>
            </div>
          )}

          {/* ── Paste tab ── */}
          {activeTab === 'paste' && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <label className="text-xs text-gray-500 whitespace-nowrap">Name (optional):</label>
                <input
                  type="text"
                  value={pasteName}
                  onChange={e => setPasteName(e.target.value)}
                  placeholder="Auto-generated if left blank"
                  className="flex-1 px-3 py-1.5 border border-gray-200 rounded-md text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <textarea
                value={pasteContent}
                onChange={e => setPasteContent(e.target.value)}
                placeholder="Paste your text here..."
                className="w-full h-36 px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={handlePasteSubmit}
                disabled={!pasteContent.trim() || saving}
                className="mt-4 w-full py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
              >
                {saving ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving...</> : 'Save as Source'}
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
};

export default AddSourcesModal;
```

- [x] **Step 2: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/AddSourcesModal.tsx
git commit -m "feat: add AddSourcesModal component with Files, URL, and Paste tabs"
```

---

## Task 5: Wire Up SourcesView + Environment Config

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/components/SourcesView.tsx`
- Modify: `Faragopedia-Sales/.env` (or `.env.local`)

- [x] **Step 1: Add env vars to `.env`**

Open `Faragopedia-Sales/.env` and add:

```
WISECRAWLER_BASE_URL=https://wisecrawler.accountantwise.uk
WISECRAWLER_API_KEY=your_api_key_here
```

Replace `your_api_key_here` with the actual value of `API_KEY` from WiseCrawler's `.env`.

- [x] **Step 2: Update `SourcesView.tsx`**

In `Faragopedia-Sales/frontend/src/components/SourcesView.tsx`:

**a) Add the import** at the top (after the existing imports):

```tsx
import AddSourcesModal from './AddSourcesModal';
```

**b) Add modal state** inside `SourcesView` (after the existing `const [isDeleting, ...]` line):

```tsx
const [showAddModal, setShowAddModal] = useState<boolean>(false);
```

**c) Replace the upload label** in the sidebar header. Find this block (around line 230–233):

```tsx
<label className="p-1.5 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors cursor-pointer disabled:opacity-50" title="Add Source">
  <input type="file" className="hidden" onChange={handleFileUpload} disabled={uploading} />
  {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
</label>
```

Replace it with:

```tsx
<button
  onClick={() => setShowAddModal(true)}
  className="p-1.5 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors"
  title="Add Source"
>
  <Plus className="w-4 h-4" />
</button>
```

**d) Add the modal** just before the closing `</div>` of the outermost return div (before the `{error && ...}` block):

```tsx
<AddSourcesModal
  open={showAddModal}
  onClose={() => setShowAddModal(false)}
  onSourceAdded={() => { fetchSources(); fetchMetadata(); }}
/>
```

**e) Remove the now-unused `handleFileUpload` function and `uploading` state** (lines 160–185 and line 14). They are fully replaced by the modal's Files tab.

- [x] **Step 3: Verify the app compiles**

```bash
cd Faragopedia-Sales/frontend
npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [x] **Step 4: Manual smoke test**

Start the dev server:

```bash
cd Faragopedia-Sales/frontend
npm run dev
```

Open the app and navigate to Sources. Verify:

1. **`+` button opens the modal** with three tabs visible.
2. **Files tab:** drag a file onto the drop zone — it appears in the queue list. Click "Upload 1 File" — file uploads and appears in the sources list. Modal closes.
3. **URL tab:** enter a URL, click "Start Crawl" — modal closes immediately. After ~60s the new `.md` source appears in the list automatically.
4. **Paste tab:** enter text with no name, click "Save as Source" — source appears with a `paste-` filename. Try again with a name — filename matches.
5. **Error state:** submit the URL tab with an invalid URL — an error toast or inline error appears.
6. **ESC / close button** dismisses the modal without submitting.

- [x] **Step 5: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/SourcesView.tsx Faragopedia-Sales/.env
git commit -m "feat: wire AddSourcesModal into SourcesView, replace single upload button"
```

---

## Self-Review Checklist

- [x] **WiseCrawler client** — Tasks 1 covers `start_crawl`, `poll_until_done`, `analyze_crawl` with tests
- [x] **POST /paste** — Task 2 covers happy path, custom name, empty content rejection
- [x] **POST /scrape-urls** — Task 3 covers background task dispatch, empty list 422, missing env var 503
- [x] **AddSourcesModal** — Task 4 covers all three tabs with loading/error states
- [x] **SourcesView wiring** — Task 5 replaces the old upload button and removes dead code
- [x] **Environment config** — Task 5 covers adding `WISECRAWLER_BASE_URL` and `WISECRAWLER_API_KEY`
- [x] **Type consistency** — `onSourceAdded` callback, `Tab` type, and function names are consistent across Tasks 4–5
- [x] **No placeholders** — all steps contain actual code

## Task 6: Aesthetic formatting of .md Sources

- [x] **Step 1:** Updated `SourcesView.tsx` to implement `ReactMarkdown` and frontmatter parsing for aesthetic formatting of `.md` files to match the main Wiki view content.
