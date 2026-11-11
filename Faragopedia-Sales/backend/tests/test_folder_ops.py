import os
import pytest
import yaml
from unittest.mock import patch, MagicMock

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
def manager_with_types(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    (schema_dir / "SCHEMA_TEMPLATE.md").write_text(
        "# SCHEMA\n\n{{ENTITY_TYPES_DIRECTORY}}\n\n{{ENTITY_TYPES_SCHEMAS}}\n"
    )

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    sources = tmp_path / "sources"
    sources.mkdir()

    # Create one entity folder with _type.yaml
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
    (clients / "test-brand.md").write_text("---\ntype: client\nname: Test Brand\n---\n# Test Brand\n")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        mgr = WikiManager(
            sources_dir=str(sources),
            wiki_dir=str(wiki),
            archive_dir=str(tmp_path / "archive"),
            schema_dir=str(schema_dir),
        )
    return mgr


@pytest.mark.asyncio
async def test_create_folder(manager_with_types):
    mgr = manager_with_types
    await mgr.create_folder("stylists", "Stylists", "Hair and makeup stylists")

    folder = os.path.join(mgr.wiki_dir, "stylists")
    assert os.path.isdir(folder)

    type_yaml_path = os.path.join(folder, "_type.yaml")
    assert os.path.exists(type_yaml_path)

    with open(type_yaml_path) as f:
        data = yaml.safe_load(f)
    assert data["name"] == "Stylists"
    assert data["description"] == "Hair and makeup stylists"


@pytest.mark.asyncio
async def test_create_folder_already_exists(manager_with_types):
    mgr = manager_with_types
    with pytest.raises(ValueError, match="already exists"):
        await mgr.create_folder("clients", "Clients", "Duplicate")


@pytest.mark.asyncio
async def test_delete_folder_empty(manager_with_types):
    mgr = manager_with_types
    # Create then delete an empty folder
    await mgr.create_folder("stylists", "Stylists", "Test")
    await mgr.delete_folder("stylists")

    assert not os.path.exists(os.path.join(mgr.wiki_dir, "stylists"))


@pytest.mark.asyncio
async def test_delete_folder_nonempty_raises(manager_with_types):
    mgr = manager_with_types
    with pytest.raises(ValueError, match="not empty"):
        await mgr.delete_folder("clients")


@pytest.mark.asyncio
async def test_rename_folder(manager_with_types):
    mgr = manager_with_types
    # Create a page that links to clients/test-brand
    prospects = os.path.join(mgr.wiki_dir, "prospects")
    os.makedirs(prospects)
    with open(os.path.join(prospects, "_type.yaml"), "w") as f:
        f.write(yaml.dump({
            "name": "Prospects", "singular": "prospect", "fields": [], "sections": [],
        }))
    with open(os.path.join(prospects, "some-prospect.md"), "w") as f:
        f.write("---\ntype: prospect\n---\n# Prospect\n\nRelated: [[clients/test-brand]]\n")

    await mgr.rename_folder("clients", "brands")

    # Old folder gone, new folder exists
    assert not os.path.exists(os.path.join(mgr.wiki_dir, "clients"))
    assert os.path.isdir(os.path.join(mgr.wiki_dir, "brands"))

    # Page moved
    assert os.path.exists(os.path.join(mgr.wiki_dir, "brands", "test-brand.md"))

    # Wikilinks in other pages updated
    with open(os.path.join(prospects, "some-prospect.md")) as f:
        content = f.read()
    assert "[[brands/test-brand]]" in content
    assert "[[clients/test-brand]]" not in content


@pytest.mark.asyncio
async def test_move_page(manager_with_types):
    mgr = manager_with_types
    # Create target folder
    await mgr.create_folder("prospects", "Prospects", "Pipeline")

    # Move the page
    new_path = await mgr.move_page("clients/test-brand.md", "prospects")

    assert new_path == "prospects/test-brand.md"
    assert not os.path.exists(os.path.join(mgr.wiki_dir, "clients", "test-brand.md"))
    assert os.path.exists(os.path.join(mgr.wiki_dir, "prospects", "test-brand.md"))


@pytest.mark.asyncio
async def test_move_page_updates_wikilinks(manager_with_types):
    mgr = manager_with_types
    await mgr.create_folder("prospects", "Prospects", "Pipeline")

    # Create a page that references clients/test-brand
    prospects_dir = os.path.join(mgr.wiki_dir, "prospects")
    with open(os.path.join(prospects_dir, "other.md"), "w") as f:
        f.write("---\ntype: prospect\n---\n# Other\n\nSee [[clients/test-brand]]\n")

    await mgr.move_page("clients/test-brand.md", "prospects")

    with open(os.path.join(prospects_dir, "other.md")) as f:
        content = f.read()
    assert "[[prospects/test-brand]]" in content
    assert "[[clients/test-brand]]" not in content


@pytest.mark.asyncio
async def test_move_page_invalid_target(manager_with_types):
    mgr = manager_with_types
    with pytest.raises(ValueError, match="does not exist"):
        await mgr.move_page("clients/test-brand.md", "nonexistent")


def test_get_entity_types_is_dynamic(manager_with_types):
    mgr = manager_with_types
    types = mgr.get_entity_types()
    assert "clients" in types
    assert isinstance(types["clients"], dict)
    assert types["clients"]["name"] == "Clients"


def test_update_index_uses_dynamic_types(manager_with_types):
    mgr = manager_with_types
    mgr.update_index()
    index_path = os.path.join(mgr.wiki_dir, "index.md")
    with open(index_path) as f:
        content = f.read()
    assert "## Clients" in content
    assert "[[clients/test-brand]]" in content


# --- Explicit _type.yaml schema on create_folder -----------------------------------
# fields/sections/singular are optional additions. The first test is the regression
# guard that matters: the UI's New Folder dialog sends only name/display_name/
# description, so omitting them must keep producing exactly the type this method
# wrote before.


@pytest.mark.asyncio
async def test_create_folder_writes_unchanged_default_type_when_schema_omitted(manager_with_types):
    mgr = manager_with_types
    await mgr.create_folder("stylists", "Stylists", "Hair and makeup")

    with open(os.path.join(mgr.wiki_dir, "stylists", "_type.yaml")) as f:
        data = yaml.safe_load(f)

    assert data["singular"] == "stylist"
    assert data["fields"] == [
        {"name": "type", "type": "string", "default": "stylist"},
        {"name": "name", "type": "string", "required": True},
    ]
    assert data["sections"] == ["Overview", "Notes"]


@pytest.mark.asyncio
async def test_create_folder_accepts_explicit_fields_and_sections(manager_with_types):
    mgr = manager_with_types
    fields = [
        {"name": "type", "type": "string", "default": "job"},
        {"name": "name", "type": "string", "required": True},
        {"name": "job_reference_number", "type": "string"},
        {"name": "campaigns", "type": "list", "default": "[]"},
        {"name": "shoot_start", "type": "date"},
    ]
    sections = ["Overview", "Shoot Days", "People", "Source"]
    await mgr.create_folder("jobs", "Jobs", "Production jobs", fields=fields, sections=sections)

    with open(os.path.join(mgr.wiki_dir, "jobs", "_type.yaml")) as f:
        data = yaml.safe_load(f)

    assert data["fields"] == fields
    assert data["sections"] == sections


@pytest.mark.asyncio
async def test_create_folder_explicit_singular_overrides_rstrip_guess(manager_with_types):
    """rstrip("s") strips *every* trailing s, so the guess is wrong for words like
    "classes" (-> "clas"). An explicit singular is the fix."""
    mgr = manager_with_types
    await mgr.create_folder("classes", "Classes", "", singular="class")

    with open(os.path.join(mgr.wiki_dir, "classes", "_type.yaml")) as f:
        data = yaml.safe_load(f)

    assert data["singular"] == "class"
    # The default type field follows the resolved singular, not the stripped folder name.
    assert data["fields"][0] == {"name": "type", "type": "string", "default": "class"}


@pytest.mark.asyncio
async def test_create_folder_empty_sections_list_is_honoured(manager_with_types):
    """An explicit empty list means "no sections", and must not fall back to the
    default — hence the `is not None` check rather than a truthiness test."""
    mgr = manager_with_types
    await mgr.create_folder("jobs", "Jobs", "", sections=[])

    with open(os.path.join(mgr.wiki_dir, "jobs", "_type.yaml")) as f:
        data = yaml.safe_load(f)

    assert data["sections"] == []


# --- Route-level field validation --------------------------------------------------


def test_validate_type_fields_accepts_the_documented_vocabulary():
    from api.routes import validate_type_fields

    validate_type_fields([
        {"name": "a", "type": "string"},
        {"name": "b", "type": "date"},
        {"name": "c", "type": "integer"},
        {"name": "d", "type": "list", "default": "[]"},
        {"name": "e", "type": "enum", "values": ["x", "y"]},
        {"name": "f"},  # type defaults to string
    ])


@pytest.mark.parametrize("fields,expected", [
    ("not-a-list", "fields must be a list"),
    ([["nope"]], "must be an object"),
    ([{"type": "string"}], "missing a name"),
    ([{"name": "a", "type": "timestamp"}], "unknown type"),
    ([{"name": "a", "type": "enum"}], "needs a values list"),
    ([{"name": "a", "type": "enum", "values": []}], "needs a values list"),
])
def test_validate_type_fields_rejects_malformed_schema(fields, expected):
    from fastapi import HTTPException
    from api.routes import validate_type_fields

    with pytest.raises(HTTPException) as exc:
        validate_type_fields(fields)
    assert exc.value.status_code == 422
    assert expected in exc.value.detail
