import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock, mock_open
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app


@pytest.mark.asyncio
async def test_bulk_ingest_returns_202():
    with patch("api.routes._wiki_manager") as mock_wm, \
         patch("api.routes.asyncio.create_task") as mock_task, \
         patch("api.routes.os.path.exists", return_value=True):
        mock_wm.ingest_source = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.post("/sources/bulk-ingest", json={"filenames": ["a.pdf", "b.txt"]})
    assert resp.status_code == 202
    assert resp.json()["queued"] == ["a.pdf", "b.txt"]


@pytest.mark.asyncio
async def test_bulk_ingest_skips_missing_files():
    def exists_side_effect(path):
        return "a.pdf" in path

    with patch("api.routes._wiki_manager") as mock_wm, \
         patch("api.routes.asyncio.create_task"), \
         patch("api.routes.os.path.exists", side_effect=exists_side_effect), \
         patch("api.routes.os.path.join", side_effect=lambda *a: "/".join(a)):
        mock_wm.ingest_source = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.post("/sources/bulk-ingest", json={"filenames": ["a.pdf", "missing.txt"]})
    assert resp.status_code == 202
    data = resp.json()
    assert "a.pdf" in data["queued"]
    assert "missing.txt" in data["skipped"]


@pytest.mark.asyncio
async def test_bulk_archive_sources():
    with patch("api.routes._wiki_manager") as mock_wm:
        mock_wm.archive_source = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
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

    with patch("api.routes._wiki_manager") as mock_wm:
        mock_wm.archive_source = AsyncMock(side_effect=archive_side_effect)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
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
    with patch("api.routes._wiki_manager") as mock_wm, \
         patch("api.routes.safe_wiki_filename", side_effect=lambda p, wm: p):
        mock_wm.archive_page = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.request(
                "DELETE", "/pages/bulk",
                json={"paths": ["clients/acme.md", "contacts/bob.md"]}
            )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["archived"]) == {"clients/acme.md", "contacts/bob.md"}
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_bulk_move_pages_success():
    """Pages are renamed and wikilinks are rewritten."""
    moved_calls = []

    def rename_side_effect(src, dst):
        moved_calls.append((src, dst))

    def exists_side_effect(path):
        # Source exists, destination doesn't
        return "prospects/acme.md" in path

    with patch("api.routes._wiki_manager") as mock_wm, \
         patch("api.routes.safe_wiki_filename", side_effect=lambda p, wm: p), \
         patch("api.routes.os.path.exists", side_effect=exists_side_effect), \
         patch("api.routes.os.rename", side_effect=rename_side_effect), \
         patch("api.routes.rewrite_wikilinks", return_value={"contacts/john.md": 1}):
        mock_wm.get_entity_types.return_value = {"clients": {}, "prospects": {}, "contacts": {}}
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
    with patch("api.routes._wiki_manager") as mock_wm:
        mock_wm.get_entity_types.return_value = {"clients": {}, "prospects": {}, "contacts": {}, "photographers": {}, "productions": {}}
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

    with patch("api.routes._wiki_manager") as mock_wm, \
         patch("api.routes.safe_wiki_filename", side_effect=lambda p, wm: p), \
         patch("api.routes.os.path.exists", side_effect=exists_side_effect), \
         patch("api.routes.rewrite_wikilinks", return_value={}):
        mock_wm.get_entity_types.return_value = {"clients": {}, "prospects": {}, "contacts": {}}
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


@pytest.mark.asyncio
async def test_bulk_download_pages_success():
    """Returns a ZIP with the requested pages."""
    import io, zipfile as zf

    fake_content = b"# Acme\nSome content"

    with patch("api.routes._wiki_manager") as mock_wm, \
         patch("api.routes.safe_wiki_filename", side_effect=lambda p, wm: p), \
         patch("api.routes.os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=fake_content)):
        mock_wm.get_entity_types.return_value = {}
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
    with patch("api.routes._wiki_manager") as mock_wm, \
         patch("api.routes.safe_wiki_filename", side_effect=lambda p, wm: p), \
         patch("api.routes.os.path.exists", return_value=False):
        mock_wm.get_entity_types.return_value = {}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as ac:
            resp = await ac.post(
                "/pages/bulk-download",
                json={"paths": ["clients/missing.md"]}
            )
    assert resp.status_code == 404


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
