import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# main.py calls agent.workspace_manager.initialize_workspaces() at import
# time, which reads/writes the real on-disk WORKSPACES_BASE/registry.json.
# Point those at a throwaway workspace under a tempdir BEFORE importing main,
# so setup routes (which resolve paths via get_wiki_dir()/get_schema_dir(),
# themselves backed by workspace_manager's active-workspace state) operate
# on test-owned directories instead of whatever real workspace exists on
# the machine running the tests.
_tmp = tempfile.mkdtemp()
_workspace_id = "test-ws"

import agent.workspace_manager as wm
wm.WORKSPACES_BASE = _tmp
wm.REGISTRY_PATH = os.path.join(_tmp, "registry.json")

_dirs = wm.workspace_dirs(_workspace_id)
_schema_dir = _dirs["schema_dir"]
_wiki_dir = _dirs["wiki_dir"]
for d in _dirs.values():
    os.makedirs(d, exist_ok=True)

_registry = {
    "active_workspace_id": _workspace_id,
    "workspaces": [
        {"id": _workspace_id, "name": "Test Workspace", "created_at": "2026-01-01T00:00:00"},
    ],
}
with open(wm.REGISTRY_PATH, "w", encoding="utf-8") as f:
    json.dump(_registry, f)

from main import app  # noqa: E402

client = TestClient(app)


def _clear_state():
    config = os.path.join(_schema_dir, "wiki_config.json")
    if os.path.exists(config):
        os.remove(config)
    wm.initialize_workspaces()
    import api.routes
    api.routes.set_wiki_manager(None)


def test_setup_status_required_when_no_config():
    _clear_state()
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    assert r.json()["setup_required"] is True


def test_setup_status_not_required_when_config_present():
    _clear_state()
    config = {"wiki_name": "TestWiki", "org_name": "Test Org", "setup_complete": True}
    with open(os.path.join(_schema_dir, "wiki_config.json"), "w") as f:
        json.dump(config, f)
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    assert r.json()["setup_required"] is False
    assert r.json()["wiki_name"] == "TestWiki"


def test_setup_config_returns_404_when_missing():
    _clear_state()
    r = client.get("/api/setup/config")
    assert r.status_code == 404


def test_wiki_routes_return_503_when_not_setup():
    _clear_state()
    r = client.get("/api/pages")
    assert r.status_code == 503


def test_setup_clear_returns_existing_folders():
    _clear_state()
    folder = os.path.join(_wiki_dir, "clients")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "_type.yaml"), "w") as f:
        f.write("name: Clients\n")
    r = client.post("/api/setup/clear")
    assert r.status_code == 200
    assert "clients" in r.json()["existing_folders"]


def test_delete_setup_folder():
    _clear_state()
    folder = os.path.join(_wiki_dir, "to-delete")
    os.makedirs(folder, exist_ok=True)
    r = client.delete("/api/setup/folder/to-delete")
    assert r.status_code == 200
    assert not os.path.exists(folder)


def test_delete_setup_folder_invalid_name():
    r = client.delete("/api/setup/folder/../etc")
    assert r.status_code in (400, 404)
