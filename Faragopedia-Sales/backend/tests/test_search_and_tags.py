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
    schema = tmp_path / "schema"
    sources.mkdir()
    wiki.mkdir()
    schema.mkdir()
    # Create a clients entity folder with _type.yaml
    clients = wiki / "clients"
    clients.mkdir()
    (clients / "_type.yaml").write_text(
        yaml.dump({"name": "Clients", "singular": "client", "fields": [], "sections": []})
    )
    return str(sources), str(wiki), str(archive), str(schema)


def make_manager(wiki_env):
    sources, wiki, archive, schema = wiki_env
    return WikiManager(sources_dir=sources, wiki_dir=wiki, archive_dir=archive, schema_dir=schema)


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
    sources, wiki, archive, _schema = wiki_env
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
    sources, wiki, archive, _schema = wiki_env
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
    sources, wiki, archive, _schema = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags: []\n---\n\n# Test\n\nHello.")
    # Index should not exist yet
    assert not os.path.exists(os.path.join(wiki, "search-index.json"))
    make_manager(wiki_env)
    assert os.path.exists(os.path.join(wiki, "search-index.json"))


# ── Index sync on writes ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_page_content_rebuilds_index(wiki_env):
    sources, wiki, archive, _schema = wiki_env
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
    sources, wiki, archive, _schema = wiki_env
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
    sources, wiki, archive, _schema = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/restored.md",
               "---\nname: Restored\ntags: []\n---\n\n# Restored\n\nContent.")
    await manager.archive_page("clients/restored.md")

    await manager.restore_page("clients/restored.md")

    with open(os.path.join(wiki, "search-index.json")) as f:
        index = json.load(f)
    assert any(p["path"] == "clients/restored.md" for p in index["pages"])


# ── Tag management ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_page_tags_writes_frontmatter(wiki_env):
    sources, wiki, archive, _schema = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme.md",
               "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nContent.")

    await manager.update_page_tags("clients/acme.md", ["wedding", "VIP"])

    content = manager.get_page_content("clients/acme.md")
    fm, _ = manager._parse_frontmatter(content)
    assert fm["tags"] == ["wedding", "vip"]


@pytest.mark.asyncio
async def test_update_page_tags_rebuilds_index(wiki_env):
    sources, wiki, archive, _schema = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme.md",
               "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nContent.")

    await manager.update_page_tags("clients/acme.md", ["commercial"])

    with open(os.path.join(wiki, "search-index.json")) as f:
        index = json.load(f)
    entry = next(p for p in index["pages"] if p["path"] == "clients/acme.md")
    assert "commercial" in entry["tags"]


def test_update_source_tags_writes_metadata(wiki_env):
    sources, wiki, archive, _schema = wiki_env
    manager = make_manager(wiki_env)
    src = os.path.join(sources, "brief.txt")
    with open(src, "w") as f:
        f.write("content")
    manager.mark_source_ingested("brief.txt", True)

    manager.update_source_tags("brief.txt", ["brief", "wedding"])

    raw = manager._load_metadata()
    assert raw["brief.txt"]["tags"] == ["brief", "wedding"]


def test_update_source_tags_rebuilds_index(wiki_env):
    sources, wiki, archive, _schema = wiki_env
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
    sources, wiki, archive, _schema = wiki_env
    manager = make_manager(wiki_env)
    src = os.path.join(sources, "file.txt")
    with open(src, "w") as f:
        f.write("x")

    meta = manager.get_sources_metadata()
    assert "tags" in meta["file.txt"]
    assert meta["file.txt"]["tags"] == []


# ── Tag suggestion ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggest_tags_returns_list(wiki_env):
    manager = make_manager(wiki_env)
    from unittest.mock import AsyncMock, MagicMock
    mock_response = MagicMock()
    mock_response.content = '["wedding", "commercial", "VIP"]'
    manager.ingest_llm.ainvoke = AsyncMock(return_value=mock_response)

    tags = await manager._suggest_tags("Some page content about weddings.", "clients")
    assert isinstance(tags, list)
    assert all(isinstance(t, str) for t in tags)
    assert len(tags) <= 5


@pytest.mark.asyncio
async def test_suggest_tags_returns_empty_on_error(wiki_env):
    manager = make_manager(wiki_env)
    from unittest.mock import AsyncMock
    manager.ingest_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))

    tags = await manager._suggest_tags("content", "clients")
    assert tags == []


