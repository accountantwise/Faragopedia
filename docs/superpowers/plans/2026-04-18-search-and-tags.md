# Search & Tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-view keyword search (client-side JSON index) and a free-form tag system (shared vocabulary across wiki pages and sources) to Faragopedia-Sales.

**Architecture:** A sync `_rebuild_search_index()` on `WikiManager` writes `wiki/search-index.json` after every write operation. Tags live in YAML frontmatter on wiki pages and in `.metadata.json` for sources. The frontend fetches the index once on view load and filters client-side with ~150ms debounce.

**Tech Stack:** Python/FastAPI backend, LangChain for LLM calls, React/TypeScript frontend, Tailwind CSS, Lucide icons (already in use).

**Spec:** `docs/superpowers/specs/2026-04-18-search-and-tags-design.md`

---

## File Map

**Create:**
- `Faragopedia-Sales/backend/tests/test_search_and_tags.py`

**Modify:**
- `Faragopedia-Sales/backend/agent/wiki_manager.py` — add helpers, index builder, tag management, tag suggestion, update `save_page_content` return type
- `Faragopedia-Sales/backend/api/routes.py` — add 5 new endpoints, update `PUT /pages/{path}` response
- `Faragopedia-Sales/frontend/src/components/WikiView.tsx` — add search bar, results panel, tag chips, filter row, AI suggestion UI
- `Faragopedia-Sales/frontend/src/components/SourcesView.tsx` — add search bar, tag chips, filter row

---

## Task 1: WikiManager — parsing helpers + search index builder

**Files:**
- Modify: `Faragopedia-Sales/backend/agent/wiki_manager.py`
- Create: `Faragopedia-Sales/backend/tests/test_search_and_tags.py`

- [ ] **Step 1: Write the failing tests**

Create `Faragopedia-Sales/backend/tests/test_search_and_tags.py`:

```python
import json
import os
import pytest
import yaml
from unittest.mock import patch
from agent.wiki_manager import WikiManager


@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "AI_PROVIDER": "openai",
        "AI_MODEL": "gpt-4o-mini",
    }):
        yield


@pytest.fixture
def wiki_env(tmp_path):
    sources = tmp_path / "sources"
    wiki = tmp_path / "wiki"
    archive = tmp_path / "archive"
    sources.mkdir()
    wiki.mkdir()
    # Create a clients entity folder with _type.yaml
    clients = wiki / "clients"
    clients.mkdir()
    (clients / "_type.yaml").write_text(
        yaml.dump({"name": "Clients", "singular": "client", "fields": [], "sections": []})
    )
    return str(sources), str(wiki), str(archive)


def make_manager(wiki_env):
    sources, wiki, archive = wiki_env
    return WikiManager(sources_dir=sources, wiki_dir=wiki, archive_dir=archive)


def write_page(wiki_dir, rel_path, content):
    full = os.path.join(wiki_dir, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


# ── Parsing helpers ───────────────────────────────────────────────────────────

def test_parse_frontmatter_with_tags(wiki_env):
    manager = make_manager(wiki_env)
    content = "---\nname: Acme Corp\ntags:\n- wedding\n- VIP\n---\n\n# Acme Corp\n\nBody."
    fm, body = manager._parse_frontmatter(content)
    assert fm["name"] == "Acme Corp"
    assert fm["tags"] == ["wedding", "VIP"]
    assert "Body." in body


def test_parse_frontmatter_no_yaml(wiki_env):
    manager = make_manager(wiki_env)
    content = "# Just a heading\n\nNo frontmatter."
    fm, body = manager._parse_frontmatter(content)
    assert fm == {}
    assert "Just a heading" in body


def test_render_frontmatter_roundtrip(wiki_env):
    manager = make_manager(wiki_env)
    content = "---\nname: Test\ntags:\n- foo\n---\n\nBody text."
    fm, body = manager._parse_frontmatter(content)
    rendered = manager._render_frontmatter(fm, body)
    fm2, body2 = manager._parse_frontmatter(rendered)
    assert fm2["name"] == "Test"
    assert fm2["tags"] == ["foo"]
    assert "Body text." in body2


def test_strip_markdown(wiki_env):
    manager = make_manager(wiki_env)
    text = "## Header\n\n**bold** and [[clients/foo]] and *italic* and [link](url)"
    result = manager._strip_markdown(text)
    assert "##" not in result
    assert "**" not in result
    assert "[[" not in result
    assert "Header" in result
    assert "bold" in result


# ── Search index builder ──────────────────────────────────────────────────────

def test_rebuild_search_index_creates_file(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme-corp.md",
               "---\ntype: client\nname: Acme Corp\ntags:\n- wedding\n---\n\n# Acme Corp\n\nContent here.")

    manager._rebuild_search_index()

    index_path = os.path.join(wiki, "search-index.json")
    assert os.path.exists(index_path)
    with open(index_path) as f:
        index = json.load(f)
    assert len(index["pages"]) == 1
    assert index["pages"][0]["path"] == "clients/acme-corp.md"
    assert index["pages"][0]["title"] == "Acme Corp"
    assert index["pages"][0]["tags"] == ["wedding"]
    assert "Content here" in index["pages"][0]["content_preview"]


def test_rebuild_search_index_includes_sources(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    src_file = os.path.join(sources, "brief.pdf")
    with open(src_file, "w") as f:
        f.write("dummy")
    # Manually write metadata with tags
    meta = {"brief.pdf": {"ingested": True, "ingested_at": "2026-01-01", "tags": ["brief"]}}
    meta_path = os.path.join(sources, ".metadata.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f)

    manager._rebuild_search_index()

    with open(os.path.join(wiki, "search-index.json")) as f:
        index = json.load(f)
    src_entry = next((s for s in index["sources"] if s["filename"] == "brief.pdf"), None)
    assert src_entry is not None
    assert src_entry["tags"] == ["brief"]


def test_init_creates_index_if_missing(wiki_env):
    sources, wiki, archive = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags: []\n---\n\n# Test\n\nHello.")
    # Index should not exist yet
    assert not os.path.exists(os.path.join(wiki, "search-index.json"))
    make_manager(wiki_env)
    assert os.path.exists(os.path.join(wiki, "search-index.json"))
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py -v
```
Expected: `AttributeError: 'WikiManager' object has no attribute '_parse_frontmatter'` (or similar)

- [ ] **Step 3: Add helpers and `_rebuild_search_index` to WikiManager**

Add these methods to `WikiManager` in `backend/agent/wiki_manager.py`, after `_init_llm` (around line 146):

