import io
import json
import zipfile

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
    import api.export_routes as er
    import agent.workspace_manager as wm_module
    wm_module._active_dirs = {
        "wiki_dir": str(dirs / "wiki"),
        "sources_dir": str(dirs / "sources"),
        "archive_dir": str(dirs / "archive"),
        "snapshots_dir": str(dirs / "snapshots"),
        "schema_dir": str(dirs / "schema"),
    }

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
