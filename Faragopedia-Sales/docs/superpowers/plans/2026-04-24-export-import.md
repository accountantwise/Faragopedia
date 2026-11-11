# Wiki Export & Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing 5-file bundle export and two-step import with Full/Template export modes and a single atomic import endpoint; update the frontend to expose all four operations with clear descriptions.

**Architecture:** Two GET endpoints stream ZIP archives containing a `manifest.json` that declares `"type": "full"` or `"type": "template"`. A single POST `/import` validates the manifest, atomically restores files from a temp staging directory, then either reinitializes WikiManager (Full) or returns entity type data without writing `wiki_config.json` (Template). The SetupWizard handles Template imports by jumping directly to the schema review step pre-populated with the imported entity types; after a Template import via SettingsDrawer, data is passed via `sessionStorage` across the page reload.

**Tech Stack:** FastAPI + Python stdlib (`zipfile`, `shutil`, `tempfile`, `pathlib`), React 18 + TypeScript, pytest + FastAPI `TestClient`

---

## File Map

| File | Change |
|---|---|
| `backend/api/export_routes.py` | Full rewrite — 3 old endpoints → 2 export + 1 import |
| `backend/tests/test_export_routes.py` | Full rewrite — new test coverage for all 3 endpoints |
| `frontend/src/components/SettingsDrawer.tsx` | Modify — replace single Download with Full/Template export buttons + Import section |
| `frontend/src/components/SetupWizard.tsx` | Modify — replace two-step import handler with single-step; add `sessionStorage` template auto-detect on mount |

---

## Task 1: Backend — Export Endpoints (TDD)

**Files:**
- Rewrite: `backend/tests/test_export_routes.py`
- Rewrite: `backend/api/export_routes.py`

- [ ] **Step 1: Write failing tests for Full and Template export**

Replace the entire contents of `backend/tests/test_export_routes.py` with:

```python
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def dirs(tmp_path):
    schema_dir = tmp_path / "schema"
    wiki_dir = tmp_path / "wiki"
    sources_dir = tmp_path / "sources"
    archive_dir = tmp_path / "archive"
    snapshots_dir = tmp_path / "snapshots"

    for d in [schema_dir, wiki_dir, sources_dir, archive_dir, snapshots_dir]:
        d.mkdir()

    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "SCHEMA_TEMPLATE.md").write_text("# Template")
    (schema_dir / "company_profile.md").write_text("Acme Corp")
    (schema_dir / "wiki_config.json").write_text(json.dumps({
        "setup_complete": True,
        "wiki_name": "TestWiki",
        "org_name": "Acme",
        "org_description": "A company",
        "entity_types": [
            {"folder_name": "clients", "display_name": "Clients", "description": "Client orgs",
             "singular": "Client", "fields": [], "sections": ["Overview"]},
        ],
    }))

    clients_dir = wiki_dir / "clients"
    clients_dir.mkdir()
    (clients_dir / "_type.yaml").write_text("name: clients\n")
    (clients_dir / "acme.md").write_text("# Acme\n")
    (wiki_dir / "index.md").write_text("# Index\n")
    (wiki_dir / "log.md").write_text("# Log\n")
    (wiki_dir / "search-index.json").write_text("{}")

    metadata = {"doc.pdf": {"ingested": True, "ingested_at": "2026-01-01 00:00:00", "tags": []}}
    (sources_dir / ".metadata.json").write_text(json.dumps(metadata))
    (sources_dir / "doc.pdf").write_bytes(b"PDF content")
    (snapshots_dir / "20260101-000000.zip").write_bytes(b"snapshot data")

    return tmp_path


def _make_client(dirs):
    import backend.api.export_routes as er
    er.WIKI_DIR = str(dirs / "wiki")
    er.SOURCES_DIR = str(dirs / "sources")
    er.ARCHIVE_DIR = str(dirs / "archive")
    er.SNAPSHOTS_DIR = str(dirs / "snapshots")
    er.SCHEMA_DIR = str(dirs / "schema")

    app = FastAPI()
    app.include_router(er.export_router)
    return TestClient(app)


# ── Full export ────────────────────────────────────────────────────────────────

def test_full_export_returns_zip(dirs):
    r = _make_client(dirs).get("/bundle/full")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "faragopedia-full-" in r.headers["content-disposition"]


def test_full_export_manifest(dirs):
    r = _make_client(dirs).get("/bundle/full")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        m = json.loads(zf.read("manifest.json"))
    assert m["version"] == 1
    assert m["type"] == "full"
    assert "exported_at" in m


def test_full_export_includes_all_directories(dirs):
    r = _make_client(dirs).get("/bundle/full")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
    assert "schema/SCHEMA.md" in names
    assert "schema/wiki_config.json" in names
    assert "wiki/clients/_type.yaml" in names
    assert "wiki/clients/acme.md" in names
    assert "wiki/index.md" in names
    assert "sources/doc.pdf" in names
    assert "sources/.metadata.json" in names
    assert "snapshots/20260101-000000.zip" in names


# ── Template export ────────────────────────────────────────────────────────────

def test_template_export_returns_zip(dirs):
    r = _make_client(dirs).get("/bundle/template")
    assert r.status_code == 200
    assert "faragopedia-template-" in r.headers["content-disposition"]


def test_template_export_manifest(dirs):
    r = _make_client(dirs).get("/bundle/template")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        m = json.loads(zf.read("manifest.json"))
    assert m["version"] == 1
    assert m["type"] == "template"


def test_template_export_structure_only(dirs):
    r = _make_client(dirs).get("/bundle/template")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
    # Schema included in full
    assert "schema/SCHEMA.md" in names
    assert "schema/wiki_config.json" in names
    # Entity type structure included
    assert "wiki/clients/_type.yaml" in names
    # Page content excluded
    assert "wiki/clients/acme.md" not in names
    assert "wiki/index.md" not in names
    assert "wiki/search-index.json" not in names
    # Sources, archive, snapshots excluded
    assert "sources/doc.pdf" not in names
    assert "snapshots/20260101-000000.zip" not in names
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_export_routes.py -k "export" -v
```

Expected: `FAILED` — endpoints `/bundle/full` and `/bundle/template` do not exist yet.

- [ ] **Step 3: Rewrite export_routes.py with export endpoints**

Replace the entire contents of `backend/api/export_routes.py` with:

```python
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from agent.wiki_manager import WikiManager
from api.routes import (
    ARCHIVE_DIR,
    SNAPSHOTS_DIR,
    SOURCES_DIR,
    WIKI_DIR,
    set_wiki_manager,
)
from api.setup_routes import SCHEMA_DIR

export_router = APIRouter()

_APP_VERSION = "1.0.0"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@export_router.get("/bundle/full")
async def export_bundle_full():
    manifest = {
        "version": 1,
        "type": "full",
        "exported_at": _utcnow(),
        "app_version": _APP_VERSION,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for dir_name, dir_str in [
            ("schema", SCHEMA_DIR),
            ("wiki", WIKI_DIR),
            ("sources", SOURCES_DIR),
            ("archive", ARCHIVE_DIR),
            ("snapshots", SNAPSHOTS_DIR),
        ]:
            dir_path = Path(dir_str)
            if not dir_path.exists():
                continue
            for fp in sorted(dir_path.rglob("*")):
                if fp.is_file():
                    rel = str(fp.relative_to(dir_path)).replace("\\", "/")
                    zf.write(fp, f"{dir_name}/{rel}")
    buf.seek(0)
    ts = _timestamp()
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="faragopedia-full-{ts}.zip"'},
    )


@export_router.get("/bundle/template")
async def export_bundle_template():
    manifest = {
        "version": 1,
        "type": "template",
        "exported_at": _utcnow(),
        "app_version": _APP_VERSION,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        # Full schema directory
        schema_path = Path(SCHEMA_DIR)
        if schema_path.exists():
            for fp in sorted(schema_path.rglob("*")):
                if fp.is_file():
                    rel = str(fp.relative_to(schema_path)).replace("\\", "/")
                    zf.write(fp, f"schema/{rel}")
        # _type.yaml files only from wiki
        wiki_path = Path(WIKI_DIR)
        if wiki_path.exists():
            for fp in sorted(wiki_path.rglob("_type.yaml")):
                rel = str(fp.relative_to(wiki_path)).replace("\\", "/")
                zf.write(fp, f"wiki/{rel}")
    buf.seek(0)
    ts = _timestamp()
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="faragopedia-template-{ts}.zip"'},
    )
```

