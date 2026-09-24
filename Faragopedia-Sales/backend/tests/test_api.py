import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "AI_PROVIDER": "openai",
        "AI_MODEL": "gpt-4o-mini"
    }):
        yield

@pytest.fixture
def client(tmp_path):
    sources_dir = tmp_path / "sources"
    wiki_dir = tmp_path / "wiki"
    archive_dir = tmp_path / "archive"
    schema_dir = tmp_path / "schema"
    sources_dir.mkdir()
    wiki_dir.mkdir()
    archive_dir.mkdir()
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    # Create entity subdirs
    for sub in ["clients", "prospects", "contacts", "photographers", "productions"]:
        (wiki_dir / sub).mkdir()

    from agent.wiki_manager import FixReport, Snapshot
    from api.routes import set_wiki_manager

    mock_wm = MagicMock()
    mock_wm.list_pages.return_value = ["clients/test-page.md"]
    mock_wm.get_page_content.return_value = "# Test Page"
    mock_wm.get_backlinks.return_value = []
    mock_wm.save_page_content = AsyncMock(return_value=[])
    mock_wm.auto_rename_if_untitled = AsyncMock(return_value=None)
    mock_wm.archive_page = AsyncMock()
    mock_wm.create_new_page = AsyncMock(return_value="clients/Untitled.md")
    mock_wm.lint = AsyncMock(return_value=MagicMock(model_dump=lambda: {"findings": [], "summary": "Clean."}))
    mock_wm.get_entity_types.return_value = {
        "clients": {"name": "Clients", "singular": "client"},
        "prospects": {"name": "Prospects", "singular": "prospect"},
        "contacts": {"name": "Contacts", "singular": "contact"},
        "photographers": {"name": "Photographers", "singular": "photographer"},
        "productions": {"name": "Productions", "singular": "production"},
    }
    mock_wm.get_field_schema.return_value = {
        "status": ["Active", "Dormant"],
        "relationship": ["Cold", "Warm", "Hot"],
    }
    mock_wm.create_folder = AsyncMock()
    mock_wm.delete_folder = AsyncMock()
    mock_wm.rename_folder = AsyncMock()
    mock_wm.move_page = AsyncMock(return_value="prospects/test-page.md")
    mock_wm.fix_lint_findings = AsyncMock(return_value=FixReport(
        files_changed=["concepts/e-sign.md"],
        skipped=[],
        summary="Fixed 1 finding.",
        snapshot_id="20260420-143201",
    ))
    mock_wm.list_snapshots.return_value = [
        Snapshot(id="20260420-143201", label="pre-lint 2026-04-20 14:32", created_at="2026-04-20T14:32:01", file_count=5)
    ]
    mock_wm.restore_snapshot = MagicMock()
    mock_wm.delete_snapshot = MagicMock()
    mock_wm.patch_frontmatter_field = AsyncMock()

    set_wiki_manager(mock_wm)

    from main import app
    with TestClient(app) as c:
        yield c

    set_wiki_manager(None)


def test_get_pages_returns_grouped(client):
    response = client.get("/api/pages")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


def test_get_page(client):
    response = client.get("/api/pages/clients/test-page.md")
    assert response.status_code in (200, 400, 404)


def test_update_page(client):
    response = client.put(
        "/api/pages/clients/test-page.md",
        json={"content": "# Updated"}
    )
    assert response.status_code in (200, 400, 404, 422)


def test_delete_page(client):
    response = client.delete("/api/pages/clients/test-page.md")
    assert response.status_code in (200, 400, 404)


def test_create_page_with_entity_type(client):
    response = client.post("/api/pages?entity_type=clients")
    assert response.status_code in (200, 400, 500)


def test_create_page_invalid_entity_type(client):
    response = client.post("/api/pages?entity_type=invoices")
    assert response.status_code == 400


def test_health_endpoint_gone(client):
    response = client.get("/api/health")
    assert response.status_code == 404


def test_lint_endpoint_exists(client):
    response = client.post("/api/lint")
    assert response.status_code in (200, 500)


