import json
import os
import tempfile
from unittest.mock import patch
from agent.wiki_manager import WikiManager
import yaml
from agent.setup_wizard import (
    is_setup_complete,
    get_wiki_config,
    migrate_existing,
    clear_setup,
    complete_setup,
    EntityTypeDefinition,
    EntityTypeField,
    SetupPayload,
)

def test_wiki_manager_init_without_schema_files():
    """WikiManager should not crash when SCHEMA.md and company_profile.md are absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wiki_dir = os.path.join(tmpdir, "wiki")
        os.makedirs(wiki_dir)
        schema_dir = os.path.join(tmpdir, "schema")
        os.makedirs(schema_dir)
        # No SCHEMA.md, no company_profile.md, no SCHEMA_TEMPLATE.md
        # Should not raise
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "test_key",
            "AI_PROVIDER": "openai",
            "AI_MODEL": "gpt-4o-mini",
        }):
            wm = WikiManager(
                sources_dir=os.path.join(tmpdir, "sources"),
                wiki_dir=wiki_dir,
                archive_dir=os.path.join(tmpdir, "archive"),
                snapshots_dir=os.path.join(tmpdir, "snapshots"),
                schema_dir=schema_dir,
            )
        assert wm is not None


def test_is_setup_complete_false_when_no_config(tmp_path):
    assert is_setup_complete(str(tmp_path)) is False


def test_is_setup_complete_true_when_config_exists(tmp_path):
    config = {"wiki_name": "Test", "org_name": "Test Org", "setup_complete": True}
    (tmp_path / "wiki_config.json").write_text(json.dumps(config))
    assert is_setup_complete(str(tmp_path)) is True


def test_get_wiki_config_returns_none_when_missing(tmp_path):
    assert get_wiki_config(str(tmp_path)) is None


def test_get_wiki_config_returns_dict_when_present(tmp_path):
    config = {"wiki_name": "Test", "org_name": "Test Org", "setup_complete": True}
    (tmp_path / "wiki_config.json").write_text(json.dumps(config))
    result = get_wiki_config(str(tmp_path))
    assert result["wiki_name"] == "Test"


def test_migrate_existing_creates_config_when_profile_exists(tmp_path):
    (tmp_path / "company_profile.md").write_text("# Farago Projects")
    migrate_existing(str(tmp_path))
    assert (tmp_path / "wiki_config.json").exists()
    config = json.loads((tmp_path / "wiki_config.json").read_text())
    assert config["wiki_name"] == "Faragopedia"
    assert config["setup_complete"] is True


def test_migrate_existing_no_op_when_config_exists(tmp_path):
    (tmp_path / "company_profile.md").write_text("# Farago Projects")
    existing = {"wiki_name": "Custom", "org_name": "Custom Org", "setup_complete": True}
    (tmp_path / "wiki_config.json").write_text(json.dumps(existing))
    migrate_existing(str(tmp_path))
    config = json.loads((tmp_path / "wiki_config.json").read_text())
    assert config["wiki_name"] == "Custom"  # unchanged


def test_migrate_existing_no_op_when_no_profile(tmp_path):
    migrate_existing(str(tmp_path))
    assert not (tmp_path / "wiki_config.json").exists()


def test_clear_setup_removes_config_and_returns_folders(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "clients").mkdir()
    (wiki_dir / "productions").mkdir()
    (wiki_dir / "clients" / "_type.yaml").write_text("name: Clients")
    config = {"wiki_name": "Test", "org_name": "Test Org", "setup_complete": True}
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "wiki_config.json").write_text(json.dumps(config))

    folders = clear_setup(str(schema_dir), str(wiki_dir))
    assert not (schema_dir / "wiki_config.json").exists()
    assert "clients" in folders
    assert "productions" not in folders  # no _type.yaml


def _make_payload(**kwargs):
    defaults = dict(
        wiki_name="TestWiki",
        org_name="Test Org",
        org_description="A test organisation.",
        entity_types=[
            EntityTypeDefinition(
                folder_name="clients",
                display_name="Clients",
                description="Client organisations",
                singular="client",
                fields=[
                    EntityTypeField(name="name", type="string", required=True),
                    EntityTypeField(name="status", type="enum", values=["active", "inactive"]),
                ],
                sections=["Overview", "Notes"],
            )
        ],
    )
    defaults.update(kwargs)
    return SetupPayload(**defaults)


def test_complete_setup_writes_all_files(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    payload = _make_payload()

    complete_setup(str(schema_dir), str(wiki_dir), payload)

    assert (schema_dir / "wiki_config.json").exists()
    assert (schema_dir / "company_profile.md").exists()
    assert (schema_dir / "SCHEMA_TEMPLATE.md").exists()
    assert (schema_dir / "SCHEMA.md").exists()
    assert (wiki_dir / "clients" / "_type.yaml").exists()


def test_complete_setup_config_contents(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    complete_setup(str(schema_dir), str(wiki_dir), _make_payload())
    config = json.loads((schema_dir / "wiki_config.json").read_text())
    assert config["wiki_name"] == "TestWiki"
    assert config["org_name"] == "Test Org"
    assert config["setup_complete"] is True


def test_complete_setup_schema_template_substitution(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    complete_setup(str(schema_dir), str(wiki_dir), _make_payload())
    template = (schema_dir / "SCHEMA_TEMPLATE.md").read_text()
    assert "Test Org" in template
    assert "A test organisation." in template
    assert "{{ORG_NAME}}" not in template


def test_complete_setup_type_yaml_contents(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    complete_setup(str(schema_dir), str(wiki_dir), _make_payload())
    type_data = yaml.safe_load((wiki_dir / "clients" / "_type.yaml").read_text())
    assert type_data["name"] == "Clients"
    assert type_data["singular"] == "client"
    assert any(f["name"] == "name" for f in type_data["fields"])


def test_complete_setup_writes_entity_templates(tmp_path):
    schema_dir = tmp_path / "schema"
    wiki_dir = tmp_path / "wiki"
    schema_dir.mkdir()
    wiki_dir.mkdir()

    payload = SetupPayload(
        wiki_name="TestWiki",
        org_name="Test Org",
        org_description="A test organisation",
        entity_types=[
            EntityTypeDefinition(
                folder_name="clients",
                display_name="Clients",
                description="Client companies",
                singular="client",
                fields=[
                    EntityTypeField(name="name", type="string", required=True),
                    EntityTypeField(name="tier", type="enum", values=["A", "B", "C"]),
                    EntityTypeField(name="tags", type="list"),
                ],
                sections=["Overview", "Notes"],
            ),
        ],
    )
    complete_setup(str(schema_dir), str(wiki_dir), payload)

    template = wiki_dir / "clients" / "_template.md"
    assert template.exists(), "_template.md was not created"
    content = template.read_text()
    assert "type: client" in content
    assert "name: \n" in content
    assert "tier:  # options: A, B, C" in content
    assert "tags: []" in content
    assert "## Overview" in content
    assert "## Notes" in content