- [ ] **Step 4: Run export tests — expect pass**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_export_routes.py -k "export" -v
```

Expected: All export tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales"
git add backend/api/export_routes.py backend/tests/test_export_routes.py
git commit -m "feat: add Full and Template export endpoints with manifest"
```

---

## Task 2: Backend — Atomic Import Endpoint (TDD)

**Files:**
- Modify: `backend/tests/test_export_routes.py` (append import tests)
- Modify: `backend/api/export_routes.py` (append import endpoint + helpers)

- [ ] **Step 1: Write failing tests for import endpoint**

Append to `backend/tests/test_export_routes.py`:

```python
# ── Import helpers ─────────────────────────────────────────────────────────────

def _make_bundle(bundle_type: str) -> bytes:
    wiki_config = {
        "setup_complete": True,
        "wiki_name": "ImportedWiki",
        "org_name": "ImportedOrg",
        "org_description": "An imported org",
        "entity_types": [
            {"folder_name": "contacts", "display_name": "Contacts", "description": "People",
             "singular": "Contact", "fields": [], "sections": ["Overview"]},
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"version": 1, "type": bundle_type, "exported_at": "2026-04-24T00:00:00Z", "app_version": "1.0.0"}))
        zf.writestr("schema/SCHEMA.md", "# Schema")
        zf.writestr("schema/SCHEMA_TEMPLATE.md", "# Template")
        zf.writestr("schema/company_profile.md", "Imported Corp")
        zf.writestr("schema/wiki_config.json", json.dumps(wiki_config))
        zf.writestr("wiki/contacts/_type.yaml", "name: contacts\n")
        if bundle_type == "full":
            zf.writestr("wiki/index.md", "# Index")
            zf.writestr("wiki/log.md", "# Log")
            zf.writestr("wiki/contacts/alice.md", "# Alice")
            zf.writestr("sources/.metadata.json", json.dumps({"doc.pdf": {"ingested": True, "ingested_at": "2026-01-01 00:00:00", "tags": []}}))
            zf.writestr("sources/doc.pdf", "PDF")
            zf.writestr("snapshots/20260101.zip", "snap")
    buf.seek(0)
    return buf.read()


# ── Import tests ───────────────────────────────────────────────────────────────

def test_full_import_restores_all_directories(dirs):
    client = _make_client(dirs)
    r = client.post("/import", files={"file": ("bundle.zip", _make_bundle("full"), "application/zip")})
    assert r.status_code == 200
    assert r.json()["type"] == "full"
    # Imported content present
    assert (dirs / "wiki" / "contacts" / "alice.md").exists()
    assert (dirs / "wiki" / "contacts" / "_type.yaml").exists()
    assert (dirs / "sources" / ".metadata.json").exists()
    assert (dirs / "sources" / "doc.pdf").exists()
    assert (dirs / "schema" / "SCHEMA.md").exists()
    assert (dirs / "schema" / "wiki_config.json").exists()
    # Previous wiki content replaced
    assert not (dirs / "wiki" / "clients" / "acme.md").exists()


def test_template_import_writes_schema_and_type_yamls(dirs):
    client = _make_client(dirs)
    r = client.post("/import", files={"file": ("bundle.zip", _make_bundle("template"), "application/zip")})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "template"
    # _type.yaml written
    assert (dirs / "wiki" / "contacts" / "_type.yaml").exists()
    # Schema files written
    assert (dirs / "schema" / "SCHEMA.md").exists()
    # wiki_config.json NOT written — wizard writes it after user confirms
    assert not (dirs / "schema" / "wiki_config.json").exists()


def test_template_import_returns_entity_types_and_meta(dirs):
    client = _make_client(dirs)
    r = client.post("/import", files={"file": ("bundle.zip", _make_bundle("template"), "application/zip")})
    data = r.json()
    assert data["wiki_name"] == "ImportedWiki"
    assert data["org_name"] == "ImportedOrg"
    assert data["org_description"] == "An imported org"
    assert any(et["folder_name"] == "contacts" for et in data["entity_types"])
    assert "contacts" in data["folders"]


def test_import_rejects_missing_manifest(dirs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("schema/wiki_config.json", "{}")
    buf.seek(0)
    r = _make_client(dirs).post("/import", files={"file": ("bad.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400
    assert "manifest" in r.json()["detail"].lower()


def test_import_rejects_incompatible_version(dirs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"version": 99, "type": "full"}))
        zf.writestr("schema/wiki_config.json", "{}")
    buf.seek(0)
    r = _make_client(dirs).post("/import", files={"file": ("bad.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400
    assert "version" in r.json()["detail"].lower()


def test_import_rejects_unknown_type(dirs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"version": 1, "type": "unknown"}))
        zf.writestr("schema/wiki_config.json", "{}")
    buf.seek(0)
    r = _make_client(dirs).post("/import", files={"file": ("bad.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400
    assert "type" in r.json()["detail"].lower()


def test_import_rejects_missing_wiki_config(dirs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"version": 1, "type": "full"}))
    buf.seek(0)
    r = _make_client(dirs).post("/import", files={"file": ("bad.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400
    assert "wiki_config" in r.json()["detail"].lower()


def test_import_rejects_invalid_zip(dirs):
    r = _make_client(dirs).post("/import", files={"file": ("bad.zip", b"not a zip", "application/zip")})
    assert r.status_code == 400
```

