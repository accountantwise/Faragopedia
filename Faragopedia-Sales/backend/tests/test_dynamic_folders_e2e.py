import os
import pytest
import yaml
from unittest.mock import patch, MagicMock

from agent.wiki_manager import WikiManager
from agent.schema_builder import discover_entity_types


@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "AI_PROVIDER": "openai",
        "AI_MODEL": "gpt-4o-mini",
    }):
        yield


@pytest.fixture
def full_wiki(tmp_path):
    """Set up a complete wiki with schema template, company profile, and one entity folder."""
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "company_profile.md").write_text("# Farago Projects\nA creative production house.")
    (schema_dir / "SCHEMA_TEMPLATE.md").write_text(
        "# SCHEMA.md\n\n## Directory Structure\n\n"
        "{{ENTITY_TYPES_DIRECTORY}}\n\n"
        "## Page Schemas\n\n{{ENTITY_TYPES_SCHEMAS}}\n\n"
        "## Operations\n\nIngest, query, lint.\n"
    )
    # Initial SCHEMA.md (will be regenerated)
    (schema_dir / "SCHEMA.md").write_text("# Schema placeholder")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    sources = tmp_path / "sources"
    sources.mkdir()

    # One seed folder
    clients = wiki / "clients"
    clients.mkdir()
    (clients / "_type.yaml").write_text(yaml.dump({
        "name": "Clients",
        "description": "Active client brands",
        "singular": "client",
        "fields": [
            {"name": "type", "type": "string", "default": "client"},
            {"name": "name", "type": "string", "required": True},
        ],
        "sections": ["Overview"],
    }))
    (clients / "test-brand.md").write_text(
        "---\ntype: client\nname: Test Brand\n---\n# Test Brand\n\n## Overview\n\nA test brand.\n"
    )

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        mgr = WikiManager(
            sources_dir=str(sources),
            wiki_dir=str(wiki),
            archive_dir=str(tmp_path / "archive"),
            schema_dir=str(schema_dir),
        )
    return mgr


@pytest.mark.asyncio
async def test_full_flow_create_folder_move_page_schema_updates(full_wiki):
    mgr = full_wiki

    # 1. Create a new folder
    await mgr.create_folder("prospects", "Prospects", "Pipeline targets")

    # Verify folder exists with _type.yaml
    prospects_dir = os.path.join(mgr.wiki_dir, "prospects")
    assert os.path.isdir(prospects_dir)
    assert os.path.exists(os.path.join(prospects_dir, "_type.yaml"))

    # 2. Verify schema was rebuilt
    schema_path = os.path.join(mgr.schema_dir, "SCHEMA.md")
    with open(schema_path) as f:
        schema = f.read()
    assert "prospects/" in schema
    assert "Pipeline targets" in schema

    # 3. Verify system_prompt was reloaded (includes new schema)
    assert "prospects/" in mgr.system_prompt or "Prospects" in mgr.system_prompt

    # 4. Move a page from clients to prospects
    new_path = await mgr.move_page("clients/test-brand.md", "prospects")
    assert new_path == "prospects/test-brand.md"
    assert os.path.exists(os.path.join(mgr.wiki_dir, "prospects", "test-brand.md"))
    assert not os.path.exists(os.path.join(mgr.wiki_dir, "clients", "test-brand.md"))

    # 5. Verify index was updated
    index_path = os.path.join(mgr.wiki_dir, "index.md")
    with open(index_path) as f:
        index = f.read()
    assert "[[prospects/test-brand]]" in index
    assert "[[clients/test-brand]]" not in index

    # 6. Verify dynamic entity type discovery
    types = mgr.get_entity_types()
    assert "clients" in types
    assert "prospects" in types

    # 7. Delete the now-empty clients folder
    await mgr.delete_folder("clients")
    assert not os.path.exists(os.path.join(mgr.wiki_dir, "clients"))
    types_after = mgr.get_entity_types()
    assert "clients" not in types_after

    # 8. Verify schema no longer includes clients
    with open(schema_path) as f:
        schema_after = f.read()
    assert "clients/" not in schema_after