def test_safe_wiki_filename_invalid_rejected(client):
    response = client.get("/api/pages/evil/foo.md")
    assert response.status_code == 400

    response = client.get("/api/pages/flat-file.md")
    assert response.status_code in (400, 404)


def test_get_entity_types_endpoint(client):
    response = client.get("/api/entity-types")
    assert response.status_code == 200
    data = response.json()
    assert "clients" in data


def test_create_folder_endpoint(client):
    response = client.post("/api/folders", json={
        "name": "stylists",
        "display_name": "Stylists",
        "description": "Hair and makeup",
    })
    assert response.status_code in (200, 201)


def test_create_folder_missing_fields(client):
    response = client.post("/api/folders", json={"name": "stylists"})
    assert response.status_code == 422


def test_create_folder_invalid_name(client):
    response = client.post("/api/folders", json={
        "name": "Stylists With Spaces",
        "display_name": "Stylists",
    })
    assert response.status_code == 400


def test_delete_folder_endpoint(client):
    response = client.delete("/api/folders/stylists")
    assert response.status_code in (200, 400)


def test_rename_folder_endpoint(client):
    response = client.put("/api/folders/clients", json={"new_name": "brands"})
    assert response.status_code in (200, 400)


def test_move_page_endpoint(client):
    response = client.post("/api/pages/clients/test-page.md/move", json={
        "target_folder": "prospects",
    })
    assert response.status_code in (200, 400)


def test_create_page_dynamic_entity_type(client):
    response = client.post("/api/pages?entity_type=stylists")
    assert response.status_code in (200, 400, 500)


def test_lint_fix_endpoint(client):
    payload = {
        "findings": [
            {
                "severity": "suggestion",
                "page": "global",
                "description": "E-sign concept page is missing.",
                "fix_confidence": "stub",
                "fix_description": "Create a stub concepts/e-sign.md page.",
            }
        ]
    }
    response = client.post("/api/lint/fix", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "files_changed" in data
    assert "snapshot_id" in data
    assert data["snapshot_id"] == "20260420-143201"


def test_lint_fix_empty_findings(client):
    response = client.post("/api/lint/fix", json={"findings": []})
    assert response.status_code == 422


def test_list_snapshots_endpoint(client):
    response = client.get("/api/snapshots")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["id"] == "20260420-143201"


def test_restore_snapshot_endpoint(client):
    response = client.post("/api/snapshots/20260420-143201/restore")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_delete_snapshot_endpoint(client):
    response = client.delete("/api/snapshots/20260420-143201")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_get_meta_index_file(client):
    """Test that _meta/index.md paths are allowed and return proper content."""
    # Mock the wiki manager's get_page_content to return index content
    from api.routes import _wiki_manager
    index_content = """{
  "system": true,
  "pages": [
    {
      "path": "clients/test-page.md",
      "title": "Test Page",
      "tags": []
    }
  ]
}"""
    _wiki_manager.get_page_content = MagicMock(return_value=index_content)

    # Request the _meta/index.md file (URL-encoded path)
    response = client.get("/api/pages/_meta%2Findex.md")
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert "system" in data["content"]


def test_get_field_schema_returns_schema(client):
    response = client.get("/api/entity-types/contacts/field-schema")
    assert response.status_code == 200
    data = response.json()
    assert data["schema"]["status"] == ["Active", "Dormant"]
    assert data["schema"]["relationship"] == ["Cold", "Warm", "Hot"]


def test_get_field_schema_unknown_type(client):
    response = client.get("/api/entity-types/nonexistent/field-schema")
    assert response.status_code == 404


def test_patch_frontmatter_field_success(client):
    response = client.patch(
        "/api/pages/contacts/test-page.md/frontmatter",
        json={"field": "status", "value": "Dormant"}
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_patch_frontmatter_field_missing_field(client):
    response = client.patch(
        "/api/pages/contacts/test-page.md/frontmatter",
        json={"value": "Dormant"}
    )
    assert response.status_code == 422


def test_patch_frontmatter_field_invalid_path(client):
    response = client.patch(
        "/api/pages/../etc/passwd/frontmatter",
        json={"field": "status", "value": "Dormant"}
    )
    assert response.status_code in (400, 404, 422)