- [ ] **Step 2: Run import tests — expect failure**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_export_routes.py -k "import" -v
```

Expected: `FAILED` — `POST /import` returns 404.

- [ ] **Step 3: Append import endpoint and helpers to export_routes.py**

Append the following to the end of `backend/api/export_routes.py`:

```python

@export_router.post("/import")
async def import_bundle(file: UploadFile = File(...)):
    content = await file.read()

    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive")

    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
        names = set(zf.namelist())

        if "manifest.json" not in names:
            raise HTTPException(status_code=400, detail="Missing manifest.json — not a Faragopedia bundle")

        manifest = json.loads(zf.read("manifest.json"))

        if manifest.get("version") != 1:
            raise HTTPException(
                status_code=400,
                detail=f"Incompatible bundle version {manifest.get('version')!r}. Expected 1.",
            )

        bundle_type = manifest.get("type")
        if bundle_type not in ("full", "template"):
            raise HTTPException(status_code=400, detail=f"Unknown bundle type {bundle_type!r}")

        if "schema/wiki_config.json" not in names:
            raise HTTPException(status_code=400, detail="Missing schema/wiki_config.json in bundle")

        wiki_config = json.loads(zf.read("schema/wiki_config.json"))

        with tempfile.TemporaryDirectory() as staging_str:
            staging = Path(staging_str)
            zf.extractall(staging)

            if bundle_type == "full":
                _restore_full(staging)
                _reinit_wiki_manager()
                return {"status": "ok", "type": "full"}
            else:
                entity_types = _restore_template(staging, wiki_config)
                return {
                    "status": "ok",
                    "type": "template",
                    "wiki_name": wiki_config.get("wiki_name", ""),
                    "org_name": wiki_config.get("org_name", ""),
                    "org_description": wiki_config.get("org_description", ""),
                    "entity_types": entity_types,
                    "folders": [et["folder_name"] for et in entity_types],
                }