```python
def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
    match = re.match(r'^---\n(.*?)\n---\n?(.*)', content, re.DOTALL)
    if match:
        try:
            fm = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        return fm, match.group(2)
    return {}, content

def _render_frontmatter(self, frontmatter: dict, body: str) -> str:
    fm_str = yaml.dump(frontmatter, default_flow_style=False,
                       allow_unicode=True, sort_keys=False).rstrip()
    return f"---\n{fm_str}\n---\n{body}"

def _strip_markdown(self, text: str) -> str:
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[*_`~]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def _rebuild_search_index(self) -> None:
    pages = []
    for rel_path in self.list_pages():
        try:
            content = self.get_page_content(rel_path)
            fm, body = self._parse_frontmatter(content)
            entity_type = rel_path.split("/")[0]
            title = fm.get("name") or fm.get("title") or \
                rel_path.split("/")[-1].replace("-", " ").replace("_", " ").title()
            tags = fm.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            pages.append({
                "path": rel_path,
                "title": str(title),
                "entity_type": entity_type,
                "tags": [str(t) for t in tags],
                "frontmatter": {k: v for k, v in fm.items() if k != "tags"},
                "content_preview": self._strip_markdown(body)[:500],
            })
        except Exception:
            continue

    raw_meta = self._load_metadata()
    sources = []
    for filename in self.list_sources():
        m = raw_meta.get(filename, {})
        tags = m.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        sources.append({
            "filename": filename,
            "display_name": filename,
            "tags": [str(t) for t in tags],
            "metadata": {
                "ingested": m.get("ingested", False),
                "upload_date": m.get("ingested_at"),
            },
        })

    index = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "pages": pages,
        "sources": sources,
    }
    index_path = os.path.join(self.wiki_dir, "search-index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
```

Also update `__init__` — after the `os.makedirs` loop (around line 113), add:

```python
        # Build search index on startup if missing
        index_path = os.path.join(self.wiki_dir, "search-index.json")
        if not os.path.exists(index_path):
            self._rebuild_search_index()
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py::test_parse_frontmatter_with_tags \
       tests/test_search_and_tags.py::test_parse_frontmatter_no_yaml \
       tests/test_search_and_tags.py::test_render_frontmatter_roundtrip \
       tests/test_search_and_tags.py::test_strip_markdown \
       tests/test_search_and_tags.py::test_rebuild_search_index_creates_file \
       tests/test_search_and_tags.py::test_rebuild_search_index_includes_sources \
       tests/test_search_and_tags.py::test_init_creates_index_if_missing -v
```
Expected: all 7 PASS

- [ ] **Step 5: Run full existing test suite to check for regressions**

```
cd Faragopedia-Sales/backend
pytest tests/ -v
```
Expected: all previously passing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/backend/agent/wiki_manager.py \
        Faragopedia-Sales/backend/tests/test_search_and_tags.py
git commit -m "feat: add WikiManager parsing helpers and search index builder"
```

---

## Task 2: Hook `_rebuild_search_index` into all write operations

**Files:**
- Modify: `Faragopedia-Sales/backend/agent/wiki_manager.py`
- Modify: `Faragopedia-Sales/backend/tests/test_search_and_tags.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_search_and_tags.py`:

```python
# ── Index sync on writes ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_page_content_rebuilds_index(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme.md",
               "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nOld content.")

    new_content = "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nNew content."
    await manager.save_page_content("clients/acme.md", new_content)

    with open(os.path.join(wiki, "search-index.json")) as f:
        index = json.load(f)
    entry = next(p for p in index["pages"] if p["path"] == "clients/acme.md")
    assert "New content" in entry["content_preview"]


@pytest.mark.asyncio
async def test_archive_page_removes_from_index(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/gone.md",
               "---\nname: Gone\ntags: []\n---\n\n# Gone\n\nContent.")
    manager._rebuild_search_index()

    await manager.archive_page("clients/gone.md")

    with open(os.path.join(wiki, "search-index.json")) as f:
        index = json.load(f)
    assert not any(p["path"] == "clients/gone.md" for p in index["pages"])


@pytest.mark.asyncio
async def test_restore_page_adds_to_index(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/restored.md",
               "---\nname: Restored\ntags: []\n---\n\n# Restored\n\nContent.")
    await manager.archive_page("clients/restored.md")

    await manager.restore_page("clients/restored.md")

    with open(os.path.join(wiki, "search-index.json")) as f:
        index = json.load(f)
    assert any(p["path"] == "clients/restored.md" for p in index["pages"])
```

- [ ] **Step 2: Run new tests to verify they fail**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py::test_save_page_content_rebuilds_index \
       tests/test_search_and_tags.py::test_archive_page_removes_from_index \
       tests/test_search_and_tags.py::test_restore_page_adds_to_index -v
```
Expected: FAIL — index not updated after save/archive/restore

- [ ] **Step 3: Hook `_rebuild_search_index` into write operations**

In `wiki_manager.py`, update `save_page_content` (line 796) to call `_rebuild_search_index` after writing. Change:

```python
async def save_page_content(self, page_path: str, content: str):
    """
    Save content to a wiki page and log the action.
    """
    path = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
    async with self._write_lock:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.update_index()
        self._append_to_log("edit", f"Updated {page_path}")
```

to:

```python
async def save_page_content(self, page_path: str, content: str) -> list[str]:
    """
    Save content to a wiki page and log the action.
    Returns AI-suggested tags not already on the page (populated in Task 4).
    """
    path = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
    async with self._write_lock:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.update_index()
        self._append_to_log("edit", f"Updated {page_path}")
    self._rebuild_search_index()
    return []
```

Update `archive_page` (line 595) — add `self._rebuild_search_index()` after the lock block:

```python
async def archive_page(self, page_path: str):
    """Move a wiki page to the archive."""
    src = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
    dest = os.path.join(self.archive_wiki_dir, page_path.replace("/", os.sep))
    async with self._write_lock:
        if not os.path.exists(src):
            raise FileNotFoundError(f"Page not found: {page_path}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            base, ext = os.path.splitext(dest)
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            dest = f"{base}_{timestamp}{ext}"
        shutil.move(src, dest)
        self.update_index()
        self._append_to_log("archive", f"Archived {page_path}")
    self._rebuild_search_index()
```

Also update `create_new_page` (line 440) — add `self._rebuild_search_index()` after the lock block (after `self.update_index()` and `self._append_to_log`):

```python
        # end of async with self._write_lock block
        self._rebuild_search_index()
        return rel_path
```

Update `restore_page` (line 629) — add `self._rebuild_search_index()` after the lock block:

```python
async def restore_page(self, filename: str):
    """Move an archived wiki page back to the main wiki directory."""
    src = os.path.join(self.archive_wiki_dir, filename)
    dest = os.path.join(self.wiki_dir, filename)
    async with self._write_lock:
        if not os.path.exists(src):
            raise FileNotFoundError(f"Archived page not found: {filename}")
        if os.path.exists(dest):
            base, ext = os.path.splitext(filename)
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            dest = os.path.join(self.wiki_dir, f"{base}_{timestamp}{ext}")
        shutil.move(src, dest)
        self.update_index()
        self._append_to_log("restore", f"Restored {filename}")
    self._rebuild_search_index()
```

- [ ] **Step 4: Run new tests to verify they pass**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py::test_save_page_content_rebuilds_index \
       tests/test_search_and_tags.py::test_archive_page_removes_from_index \
       tests/test_search_and_tags.py::test_restore_page_adds_to_index -v
```
Expected: all 3 PASS

- [ ] **Step 5: Run full test suite**

```
cd Faragopedia-Sales/backend
pytest tests/ -v
```
Expected: all previously passing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/backend/agent/wiki_manager.py \
        Faragopedia-Sales/backend/tests/test_search_and_tags.py
git commit -m "feat: rebuild search index on page save, archive, and restore"
```

---

## Task 3: WikiManager — tag management methods

**Files:**
- Modify: `Faragopedia-Sales/backend/agent/wiki_manager.py`
- Modify: `Faragopedia-Sales/backend/tests/test_search_and_tags.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_search_and_tags.py`:

```python
# ── Tag management ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_page_tags_writes_frontmatter(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme.md",
               "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nContent.")

    await manager.update_page_tags("clients/acme.md", ["wedding", "VIP"])

    content = manager.get_page_content("clients/acme.md")
    fm, _ = manager._parse_frontmatter(content)
    assert fm["tags"] == ["wedding", "VIP"]


@pytest.mark.asyncio
async def test_update_page_tags_rebuilds_index(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme.md",
               "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nContent.")

    await manager.update_page_tags("clients/acme.md", ["commercial"])

    with open(os.path.join(wiki, "search-index.json")) as f:
        index = json.load(f)
    entry = next(p for p in index["pages"] if p["path"] == "clients/acme.md")
    assert "commercial" in entry["tags"]


def test_update_source_tags_writes_metadata(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    src = os.path.join(sources, "brief.txt")
    with open(src, "w") as f:
        f.write("content")
    manager.mark_source_ingested("brief.txt", True)

    manager.update_source_tags("brief.txt", ["brief", "wedding"])

    raw = manager._load_metadata()
    assert raw["brief.txt"]["tags"] == ["brief", "wedding"]


def test_update_source_tags_rebuilds_index(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    src = os.path.join(sources, "brief.txt")
    with open(src, "w") as f:
        f.write("content")

    manager.update_source_tags("brief.txt", ["brief"])

    with open(os.path.join(wiki, "search-index.json")) as f:
        index = json.load(f)
    entry = next((s for s in index["sources"] if s["filename"] == "brief.txt"), None)
    assert entry is not None
    assert "brief" in entry["tags"]


def test_get_sources_metadata_includes_tags_default(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    src = os.path.join(sources, "file.txt")
    with open(src, "w") as f:
        f.write("x")

    meta = manager.get_sources_metadata()
    assert "tags" in meta["file.txt"]
    assert meta["file.txt"]["tags"] == []
```

- [ ] **Step 2: Run new tests to verify they fail**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py::test_update_page_tags_writes_frontmatter \
       tests/test_search_and_tags.py::test_update_page_tags_rebuilds_index \
       tests/test_search_and_tags.py::test_update_source_tags_writes_metadata \
       tests/test_search_and_tags.py::test_update_source_tags_rebuilds_index \
       tests/test_search_and_tags.py::test_get_sources_metadata_includes_tags_default -v
```
Expected: all FAIL

- [ ] **Step 3: Add tag management methods to WikiManager**

Add these methods after `_rebuild_search_index`:

```python
async def update_page_tags(self, page_path: str, tags: list[str]) -> None:
    """Replace the tags list on a wiki page's YAML frontmatter and rebuild index."""
    path = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
    if not os.path.exists(path):
        raise FileNotFoundError(f"Page not found: {page_path}")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    fm, body = self._parse_frontmatter(content)
    fm["tags"] = [str(t).lower().strip() for t in tags]
    new_content = self._render_frontmatter(fm, body)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    self._rebuild_search_index()

def update_source_tags(self, filename: str, tags: list[str]) -> None:
    """Replace the tags list on a source's metadata entry and rebuild index."""
    metadata = self._load_metadata()
    entry = metadata.get(filename, {"ingested": False, "ingested_at": None})
    entry["tags"] = [str(t).lower().strip() for t in tags]
    metadata[filename] = entry
    self._save_metadata(metadata)
    self._rebuild_search_index()
```

Update `get_sources_metadata` to include `tags` default (replace the existing method at line 160):

```python
def get_sources_metadata(self) -> Dict:
    """Return metadata for all current sources."""
    metadata = self._load_metadata()
    current_sources = self.list_sources()
    result = {}
    for s in current_sources:
        stored = metadata.get(s, {})
        result[s] = {
            "ingested": stored.get("ingested", False),
            "ingested_at": stored.get("ingested_at", None),
            "tags": stored.get("tags", []),
        }
    return result
```

- [ ] **Step 4: Run new tests to verify they pass**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py::test_update_page_tags_writes_frontmatter \
       tests/test_search_and_tags.py::test_update_page_tags_rebuilds_index \
       tests/test_search_and_tags.py::test_update_source_tags_writes_metadata \
       tests/test_search_and_tags.py::test_update_source_tags_rebuilds_index \
       tests/test_search_and_tags.py::test_get_sources_metadata_includes_tags_default -v
```
Expected: all 5 PASS

- [ ] **Step 5: Run full test suite**

```
cd Faragopedia-Sales/backend
pytest tests/ -v
```
Expected: all previously passing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/backend/agent/wiki_manager.py \
        Faragopedia-Sales/backend/tests/test_search_and_tags.py
git commit -m "feat: add update_page_tags and update_source_tags to WikiManager"
```

---

## Task 4: WikiManager — `_suggest_tags` + hook into save/ingest

**Files:**
- Modify: `Faragopedia-Sales/backend/agent/wiki_manager.py`
- Modify: `Faragopedia-Sales/backend/tests/test_search_and_tags.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_search_and_tags.py`:

```python
# ── Tag suggestion ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggest_tags_returns_list(wiki_env):
    manager = make_manager(wiki_env)
    from unittest.mock import AsyncMock, MagicMock
    mock_response = MagicMock()
    mock_response.content = '["wedding", "commercial", "VIP"]'
    manager.llm.ainvoke = AsyncMock(return_value=mock_response)

    tags = await manager._suggest_tags("Some page content about weddings.", "clients")
    assert isinstance(tags, list)
    assert all(isinstance(t, str) for t in tags)
    assert len(tags) <= 5


@pytest.mark.asyncio
async def test_suggest_tags_returns_empty_on_error(wiki_env):
    manager = make_manager(wiki_env)
    from unittest.mock import AsyncMock
    manager.llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))

    tags = await manager._suggest_tags("content", "clients")
    assert tags == []


@pytest.mark.asyncio
async def test_save_page_content_returns_new_suggestions(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme.md",
               "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nContent.")

    from unittest.mock import AsyncMock, MagicMock
    mock_response = MagicMock()
    mock_response.content = '["wedding", "VIP"]'
    manager.llm.ainvoke = AsyncMock(return_value=mock_response)

    suggestions = await manager.save_page_content(
        "clients/acme.md",
        "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nUpdated."
    )
    assert isinstance(suggestions, list)
    assert "wedding" in suggestions


@pytest.mark.asyncio
async def test_save_page_content_excludes_existing_tags_from_suggestions(wiki_env):
    sources, wiki, archive = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme.md",
               "---\nname: Acme\ntags:\n- wedding\n---\n\n# Acme\n\nContent.")

    from unittest.mock import AsyncMock, MagicMock
    mock_response = MagicMock()
    mock_response.content = '["wedding", "VIP"]'  # "wedding" already on page
    manager.llm.ainvoke = AsyncMock(return_value=mock_response)

    suggestions = await manager.save_page_content(
        "clients/acme.md",
        "---\nname: Acme\ntags:\n- wedding\n---\n\n# Acme\n\nUpdated."
    )
    assert "wedding" not in suggestions
    assert "VIP" in suggestions
```

- [ ] **Step 2: Run new tests to verify they fail**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py::test_suggest_tags_returns_list \
       tests/test_search_and_tags.py::test_suggest_tags_returns_empty_on_error \
       tests/test_search_and_tags.py::test_save_page_content_returns_new_suggestions \
       tests/test_search_and_tags.py::test_save_page_content_excludes_existing_tags_from_suggestions -v
```
Expected: `AttributeError: '_suggest_tags'` and return type failures

- [ ] **Step 3: Add `_suggest_tags` and update `save_page_content`**

Add `_suggest_tags` after `update_source_tags`:

```python
async def _suggest_tags(self, content: str, entity_type: str) -> list[str]:
    """Ask the LLM for 3-5 tags. Returns empty list on any failure."""
    from langchain_core.prompts import ChatPromptTemplate
    prompt = ChatPromptTemplate.from_messages([
        ("human", (
            "Suggest 3-5 short, lowercase tags for this {entity_type} page. "
            "Return ONLY a JSON array of strings, e.g. [\"tag1\", \"tag2\"]. "
            "Content:\n{content}"
        ))
    ])
    chain = prompt | self.llm
    try:
        response = await chain.ainvoke({
            "entity_type": entity_type,
            "content": content[:2000],
        })
        text = response.content if hasattr(response, "content") else str(response)
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            tags = json.loads(match.group())
            return [str(t).lower().strip() for t in tags if isinstance(t, str)][:5]
    except Exception:
        pass
    return []
```

Update `save_page_content` to call `_suggest_tags` and return new suggestions (replace the version from Task 2):

```python
async def save_page_content(self, page_path: str, content: str) -> list[str]:
    """
    Save content to a wiki page and log the action.
    Returns AI-suggested tags not already present on the page.
    """
    path = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
    async with self._write_lock:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.update_index()
        self._append_to_log("edit", f"Updated {page_path}")
    self._rebuild_search_index()

    entity_type = page_path.split("/")[0]
    fm, _ = self._parse_frontmatter(content)
    existing_tags = [str(t).lower() for t in fm.get("tags", []) if isinstance(t, str)]
    all_suggestions = await self._suggest_tags(content, entity_type)
    return [t for t in all_suggestions if t not in existing_tags]
```

Update `ingest_source` (line 263) — add auto-apply of tags in Phase 3, after the existing Phase 2 block. After the `async with self._write_lock:` block and before `return result`, add:

```python
        # Phase 3: Auto-apply AI tags to pages and source (outside lock)
        for page in result.pages:
            try:
                entity_type = page.path.split("/")[0]
                tags = await self._suggest_tags(page.content, entity_type)
                if tags:
                    await self.update_page_tags(page.path, tags)
            except Exception:
                pass
        try:
            source_tags = await self._suggest_tags(content[:2000], "source")
            if source_tags:
                self.update_source_tags(file_name, source_tags)
        except Exception:
            pass
        self._rebuild_search_index()
```

The full updated tail of `ingest_source` (replacing lines 326–338) becomes:

```python
        # Phase 2: Write files (serialized)
        async with self._write_lock:
            for page in result.pages:
                page_full_path = os.path.join(self.wiki_dir, page.path.replace("/", os.sep))
                os.makedirs(os.path.dirname(page_full_path), exist_ok=True)
                with open(page_full_path, "w", encoding="utf-8") as f:
                    f.write(page.content)

            self.update_index()
            self.mark_source_ingested(file_name, True)
            self._append_to_log("ingest", result.log_entry)

        # Phase 3: Auto-apply AI tags (outside lock — async LLM calls)
        for page in result.pages:
            try:
                entity_type = page.path.split("/")[0]
                tags = await self._suggest_tags(page.content, entity_type)
                if tags:
                    await self.update_page_tags(page.path, tags)
            except Exception:
                pass
        try:
            source_tags = await self._suggest_tags(content[:2000], "source")
            if source_tags:
                self.update_source_tags(file_name, source_tags)
        except Exception:
            pass
        self._rebuild_search_index()

        return result
```

- [ ] **Step 4: Run new tests to verify they pass**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py::test_suggest_tags_returns_list \
       tests/test_search_and_tags.py::test_suggest_tags_returns_empty_on_error \
       tests/test_search_and_tags.py::test_save_page_content_returns_new_suggestions \
       tests/test_search_and_tags.py::test_save_page_content_excludes_existing_tags_from_suggestions -v
```
Expected: all 4 PASS

- [ ] **Step 5: Run full test suite**

```
cd Faragopedia-Sales/backend
pytest tests/ -v
```
Expected: all previously passing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/backend/agent/wiki_manager.py \
        Faragopedia-Sales/backend/tests/test_search_and_tags.py
git commit -m "feat: add _suggest_tags and wire tag suggestion into save_page_content and ingest_source"
```

---

## Task 5: API — new endpoints + update PUT /pages/{path}

**Files:**
- Modify: `Faragopedia-Sales/backend/api/routes.py`
- Modify: `Faragopedia-Sales/backend/tests/test_search_and_tags.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_search_and_tags.py`:

```python
# ── API endpoints ─────────────────────────────────────────────────────────────

from fastapi.testclient import TestClient
import sys

@pytest.fixture
def client(wiki_env, monkeypatch):
    sources, wiki, archive = wiki_env
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_MODEL", "gpt-4o-mini")

    from api import routes as r
    r.SOURCES_DIR = sources
    r.WIKI_DIR = wiki
    r.ARCHIVE_DIR = archive
    r.wiki_manager = WikiManager(sources_dir=sources, wiki_dir=wiki, archive_dir=archive)

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(r.router)
    return TestClient(app)


def test_get_search_index(client, wiki_env):
    sources, wiki, archive = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags:\n- foo\n---\n\n# Test\n\nContent.")
    import api.routes as r
    r.wiki_manager._rebuild_search_index()

    resp = client.get("/search/index")
    assert resp.status_code == 200
    data = resp.json()
    assert "pages" in data
    assert "sources" in data


def test_get_tags(client, wiki_env):
    sources, wiki, archive = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags:\n- foo\n- bar\n---\n\n# Test\n\nContent.")
    import api.routes as r
    r.wiki_manager._rebuild_search_index()

    resp = client.get("/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert "foo" in data
    assert "bar" in data


def test_patch_page_tags(client, wiki_env):
    sources, wiki, archive = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags: []\n---\n\n# Test\n\nContent.")

    resp = client.patch("/pages/clients/test.md/tags", json={"tags": ["wedding", "VIP"]})
    assert resp.status_code == 200
    import api.routes as r
    fm, _ = r.wiki_manager._parse_frontmatter(
        r.wiki_manager.get_page_content("clients/test.md")
    )
    assert fm["tags"] == ["wedding", "VIP"]


def test_patch_source_tags(client, wiki_env):
    sources, wiki, archive = wiki_env
    src_path = os.path.join(sources, "file.txt")
    with open(src_path, "w") as f:
        f.write("content")

    resp = client.patch("/sources/file.txt/tags", json={"tags": ["brief"]})
    assert resp.status_code == 200
    import api.routes as r
    meta = r.wiki_manager._load_metadata()
    assert meta["file.txt"]["tags"] == ["brief"]


def test_put_page_returns_suggested_tags(client, wiki_env):
    sources, wiki, archive = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags: []\n---\n\n# Test\n\nContent.")

    from unittest.mock import AsyncMock, MagicMock, patch as mock_patch
    import api.routes as r
    mock_resp = MagicMock()
    mock_resp.content = '["wedding"]'
    r.wiki_manager.llm.ainvoke = AsyncMock(return_value=mock_resp)

    resp = client.put("/pages/clients/test.md",
                      json={"content": "---\nname: Test\ntags: []\n---\n\n# Test\n\nNew."})
    assert resp.status_code == 200
    data = resp.json()
    assert "suggested_tags" in data
    assert isinstance(data["suggested_tags"], list)
```

- [ ] **Step 2: Run new tests to verify they fail**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py::test_get_search_index \
       tests/test_search_and_tags.py::test_get_tags \
       tests/test_search_and_tags.py::test_patch_page_tags \
       tests/test_search_and_tags.py::test_patch_source_tags \
       tests/test_search_and_tags.py::test_put_page_returns_suggested_tags -v
```
Expected: all FAIL — endpoints don't exist yet

- [ ] **Step 3: Add new endpoints and update `PUT /pages/{path}`**

Add these Pydantic models near the top of `routes.py`, after the imports (before `router = APIRouter()`):

```python
from pydantic import BaseModel
from typing import List

class TagsUpdate(BaseModel):
    tags: List[str]
```

Add the five new endpoints anywhere in `routes.py` (e.g., after the existing `GET /sources/metadata` endpoint):

```python
@router.get("/search/index")
async def get_search_index():
    index_path = os.path.join(WIKI_DIR, "search-index.json")
    if not os.path.exists(index_path):
        wiki_manager._rebuild_search_index()
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading search index: {str(e)}")


@router.get("/tags")
async def get_tags():
    index_path = os.path.join(WIKI_DIR, "search-index.json")
    if not os.path.exists(index_path):
        wiki_manager._rebuild_search_index()
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        tag_counts: dict[str, int] = {}
        for page in index.get("pages", []):
            for t in page.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        for src in index.get("sources", []):
            for t in src.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        return tag_counts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading tags: {str(e)}")


@router.patch("/pages/{path:path}/tags")
async def update_page_tags(path: str, body: TagsUpdate):
    try:
        safe_path = safe_wiki_filename(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        await wiki_manager.update_page_tags(safe_path, body.tags)
        return {"tags": body.tags}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating tags: {str(e)}")


@router.patch("/sources/{filename}/tags")
async def update_source_tags(filename: str, body: TagsUpdate):
    safe_name = os.path.basename(filename)
    try:
        wiki_manager.update_source_tags(safe_name, body.tags)
        return {"tags": body.tags}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating source tags: {str(e)}")


@router.post("/search/rebuild")
async def rebuild_search_index():
    try:
        wiki_manager._rebuild_search_index()
        return {"message": "Search index rebuilt"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rebuilding index: {str(e)}")
```

Also add `import json` to `routes.py` imports if not already present (check line 1–10).

Update the existing `PUT /pages/{path:path}` endpoint (line 477) to return `suggested_tags`:

```python
@router.put("/pages/{path:path}")
async def update_page(path: str, payload: dict):
    try:
        safe_path = safe_wiki_filename(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    content = payload.get("content")
    if content is None:
        raise HTTPException(status_code=422, detail="Content is required")
    try:
        suggested_tags = await wiki_manager.save_page_content(safe_path, content)
        return {"message": "Page updated successfully", "suggested_tags": suggested_tags}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating page: {str(e)}")
```

- [ ] **Step 4: Run new tests to verify they pass**

```
cd Faragopedia-Sales/backend
pytest tests/test_search_and_tags.py::test_get_search_index \
       tests/test_search_and_tags.py::test_get_tags \
       tests/test_search_and_tags.py::test_patch_page_tags \
       tests/test_search_and_tags.py::test_patch_source_tags \
       tests/test_search_and_tags.py::test_put_page_returns_suggested_tags -v
```
Expected: all 5 PASS

- [ ] **Step 5: Run full test suite**

```
cd Faragopedia-Sales/backend
pytest tests/ -v
```
Expected: all previously passing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/backend/api/routes.py \
        Faragopedia-Sales/backend/tests/test_search_and_tags.py
git commit -m "feat: add search index and tag API endpoints"
```

---

## Task 6: Frontend WikiView — search bar + results panel

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/components/WikiView.tsx`

- [ ] **Step 1: Add TypeScript types and search state**

At the top of `WikiView.tsx`, after the existing imports, add:

```typescript
type SearchEntry = {
  path: string;
  title: string;
  entity_type: string;
  tags: string[];
  frontmatter: Record<string, unknown>;
  content_preview: string;
};

type SearchIndex = {
  pages: SearchEntry[];
  sources: Array<{
    filename: string;
    display_name: string;
    tags: string[];
    metadata: { ingested: boolean; upload_date: string | null };
  }>;
};
```

Inside the `WikiView` component, after the existing state declarations (around line 55), add:

```typescript
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [searchIndex, setSearchIndex] = useState<SearchIndex | null>(null);
  const [tagFilter, setTagFilter] = useState<string[]>([]);
  const [suggestedTags, setSuggestedTags] = useState<string[]>([]);
```

- [ ] **Step 2: Fetch the search index on mount**

In `WikiView.tsx`, add a `fetchSearchIndex` function alongside the existing `fetchPages` / `fetchEntityTypes` functions:

```typescript
  const fetchSearchIndex = async () => {
    try {
      const res = await fetch(`${API_BASE}/search/index`);
      if (!res.ok) return;
      const data: SearchIndex = await res.json();
      setSearchIndex(data);
    } catch {
      // search unavailable — silently degrade
    }
  };
```

In the `useEffect` that calls `fetchEntityTypes` and `fetchPages` (around line 75), add `fetchSearchIndex()`:

```typescript
  useEffect(() => {
    fetchEntityTypes();
    fetchPages();
    fetchSearchIndex();
    // ... rest of effect unchanged
```

- [ ] **Step 3: Add search computation**

Add this computed value inside the component, before the `return` statement:

```typescript
  const searchResults: SearchEntry[] | null = (() => {
    if (!searchIndex || !searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    return searchIndex.pages.filter(page => {
      const matchesQuery =
        page.title.toLowerCase().includes(q) ||
        page.content_preview.toLowerCase().includes(q) ||
        page.tags.some(t => t.toLowerCase().includes(q)) ||
        Object.values(page.frontmatter).some(v => String(v).toLowerCase().includes(q));
      const matchesTags =
        tagFilter.length === 0 || tagFilter.every(t => page.tags.includes(t));
      return matchesQuery && matchesTags;
    });
  })();

  const resultTags: string[] = (() => {
    if (!searchResults) return [];
    const all = new Set<string>();
    searchResults.forEach(r => r.tags.forEach(t => all.add(t)));
    return Array.from(all).sort();
  })();

  const highlightMatch = (text: string, query: string): React.ReactNode => {
    if (!query.trim()) return text;
    const idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return text;
    return (
      <>
        {text.slice(0, idx)}
        <mark className="bg-yellow-200/30 text-yellow-300">{text.slice(idx, idx + query.length)}</mark>
        {text.slice(idx + query.length)}
      </>
    );
  };
```

- [ ] **Step 4: Add search bar and results panel to the JSX**

In the `WikiView` return JSX, find the element that wraps the sidebar and content area (the outermost `<div>` after the error toast). Add the search bar as the very first child, spanning full width, before the sidebar/content split:

```tsx
{/* Search bar — full width above sidebar+content */}
<div className="border-b border-gray-700 bg-gray-900 px-4 py-2 flex items-center gap-3">
  <Search className="w-4 h-4 text-gray-400 shrink-0" />
  <input
    type="text"
    value={searchQuery}
    onChange={e => { setSearchQuery(e.target.value); setTagFilter([]); }}
    placeholder="Search wiki pages…"
    className="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-500 outline-none"
  />
  {searchQuery && (
    <button onClick={() => { setSearchQuery(''); setTagFilter([]); }}
            className="text-gray-500 hover:text-gray-300">
      <X className="w-4 h-4" />
    </button>
  )}
  {searchIndex && (
    <span className="text-xs text-gray-500 shrink-0">
      {searchResults ? `${searchResults.length} result${searchResults.length !== 1 ? 's' : ''}` : ''}
    </span>
  )}
  {!searchIndex && <span className="text-xs text-gray-500">Search unavailable</span>}
</div>
```

Add `Search` to the lucide-react import at the top of the file (it's already there from the icon list — if not, add it).

When `searchResults` is not null, render the results panel **instead of** the normal page-tree sidebar. In the sidebar column JSX, wrap the existing tree rendering in a conditional:

```tsx
{searchResults !== null ? (
  /* ── Search results panel ── */
  <div className="flex flex-col h-full overflow-hidden">
    {/* Tag filter row */}
    {resultTags.length > 0 && (
      <div className="flex flex-wrap gap-1 px-3 py-2 border-b border-gray-700 bg-gray-850">
        <span className="text-xs text-gray-500 self-center mr-1">Filter:</span>
        {resultTags.map(tag => (
          <button
            key={tag}
            onClick={() =>
              setTagFilter(prev =>
                prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
              )
            }
            className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
              tagFilter.includes(tag)
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-600 text-gray-400 hover:border-gray-400'
            }`}
          >
            {tagFilter.includes(tag) ? `${tag} ×` : tag}
          </button>
        ))}
      </div>
    )}
    {/* Results list */}
    <div className="flex-1 overflow-y-auto">
      {searchResults.length === 0 ? (
        <p className="text-sm text-gray-500 p-4">No pages match.</p>
      ) : (
        searchResults.map(entry => (
          <button
            key={entry.path}
            onClick={() => { selectPage(entry.path); setSearchQuery(''); setTagFilter([]); }}
            className="w-full text-left px-3 py-3 border-b border-gray-800 hover:bg-gray-800 transition-colors"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-gray-200">
                {highlightMatch(entry.title, searchQuery)}
              </span>
              <span className="text-xs text-gray-500 ml-2 shrink-0">{entry.entity_type}</span>
            </div>
            {entry.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-1">
                {entry.tags.map(t => (
                  <span key={t} className="text-xs px-1.5 py-0.5 rounded-full bg-blue-900/40 text-blue-300">
                    {t}
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-400 line-clamp-2">
              {highlightMatch(entry.content_preview, searchQuery)}
            </p>
          </button>
        ))
      )}
    </div>
  </div>
) : (
  /* ── Normal page tree (existing JSX — unchanged) ── */
  <existing-page-tree-jsx />
)}
```

Replace `<existing-page-tree-jsx />` with the actual existing page tree JSX — do not delete it, just wrap it in the else branch.

You will also need a `selectPage` helper that handles navigation to a page (extract the logic from the existing click handler if it isn't already a named function).

- [ ] **Step 5: Manual test in browser**

Start the dev server:
```
cd Faragopedia-Sales/frontend
npm run dev
```

Open the browser, go to the Wiki view:
1. Type in the search bar → results panel appears with matching pages
2. Click a tag in the filter row → results narrow
3. Click a result → navigates to that page, search clears
4. Clear the search → normal page tree reappears

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/WikiView.tsx
git commit -m "feat: add search bar and results panel to WikiView"
```

---

## Task 7: Frontend WikiView — tag chips + add/remove + AI suggestion UI

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/components/WikiView.tsx`

- [ ] **Step 1: Add tag state**

Inside `WikiView`, after the existing `suggestedTags` state (added in Task 6):

```typescript
  const [pageTags, setPageTags] = useState<string[]>([]);
  const [tagVocabulary, setTagVocabulary] = useState<string[]>([]);
  const [addingTag, setAddingTag] = useState(false);
  const [newTagInput, setNewTagInput] = useState('');
```

- [ ] **Step 2: Load tags when a page is selected and after save**

Add a `fetchTagVocabulary` function:

```typescript
  const fetchTagVocabulary = async () => {
    try {
      const res = await fetch(`${API_BASE}/tags`);
      if (!res.ok) return;
      const data: Record<string, number> = await res.json();
      setTagVocabulary(Object.keys(data).sort());
    } catch {}
  };
```

When a page loads (`fetchPageContent` or wherever `setContent` is called), also parse the tags from frontmatter. After `setContent(data.content)` add:

```typescript
      // Parse tags from frontmatter
      const match = data.content.match(/^---\n([\s\S]*?)\n---/);
      if (match) {
        try {
          const fm = (window as any).__yaml_parse
            ? (window as any).__yaml_parse(match[1])
            : {};
          setPageTags(Array.isArray(fm?.tags) ? fm.tags : []);
        } catch { setPageTags([]); }
      } else {
        setPageTags([]);
      }
      setSuggestedTags([]);
```

Since the frontend doesn't bundle a YAML parser, parse tags with a simple regex instead:

```typescript
      const tagsMatch = data.content.match(/^tags:\s*\n((?:\s+-\s+\S+\n?)*)/m);
      if (tagsMatch) {
        const tags = tagsMatch[1]
          .split('\n')
          .map(l => l.replace(/^\s+-\s+/, '').trim())
          .filter(Boolean);
        setPageTags(tags);
      } else {
        const inlineMatch = data.content.match(/^tags:\s*\[([^\]]*)\]/m);
        if (inlineMatch) {
          setPageTags(inlineMatch[1].split(',').map(t => t.trim().replace(/['"]/g, '')).filter(Boolean));
        } else {
          setPageTags([]);
        }
      }
      setSuggestedTags([]);
```

Call `fetchTagVocabulary()` in the mount `useEffect` alongside `fetchSearchIndex()`.

After the existing `handleSave` function completes (where it calls `PUT /pages/{path}`), read `suggested_tags` from the response and set state:

```typescript
      // After: const data = await res.json();
      if (data.suggested_tags && data.suggested_tags.length > 0) {
        setSuggestedTags(data.suggested_tags);
      }
```

- [ ] **Step 3: Add helper functions for tag actions**

```typescript
  const handleAddTag = async (tag: string) => {
    const trimmed = tag.toLowerCase().trim();
    if (!trimmed || pageTags.includes(trimmed) || !selectedPage) return;
    const newTags = [...pageTags, trimmed];
    setPageTags(newTags);
    setAddingTag(false);
    setNewTagInput('');
    try {
      await fetch(`${API_BASE}/pages/${selectedPage}/tags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: newTags }),
      });
      fetchSearchIndex();
      fetchTagVocabulary();
    } catch { setPageTags(pageTags); }
  };

  const handleRemoveTag = async (tag: string) => {
    if (!selectedPage) return;
    const newTags = pageTags.filter(t => t !== tag);
    setPageTags(newTags);
    try {
      await fetch(`${API_BASE}/pages/${selectedPage}/tags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: newTags }),
      });
      fetchSearchIndex();
    } catch { setPageTags(pageTags); }
  };

  const handleAcceptSuggestedTag = async (tag: string) => {
    setSuggestedTags(prev => prev.filter(t => t !== tag));
    await handleAddTag(tag);
  };
```

- [ ] **Step 4: Add tag chips UI below the page title**

In the page-content area (the `<div>` that renders the page content), add a tag row just below the page title heading and above the content body:

```tsx
{/* Tag chips */}
{selectedPage && !isEditing && (
  <div className="flex flex-wrap items-center gap-1.5 px-6 pb-3 pt-1 border-b border-gray-800">
    {pageTags.map(tag => (
      <span key={tag}
            className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-300 border border-blue-800">
        {tag}
        <button onClick={() => handleRemoveTag(tag)}
                className="text-blue-400 hover:text-blue-200 leading-none">×</button>
      </span>
    ))}
    {addingTag ? (
      <div className="relative">
        <input
          autoFocus
          value={newTagInput}
          onChange={e => setNewTagInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') handleAddTag(newTagInput);
            if (e.key === 'Escape') { setAddingTag(false); setNewTagInput(''); }
          }}
          placeholder="tag name"
          className="text-xs bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-gray-200 outline-none w-28"
          list="tag-vocab"
        />
        <datalist id="tag-vocab">
          {tagVocabulary
            .filter(t => !pageTags.includes(t))
            .map(t => <option key={t} value={t} />)}
        </datalist>
      </div>
    ) : (
      <button onClick={() => setAddingTag(true)}
              className="text-xs text-gray-500 hover:text-gray-300 px-1">
        + tag
      </button>
    )}
    {/* AI suggestion */}
    {suggestedTags.map(tag => (
      <span key={tag} className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-900/30 text-green-400 border border-green-800">
        ✦ {tag}
        <button onClick={() => handleAcceptSuggestedTag(tag)}
                className="text-green-400 hover:text-green-200 font-medium">Accept</button>
        <button onClick={() => setSuggestedTags(prev => prev.filter(t => t !== tag))}
                className="text-green-500 hover:text-green-300">×</button>
      </span>
    ))}
  </div>
)}
```

- [ ] **Step 5: Manual test in browser**

1. Open a wiki page → tag chips appear below the title
2. Click `+ tag` → input appears with autocomplete from vocabulary
3. Type a tag and press Enter → chip added, index refreshes
4. Click `×` on a chip → tag removed
5. Save a page → if AI suggests tags, green suggestion chips appear → Accept adds them → Dismiss removes them

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/WikiView.tsx
git commit -m "feat: add tag chips, add/remove UI, and AI suggestion prompt to WikiView"
```

---

## Task 8: Frontend SourcesView — search + tag chips

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/components/SourcesView.tsx`

- [ ] **Step 1: Add types and state**

At the top of `SourcesView.tsx`, add:

```typescript
type SourceEntry = {
  filename: string;
  display_name: string;
  tags: string[];
  metadata: { ingested: boolean; upload_date: string | null };
};

type SourceSearchIndex = {
  sources: SourceEntry[];
};
```

Inside `SourcesView`, after the existing state declarations, add:

```typescript
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sourceIndex, setSourceIndex] = useState<SourceEntry[]>([]);
  const [tagFilter, setTagFilter] = useState<string[]>([]);
  const [sourceTags, setSourceTags] = useState<string[]>([]);
  const [tagVocabulary, setTagVocabulary] = useState<string[]>([]);
  const [addingTag, setAddingTag] = useState(false);
  const [newTagInput, setNewTagInput] = useState('');
