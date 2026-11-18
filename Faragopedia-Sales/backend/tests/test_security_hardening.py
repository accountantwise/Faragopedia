"""Tier 1 hardening (2026-11-18): import rename traversal, snapshot id validation,
staged snapshot restore, CORS without credentials, health endpoint.

The July 2026 roadmap audit (roadmap/02-security-remediation.md) found the first
three; they were still open on main @ acc221c.
"""
import asyncio
import os
import sys
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

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
def wm(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "clients").mkdir(parents=True)
    return WikiManager(
        sources_dir=str(tmp_path / "sources"),
        wiki_dir=str(wiki),
        archive_dir=str(tmp_path / "archive"),
        snapshots_dir=str(tmp_path / "snapshots"),
        llm=MagicMock(),
    )


def run(coro):
    return asyncio.run(coro)


# --- import rename: path traversal -------------------------------------------

@pytest.mark.parametrize("target", [
    "../escaped.md",
    "../../escaped.md",
    "contacts/escaped.md",
    "..\\escaped.md",
    "ABSOLUTE",
    "escaped.txt",
    "",
    ".md",
])
def test_import_rename_rejects_unsafe_targets(wm, tmp_path, target):
    if target == "ABSOLUTE":
        target = str(tmp_path / "escaped.md")
    files = [("acme.md", b"# Acme")]
    result = run(wm.import_pages("clients", files, {"acme.md": {"rename": target}}))
    assert result["imported"] == []
    assert "acme.md" in result["errors"]
    assert not (tmp_path / "escaped.md").exists()
    assert not (tmp_path / "wiki" / "escaped.md").exists()


def test_import_rename_accepts_plain_md_name(wm, tmp_path):
    files = [("acme.md", b"# Acme")]
    result = run(wm.import_pages("clients", files, {"acme.md": {"rename": "acme-2.md"}}))
    assert result["imported"] == ["clients/acme-2.md"]
    assert (tmp_path / "wiki" / "clients" / "acme-2.md").read_bytes() == b"# Acme"


def test_import_rejects_unsafe_folder(wm, tmp_path):
    (tmp_path / "outside").mkdir()
    with pytest.raises(FileNotFoundError):
        run(wm.import_pages("../outside", [("acme.md", b"x")], {}))
    assert not (tmp_path / "outside" / "acme.md").exists()


# --- snapshot ids --------------------------------------------------------------

@pytest.mark.parametrize("bad_id", ["..", "../x", "a/b", "a.b", "a\\b", "", "x" * 200])
def test_restore_and_delete_reject_bad_snapshot_ids(wm, bad_id):
    with pytest.raises(ValueError):
        wm.restore_snapshot(bad_id)
    with pytest.raises(ValueError):
        wm.delete_snapshot(bad_id)


# --- staged restore ------------------------------------------------------------

def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_restore_replaces_wiki_with_snapshot_contents(wm, tmp_path):
    wiki = tmp_path / "wiki"
    _write(wiki / "clients" / "acme.md", "# Original\n")
    snap = wm.create_snapshot()
    _write(wiki / "clients" / "acme.md", "# Modified\n")
    _write(wiki / "clients" / "added-later.md", "# New\n")

    with patch.object(wm, "update_index"), patch.object(wm, "_rebuild_search_index"):
        wm.restore_snapshot(snap.id)

    assert (wiki / "clients" / "acme.md").read_text() == "# Original\n"
    assert not (wiki / "clients" / "added-later.md").exists()
    # No staging or backup folders left next to the wiki.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".restore")]
    assert leftovers == []


def test_failed_extract_leaves_wiki_untouched(wm, tmp_path):
    wiki = tmp_path / "wiki"
    _write(wiki / "clients" / "acme.md", "# Original\n")
    snap = wm.create_snapshot()
    _write(wiki / "clients" / "acme.md", "# Current\n")

    with patch.object(zipfile.ZipFile, "extractall", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            wm.restore_snapshot(snap.id)

    # The old code deleted the wiki before extracting; now nothing changes.
    assert (wiki / "clients" / "acme.md").read_text() == "# Current\n"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".restore")]
    assert leftovers == []


def test_restore_refuses_snapshot_with_escaping_member(wm, tmp_path):
    wiki = tmp_path / "wiki"
    _write(wiki / "clients" / "acme.md", "# Current\n")
    os.makedirs(wm.snapshots_dir, exist_ok=True)
    with zipfile.ZipFile(os.path.join(wm.snapshots_dir, "evil.zip"), "w") as zf:
        zf.writestr("../../escaped.md", "x")
    with pytest.raises(ValueError):
        wm.restore_snapshot("evil")
    assert (wiki / "clients" / "acme.md").read_text() == "# Current\n"


# --- HTTP layer ----------------------------------------------------------------

@pytest.fixture
def client():
    from api.routes import set_wiki_manager
    mock_wm = MagicMock()
    mock_wm.restore_snapshot.side_effect = ValueError("Invalid snapshot id")
    mock_wm.delete_snapshot.side_effect = ValueError("Invalid snapshot id")
    set_wiki_manager(mock_wm)
    from main import app
    with TestClient(app) as c:
        yield c
    set_wiki_manager(None)


def test_bad_snapshot_id_is_400_not_500(client):
    assert client.post("/api/snapshots/bad.id/restore").status_code == 400
    assert client.delete("/api/snapshots/bad.id").status_code == 400


def test_cors_never_allows_credentials(client):
    res = client.get(
        "/api/health",
        headers={"Origin": "https://evil.example", "Cookie": "CF_Authorization=abc"},
    )
    assert res.headers.get("access-control-allow-credentials") != "true"
    assert res.headers.get("access-control-allow-origin") != "https://evil.example"


def test_health_endpoint(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_health_is_not_gated_by_api_key(client):
    # Uptime monitors call it on the external hostname without a key.
    env = {"FARAGOPEDIA_API_KEY": "secret123", "FARAGOPEDIA_API_HOSTNAME": "api.example"}
    with patch.dict(os.environ, env):
        res = client.get("/api/health", headers={"Host": "api.example"})
    assert res.status_code == 200


def test_api_docs_off_by_default(client):
    # They listed every route on the public external-API hostname.
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_backup_import_rejects_escaping_entry(client):
    import io, json
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"version": 1, "type": "full"}))
        zf.writestr("schema/wiki_config.json", "{}")
        zf.writestr("../../escaped.md", "x")
    res = client.post("/api/export/import", files={"file": ("b.zip", buf.getvalue(), "application/zip")})
    assert res.status_code == 400