def _restore_full(staging: Path) -> None:
    for dir_name, dir_str in [
        ("schema", SCHEMA_DIR),
        ("wiki", WIKI_DIR),
        ("sources", SOURCES_DIR),
        ("archive", ARCHIVE_DIR),
        ("snapshots", SNAPSHOTS_DIR),
    ]:
        target = Path(dir_str)
        source = staging / dir_name
        if target.exists():
            shutil.rmtree(target)
        if source.exists():
            shutil.copytree(source, target)
        else:
            target.mkdir(parents=True, exist_ok=True)


def _restore_template(staging: Path, wiki_config: dict) -> list:
    # Restore schema directory
    schema_target = Path(SCHEMA_DIR)
    schema_staging = staging / "schema"
    if schema_target.exists():
        shutil.rmtree(schema_target)
    if schema_staging.exists():
        shutil.copytree(schema_staging, schema_target)
    schema_target.mkdir(parents=True, exist_ok=True)

    # Remove wiki_config.json — setup wizard writes it after user confirms
    config_path = schema_target / "wiki_config.json"
    if config_path.exists():
        config_path.unlink()

    # Clear wiki, restore only _type.yaml files
    wiki_target = Path(WIKI_DIR)
    if wiki_target.exists():
        shutil.rmtree(wiki_target)
    wiki_target.mkdir(parents=True)

    wiki_staging = staging / "wiki"
    if wiki_staging.exists():
        for type_yaml in sorted(wiki_staging.rglob("_type.yaml")):
            rel = type_yaml.relative_to(wiki_staging)
            dest = wiki_target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(type_yaml, dest)

    return wiki_config.get("entity_types", [])


def _reinit_wiki_manager() -> None:
    wm = WikiManager(
        sources_dir=SOURCES_DIR,
        wiki_dir=WIKI_DIR,
        archive_dir=ARCHIVE_DIR,
        snapshots_dir=SNAPSHOTS_DIR,
        schema_dir=SCHEMA_DIR,
    )
    set_wiki_manager(wm)
```

- [ ] **Step 4: Run all export_routes tests — expect pass**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/backend"
python -m pytest tests/test_export_routes.py -v
```

Expected: All tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales"
git add backend/api/export_routes.py backend/tests/test_export_routes.py
git commit -m "feat: atomic import endpoint — Full restores all dirs, Template seeds schema for wizard"
```

---

## Task 3: Frontend — SettingsDrawer Export/Import UI

**Files:**
- Modify: `frontend/src/components/SettingsDrawer.tsx`

The current file is 166 lines. The existing `handleDownload` function (lines 38–53) hits the old `/export/bundle` endpoint and must be replaced. The export section (lines 129–150) must be rewritten with two export buttons and an import section.

- [ ] **Step 1: Add Upload icon import**

In `SettingsDrawer.tsx`, find the lucide-react import line (it imports icons like `Download`, `Moon`, `Sun`, etc.) and add `Upload` to it. For example if the current line is:

```typescript
import { Download, Moon, Sun, X } from 'lucide-react';
```

Change it to:

```typescript
import { Download, Moon, Sun, Upload, X } from 'lucide-react';
```

(Add `Upload` alphabetically among the existing icons — exact set will differ.)

- [ ] **Step 2: Replace handleDownload with three handlers and two state vars**

Find the `handleDownload` function (lines ~38–53). Replace it with the following block (keeping the surrounding code intact):

```typescript
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState('');

  const handleExportFull = () => {
    window.open(`${API_BASE}/export/bundle/full`, '_blank');
  };

  const handleExportTemplate = () => {
    window.open(`${API_BASE}/export/bundle/template`, '_blank');
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.zip';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      setImportLoading(true);
      setImportError('');
      const form = new FormData();
      form.append('file', file);
      try {
        const r = await fetch(`${API_BASE}/export/import`, { method: 'POST', body: form });
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: 'Import failed' }));
          setImportError(err.detail || 'Import failed');
          return;
        }
        const data = await r.json();
        if (data.type === 'template') {
          sessionStorage.setItem('templateImport', JSON.stringify({
            wiki_name: data.wiki_name,
            org_name: data.org_name,
            org_description: data.org_description,
            entity_types: data.entity_types,
          }));
        }
        window.location.reload();
      } catch {
        setImportError('Import failed. Please try again.');
      } finally {
        setImportLoading(false);
      }
    };
    input.click();
  };