@pytest.mark.asyncio
async def test_save_page_content_returns_new_suggestions(wiki_env):
    sources, wiki, archive, _schema = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme.md",
               "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nContent.")

    from unittest.mock import AsyncMock, MagicMock
    mock_response = MagicMock()
    mock_response.content = '["wedding", "VIP"]'
    manager.ingest_llm.ainvoke = AsyncMock(return_value=mock_response)

    suggestions = await manager.save_page_content(
        "clients/acme.md",
        "---\nname: Acme\ntags: []\n---\n\n# Acme\n\nUpdated."
    )
    assert isinstance(suggestions, list)
    assert "wedding" in suggestions


@pytest.mark.asyncio
async def test_save_page_content_excludes_existing_tags_from_suggestions(wiki_env):
    sources, wiki, archive, _schema = wiki_env
    manager = make_manager(wiki_env)
    write_page(wiki, "clients/acme.md",
               "---\nname: Acme\ntags:\n- wedding\n---\n\n# Acme\n\nContent.")

    from unittest.mock import AsyncMock, MagicMock
    mock_response = MagicMock()
    mock_response.content = '["wedding", "VIP"]'  # "wedding" already on page
    manager.ingest_llm.ainvoke = AsyncMock(return_value=mock_response)

    suggestions = await manager.save_page_content(
        "clients/acme.md",
        "---\nname: Acme\ntags:\n- wedding\n---\n\n# Acme\n\nUpdated."
    )
    assert "wedding" not in suggestions
    assert "vip" in suggestions


# ── API endpoints ─────────────────────────────────────────────────────────────

from fastapi.testclient import TestClient

@pytest.fixture
def client(wiki_env, monkeypatch):
    sources, wiki, archive, schema = wiki_env
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_MODEL", "gpt-4o-mini")

    from api import routes as r
    monkeypatch.setattr("api.routes.get_sources_dir", lambda: sources)
    monkeypatch.setattr("api.routes.get_wiki_dir", lambda: wiki)
    monkeypatch.setattr("api.routes.get_archive_dir", lambda: archive)
    r.set_wiki_manager(WikiManager(sources_dir=sources, wiki_dir=wiki, archive_dir=archive, schema_dir=schema))

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(r.router)
    return TestClient(app)


def test_get_search_index(client, wiki_env):
    sources, wiki, archive, _schema = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags:\n- foo\n---\n\n# Test\n\nContent.")
    import api.routes as r
    r._wiki_manager._rebuild_search_index()

    resp = client.get("/search/index")
    assert resp.status_code == 200
    data = resp.json()
    assert "pages" in data
    assert "sources" in data


def test_get_tags(client, wiki_env):
    sources, wiki, archive, _schema = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags:\n- foo\n- bar\n---\n\n# Test\n\nContent.")
    import api.routes as r
    r._wiki_manager._rebuild_search_index()

    resp = client.get("/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert "foo" in data
    assert "bar" in data


def test_patch_page_tags(client, wiki_env):
    sources, wiki, archive, _schema = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags: []\n---\n\n# Test\n\nContent.")

    resp = client.patch("/pages/clients/test.md/tags", json={"tags": ["wedding", "VIP"]})
    assert resp.status_code == 200
    import api.routes as r
    fm, _ = r._wiki_manager._parse_frontmatter(
        r._wiki_manager.get_page_content("clients/test.md")
    )
    assert fm["tags"] == ["wedding", "vip"]


def test_patch_source_tags(client, wiki_env):
    sources, wiki, archive, _schema = wiki_env
    src_path = os.path.join(sources, "file.txt")
    with open(src_path, "w") as f:
        f.write("content")

    resp = client.patch("/sources/file.txt/tags", json={"tags": ["brief"]})
    assert resp.status_code == 200
    import api.routes as r
    meta = r._wiki_manager._load_metadata()
    assert meta["file.txt"]["tags"] == ["brief"]


def test_put_page_returns_suggested_tags(client, wiki_env):
    sources, wiki, archive, _schema = wiki_env
    write_page(wiki, "clients/test.md",
               "---\nname: Test\ntags: []\n---\n\n# Test\n\nContent.")

    from unittest.mock import AsyncMock, MagicMock
    import api.routes as r
    mock_resp = MagicMock()
    mock_resp.content = '["wedding"]'
    r._wiki_manager.ingest_llm.ainvoke = AsyncMock(return_value=mock_resp)

    resp = client.put("/pages/clients/test.md",
                      json={"content": "---\nname: Test\ntags: []\n---\n\n# Test\n\nNew."})
    assert resp.status_code == 200
    data = resp.json()
    assert "suggested_tags" in data
    assert isinstance(data["suggested_tags"], list)