```

Update the `metadata` type to include `tags`:

```typescript
  const [metadata, setMetadata] = useState<Record<string, { ingested: boolean; ingested_at: string | null; tags: string[] }>>({});
```

- [ ] **Step 2: Fetch search index and tag vocabulary**

Add `fetchSourceIndex` and `fetchTagVocabulary`:

```typescript
  const fetchSourceIndex = async () => {
    try {
      const res = await fetch(`${API_BASE}/search/index`);
      if (!res.ok) return;
      const data: SourceSearchIndex = await res.json();
      setSourceIndex(data.sources || []);
    } catch {}
  };

  const fetchTagVocabulary = async () => {
    try {
      const res = await fetch(`${API_BASE}/tags`);
      if (!res.ok) return;
      const data: Record<string, number> = await res.json();
      setTagVocabulary(Object.keys(data).sort());
    } catch {}
  };
```

In the mount `useEffect` (the one that calls `fetchSources` and `fetchMetadata`), also call:

```typescript
    fetchSourceIndex();
    fetchTagVocabulary();
```

When `selectedSource` changes, also update `sourceTags` from the index:

```typescript
  useEffect(() => {
    if (!selectedSource) { setSourceTags([]); return; }
    const entry = sourceIndex.find(s => s.filename === selectedSource);
    setSourceTags(entry?.tags ?? []);
  }, [selectedSource, sourceIndex]);