```

Note: `useState` is already imported in this file. `API_BASE` is already imported from `../config`.

- [ ] **Step 3: Replace the Export section in the JSX**

Find the existing Export section (lines ~129–150, contains a single "Download Wiki Bundle" button). Replace it entirely with:

```tsx
            {/* Export */}
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider px-1">Export</h3>
              <button
                onClick={handleExportFull}
                className="w-full flex items-start gap-3 px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-left transition-colors"
              >
                <Download size={16} className="mt-0.5 shrink-0 text-gray-500 dark:text-gray-400" />
                <div>
                  <div className="text-sm font-medium text-gray-700 dark:text-gray-300">Export Full</div>
                  <div className="text-xs text-gray-500 dark:text-gray-500">All pages, sources, archive &amp; snapshots</div>
                </div>
              </button>
              <button
                onClick={handleExportTemplate}
                className="w-full flex items-start gap-3 px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-left transition-colors"
              >
                <Download size={16} className="mt-0.5 shrink-0 text-gray-500 dark:text-gray-400" />
                <div>
                  <div className="text-sm font-medium text-gray-700 dark:text-gray-300">Export Template</div>
                  <div className="text-xs text-gray-500 dark:text-gray-500">Schema &amp; folder structure only — no content</div>
                </div>
              </button>
            </div>

            {/* Import */}
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider px-1">Import</h3>
              <button
                onClick={handleImport}
                disabled={importLoading}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-left transition-colors disabled:opacity-50"
              >
                <Upload size={16} className="shrink-0 text-gray-500 dark:text-gray-400" />
                <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {importLoading ? 'Importing…' : 'Import Bundle'}
                </div>
              </button>
              {importError && (
                <p className="text-xs text-red-500 dark:text-red-400 px-1">{importError}</p>
              )}
            </div>
```

- [ ] **Step 4: Verify the app compiles**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/frontend"
npm run build 2>&1 | tail -20
```

Expected: Build succeeds with no TypeScript errors. If there are errors, fix them before continuing.

- [ ] **Step 5: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales"
git add frontend/src/components/SettingsDrawer.tsx
git commit -m "feat: replace single export button with Full/Template export and Import in SettingsDrawer"
```

---

## Task 4: Frontend — SetupWizard Import Flow + Template Auto-Detect

**Files:**
- Modify: `frontend/src/components/SetupWizard.tsx`

The wizard currently uses a two-step import: `handleImportFile` uploads to `/export/import` (validation only), then `handleConfirm` calls `/export/import/finalize`. Both must be replaced with a single-step flow. A new mount effect auto-detects template data from `sessionStorage` (written by SettingsDrawer after a Template import + reload).

- [ ] **Step 1: Add templateImport sessionStorage auto-detect on mount**

In `SetupWizard.tsx`, find the existing `useEffect` that handles reconfigure mode prefill (lines ~244–254). Add a NEW `useEffect` immediately after it:

```typescript
  // Auto-detect template import data written by SettingsDrawer before page reload
  useEffect(() => {
    if (reconfigureMode) return;
    const raw = sessionStorage.getItem('templateImport');
    if (!raw) return;
    sessionStorage.removeItem('templateImport');
    try {
      const data = JSON.parse(raw);
      if (data.wiki_name) setWikiName(data.wiki_name);
      if (data.org_name) setOrgName(data.org_name);
      if (data.org_description) setOrgDescription(data.org_description);
      if (Array.isArray(data.entity_types) && data.entity_types.length > 0) {
        setEntityTypes(data.entity_types);
        setStep(2);
      }
    } catch {
      // Malformed sessionStorage entry — ignore and start fresh
    }
  }, []);
```

- [ ] **Step 2: Replace handleImportFile with single-step import**

Find the existing `handleImportFile` function (lines ~309–335). Replace the entire function with:

```typescript
  const handleImportFile = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.zip';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      setImportLoading(true);
      setImportError('');
      const form = new FormData();
      form.append('file', file);
      try {
        const r = await fetch(`${API_BASE}/export/import`, { method: 'POST', body: form });
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: 'Import failed' }));
          setImportError(err.detail || 'Import failed');
          return;
        }
        const data = await r.json();
        if (data.type === 'full') {
          window.location.reload();
          return;
        }
        // Template: pre-populate wizard with imported schema and jump to step 2
        if (data.wiki_name) setWikiName(data.wiki_name);
        if (data.org_name) setOrgName(data.org_name);
        if (data.org_description) setOrgDescription(data.org_description);
        if (Array.isArray(data.entity_types) && data.entity_types.length > 0) {
          setEntityTypes(data.entity_types);
        }
        setStep(2);
      } catch {
        setImportError('Import failed. Please try again.');
      } finally {
        setImportLoading(false);
      }
    };
    input.click();
  };
```

- [ ] **Step 3: Remove or neutralize handleConfirm**

Find `handleConfirm` (lines ~337–363) — it calls `/export/import/finalize` which no longer exists. Since Template imports now go through the normal wizard flow ending with `handleLaunch` → `POST /setup/complete`, this function is dead code. Delete the entire `handleConfirm` function.

Also find any JSX that calls `handleConfirm` (likely a button in step 3's confirm view) and replace the `onClick={handleConfirm}` with `onClick={handleLaunch}`. The `importedConfig` state variable and its type declaration can be removed as well since they are no longer used.

- [ ] **Step 4: Verify the app compiles**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales/frontend"
npm run build 2>&1 | tail -20
```

Expected: No TypeScript errors. If `importedConfig` removal causes type errors elsewhere in the file, remove those references too.

- [ ] **Step 5: Commit**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales"
git add frontend/src/components/SetupWizard.tsx
git commit -m "feat: single-step import flow — Full reloads, Template pre-populates wizard step 2"
```

---

## Task 5: Integration Smoke Test

Verify the full feature works end-to-end before declaring done.

- [ ] **Step 1: Start the app**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales"
docker compose up --build -d
```

Wait ~15 seconds for containers to be ready.

- [ ] **Step 2: Test Full export**

Open `http://localhost:5173`, open Settings (gear icon), click **Export Full**. Verify a `faragopedia-full-*.zip` downloads. Open the zip and confirm it contains `manifest.json`, `wiki/`, `sources/`, `schema/wiki_config.json`, and `sources/.metadata.json`.

- [ ] **Step 3: Test Template export**

Click **Export Template**. Open the zip and confirm: `manifest.json` with `"type": "template"`, `schema/` files present, `wiki/{folder}/_type.yaml` files present, NO `.md` page files, NO `sources/`, NO `snapshots/`.

- [ ] **Step 4: Test Full import on fresh server**

Stop containers. Delete or rename `Faragopedia-Sales/wiki/wiki_config.json` (from `schema/` folder) to simulate a fresh server. Restart containers. The Setup Wizard should appear. Upload the Full zip from step 2. Verify the page reloads and the wiki is ready with all content intact.

- [ ] **Step 5: Test Template import on fresh server**

Simulate fresh server again (remove `schema/wiki_config.json`). Restart. Upload the Template zip. Verify the wizard jumps to step 2 with entity types pre-populated from the bundle. Modify one entity type name. Click through to confirm. Verify the wiki initializes fresh with the modified schema.

- [ ] **Step 6: Final commit if any fixes were made during smoke test**

```bash
cd "c:/Users/Colacho/Nextcloud/AI/VS Code/Faragopedia-V2/Faragopedia-Sales"
git add -p
git commit -m "fix: smoke test corrections for export/import feature"
```