```

- [ ] **Step 3: Add search computation and tag helpers**

```typescript
  const searchResults: SourceEntry[] | null = (() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    return sourceIndex.filter(src => {
      const matchesQuery =
        src.filename.toLowerCase().includes(q) ||
        src.tags.some(t => t.toLowerCase().includes(q));
      const matchesTags =
        tagFilter.length === 0 || tagFilter.every(t => src.tags.includes(t));
      return matchesQuery && matchesTags;
    });
  })();

  const resultTags: string[] = (() => {
    if (!searchResults) return [];
    const all = new Set<string>();
    searchResults.forEach(r => r.tags.forEach(t => all.add(t)));
    return Array.from(all).sort();
  })();

  const handleAddSourceTag = async (tag: string) => {
    const trimmed = tag.toLowerCase().trim();
    if (!trimmed || sourceTags.includes(trimmed) || !selectedSource) return;
    const newTags = [...sourceTags, trimmed];
    setSourceTags(newTags);
    setAddingTag(false);
    setNewTagInput('');
    try {
      await fetch(`${API_BASE}/sources/${selectedSource}/tags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: newTags }),
      });
      fetchSourceIndex();
      fetchTagVocabulary();
    } catch { setSourceTags(sourceTags); }
  };

  const handleRemoveSourceTag = async (tag: string) => {
    if (!selectedSource) return;
    const newTags = sourceTags.filter(t => t !== tag);
    setSourceTags(newTags);
    try {
      await fetch(`${API_BASE}/sources/${selectedSource}/tags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: newTags }),
      });
      fetchSourceIndex();
    } catch { setSourceTags(sourceTags); }
  };
```

- [ ] **Step 4: Add search bar, results panel, and tag chips to JSX**

Add a full-width search bar as the first element inside the outermost container (same pattern as WikiView):

```tsx
{/* Search bar */}
<div className="border-b border-gray-700 bg-gray-900 px-4 py-2 flex items-center gap-3">
  <Search className="w-4 h-4 text-gray-400 shrink-0" />
  <input
    type="text"
    value={searchQuery}
    onChange={e => { setSearchQuery(e.target.value); setTagFilter([]); }}
    placeholder="Search sources…"
    className="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-500 outline-none"
  />
  {searchQuery && (
    <button onClick={() => { setSearchQuery(''); setTagFilter([]); }}
            className="text-gray-500 hover:text-gray-300">
      <X className="w-4 h-4" />
    </button>
  )}
  {searchResults && (
    <span className="text-xs text-gray-500 shrink-0">
      {searchResults.length} result{searchResults.length !== 1 ? 's' : ''}
    </span>
  )}
</div>
```

Add `Search` to the lucide-react import if not present.

In the sources list sidebar, when `searchResults !== null`, show the results list with a tag filter row instead of the normal sources list (same pattern as WikiView Task 6):

```tsx
{searchResults !== null ? (
  <div className="flex flex-col h-full overflow-hidden">
    {resultTags.length > 0 && (
      <div className="flex flex-wrap gap-1 px-3 py-2 border-b border-gray-700">
        <span className="text-xs text-gray-500 self-center mr-1">Filter:</span>
        {resultTags.map(tag => (
          <button key={tag}
                  onClick={() => setTagFilter(prev =>
                    prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
                  )}
                  className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                    tagFilter.includes(tag)
                      ? 'bg-blue-600 border-blue-500 text-white'
                      : 'bg-gray-800 border-gray-600 text-gray-400 hover:border-gray-400'
                  }`}>
            {tagFilter.includes(tag) ? `${tag} ×` : tag}
          </button>
        ))}
      </div>
    )}
    <div className="flex-1 overflow-y-auto">
      {searchResults.length === 0 ? (
        <p className="text-sm text-gray-500 p-4">No sources match.</p>
      ) : (
        searchResults.map(entry => (
          <button key={entry.filename}
                  onClick={() => { setSelectedSource(entry.filename); setSearchQuery(''); setTagFilter([]); }}
                  className="w-full text-left px-3 py-3 border-b border-gray-800 hover:bg-gray-800">
            <div className="text-sm text-gray-200 mb-1">{entry.filename}</div>
            {entry.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {entry.tags.map(t => (
                  <span key={t} className="text-xs px-1.5 py-0.5 rounded-full bg-blue-900/40 text-blue-300">{t}</span>
                ))}
              </div>
            )}
          </button>
        ))
      )}
    </div>
  </div>
) : (
  /* existing sources list JSX — unchanged */
  <existing-sources-list-jsx />
)}
```

Add tag chips below the source filename in the detail panel, using the same chip pattern as WikiView Task 7 but calling `handleAddSourceTag` / `handleRemoveSourceTag`:

```tsx
{selectedSource && (
  <div className="flex flex-wrap items-center gap-1.5 px-6 pb-3 pt-1 border-b border-gray-800">
    {sourceTags.map(tag => (
      <span key={tag}
            className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-300 border border-blue-800">
        {tag}
        <button onClick={() => handleRemoveSourceTag(tag)} className="text-blue-400 hover:text-blue-200">×</button>
      </span>
    ))}
    {addingTag ? (
      <div className="relative">
        <input autoFocus value={newTagInput}
               onChange={e => setNewTagInput(e.target.value)}
               onKeyDown={e => {
                 if (e.key === 'Enter') handleAddSourceTag(newTagInput);
                 if (e.key === 'Escape') { setAddingTag(false); setNewTagInput(''); }
               }}
               placeholder="tag name"
               className="text-xs bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-gray-200 outline-none w-28"
               list="source-tag-vocab" />
        <datalist id="source-tag-vocab">
          {tagVocabulary.filter(t => !sourceTags.includes(t)).map(t => <option key={t} value={t} />)}
        </datalist>
      </div>
    ) : (
      <button onClick={() => setAddingTag(true)} className="text-xs text-gray-500 hover:text-gray-300 px-1">+ tag</button>
    )}
  </div>
)}
```

- [ ] **Step 5: Manual test in browser**

1. Open Sources view → search bar visible at top
2. Type a filename or tag → results list with tag filter row appears
3. Click a source in results → navigates to it, search clears
4. Select a source → tag chips appear below filename
5. Add/remove tags → optimistic update, persisted via PATCH

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/SourcesView.tsx
git commit -m "feat: add search bar and tag chips to SourcesView"
```

---

## Final: Update .gitignore and status

- [ ] **Add `.superpowers/` to `.gitignore`**

```bash
echo '.superpowers/' >> .gitignore
git add .gitignore
```

- [ ] **Run the full backend test suite one last time**

```
cd Faragopedia-Sales/backend
pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Update `docs/status.md`**

Add a section noting: search index (`wiki/search-index.json`), per-view keyword search, and shared tag system are complete.

- [ ] **Final commit**

```bash
git add .gitignore docs/status.md
git commit -m "feat: search and tags — complete implementation"
```
