import os
import pytest
import yaml
from agent.schema_builder import (
    load_type_yaml,
    discover_entity_types,
    render_type_schema_section,
    build_schema_md,
    generate_entity_template,
    write_entity_templates,
)


@pytest.fixture
def wiki_with_types(tmp_path):
    """Create a wiki dir with two entity folders and _type.yaml files."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()

    clients = wiki / "clients"
    clients.mkdir()
    (clients / "_type.yaml").write_text(yaml.dump({
        "name": "Clients",
        "description": "Active client brands",
        "singular": "client",
        "fields": [
            {"name": "type", "type": "string", "default": "client"},
            {"name": "name", "type": "string", "required": True},
            {"name": "tier", "type": "enum", "values": ["A", "B", "C"]},
        ],
        "sections": ["Overview", "Key Contacts", "Sources"],
    }))

    stylists = wiki / "stylists"
    stylists.mkdir()
    (stylists / "_type.yaml").write_text(yaml.dump({
        "name": "Stylists",
        "description": "Hair and makeup stylists",
        "singular": "stylist",
        "fields": [
            {"name": "type", "type": "string", "default": "stylist"},
            {"name": "name", "type": "string", "required": True},
            {"name": "agency", "type": "string"},
        ],
        "sections": ["Bio", "Productions"],
    }))

    # A folder without _type.yaml should be ignored
    (wiki / "sources").mkdir()

    return str(wiki)


def test_load_type_yaml(wiki_with_types):
    data = load_type_yaml(os.path.join(wiki_with_types, "clients"))
    assert data["name"] == "Clients"
    assert data["singular"] == "client"
    assert len(data["fields"]) == 3


def test_load_type_yaml_missing_file(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = load_type_yaml(str(empty))
    assert result is None


def test_discover_entity_types(wiki_with_types):
    types = discover_entity_types(wiki_with_types)
    names = sorted(types.keys())
    assert names == ["clients", "stylists"]
    assert types["clients"]["name"] == "Clients"
    assert types["stylists"]["name"] == "Stylists"


def test_discover_skips_dirs_without_type_yaml(wiki_with_types):
    types = discover_entity_types(wiki_with_types)
    assert "sources" not in types


def test_render_type_schema_section():
    type_data = {
        "name": "Clients",
        "singular": "client",
        "description": "Active client brands",
        "fields": [
            {"name": "type", "type": "string", "default": "client"},
            {"name": "name", "type": "string", "required": True},
            {"name": "tier", "type": "enum", "values": ["A", "B", "C"]},
        ],
        "sections": ["Overview", "Key Contacts"],
    }
    section = render_type_schema_section("clients", type_data)
    assert "### clients/[" in section
    assert "type: client" in section or "type:" in section
    assert "tier: A | B | C" in section
    assert "## Overview" in section or "`## Overview`" in section


def test_build_schema_md(wiki_with_types, tmp_path):
    template_path = tmp_path / "SCHEMA_TEMPLATE.md"
    template_path.write_text(
        "# SCHEMA.md\n\nFixed content here.\n\n"
        "{{ENTITY_TYPES_DIRECTORY}}\n\n"
        "{{ENTITY_TYPES_SCHEMAS}}\n\n"
        "## Operations\n\nFixed operations.\n"
    )
    result = build_schema_md(wiki_with_types, str(template_path))
    assert "# SCHEMA.md" in result
    assert "clients/" in result
    assert "stylists/" in result
    assert "## Operations" in result
    assert "{{ENTITY_TYPES_DIRECTORY}}" not in result
    assert "{{ENTITY_TYPES_SCHEMAS}}" not in result


def test_generate_entity_template_frontmatter():
    fields = [
        {"name": "type", "type": "string", "default": "client"},
        {"name": "name", "type": "string"},
        {"name": "tier", "type": "enum", "values": ["A", "B", "C"]},
        {"name": "tags", "type": "list"},
        {"name": "status", "type": "string", "default": "active"},
    ]
    result = generate_entity_template("clients", "client", fields, [])
    assert result.startswith("---\ntype: client\n")
    assert "name: \n" in result
    assert "tier:  # options: A, B, C\n" in result
    assert "tags: []\n" in result
    assert "status: active\n" in result
    assert result.count("type: client") == 1  # not duplicated


def test_generate_entity_template_sections():
    result = generate_entity_template(
        "clients", "client", [],
        ["Overview", "Key Contacts", "Notes"],
    )
    assert "## Overview\n_Add overview here..._" in result
    assert "## Key Contacts\n_Add key contacts here..._" in result
    assert "## Notes\n_Add notes here..._" in result


def test_generate_entity_template_no_sections():
    result = generate_entity_template("contacts", "contact", [{"name": "name", "type": "string"}], [])
    assert "---\ntype: contact\nname: \n---" in result
    assert "##" not in result


def test_generate_entity_template_h1_blank():
    result = generate_entity_template("clients", "client", [], ["Overview"])
    # Body starts with a blank H1
    assert "\n\n# \n" in result


def test_write_entity_templates_creates_files(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "clients").mkdir(parents=True)
    (wiki / "contacts").mkdir()

    entity_dicts = [
        {
            "folder_name": "clients",
            "singular": "client",
            "fields": [{"name": "name", "type": "string"}],
            "sections": ["Overview"],
        },
        {
            "folder_name": "contacts",
            "singular": "contact",
            "fields": [{"name": "name", "type": "string"}],
            "sections": ["Bio"],
        },
    ]
    write_entity_templates(str(wiki), entity_dicts)

    clients_tmpl = wiki / "clients" / "_template.md"
    contacts_tmpl = wiki / "contacts" / "_template.md"
    assert clients_tmpl.exists()
    assert contacts_tmpl.exists()
    assert "type: client" in clients_tmpl.read_text()
    assert "## Overview" in clients_tmpl.read_text()
    assert "type: contact" in contacts_tmpl.read_text()
    assert "## Bio" in contacts_tmpl.read_text()


def test_write_entity_templates_creates_missing_folder(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    entity_dicts = [
        {
            "folder_name": "deals",
            "singular": "deal",
            "fields": [],
            "sections": [],
        }
    ]
    write_entity_templates(str(wiki), entity_dicts)
    assert (wiki / "deals" / "_template.md").exists()


def test_write_entity_templates_overwrites_existing(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "clients").mkdir(parents=True)
    (wiki / "clients" / "_template.md").write_text("old content")

    entity_dicts = [
        {
            "folder_name": "clients",
            "singular": "client",
            "fields": [{"name": "name", "type": "string"}],
            "sections": [],
        }
    ]
    write_entity_templates(str(wiki), entity_dicts)
    content = (wiki / "clients" / "_template.md").read_text()
    assert content != "old content"
    assert "type: client" in content


def test_render_type_schema_section_comments_every_described_field():
    """Descriptions used to render for enum fields only, so a caveat on a string or
    date field never reached SCHEMA.md — the only place the ingest and lint agents
    see what a field means."""
    section = render_type_schema_section("callsheets", {
        "singular": "callsheet",
        "fields": [
            {"name": "city", "type": "string",
             "description": "Farago office that ran the job, not the shoot location"},
            {"name": "shoot_start", "type": "date", "description": "first day on the sheet"},
            {"name": "campaigns", "type": "list", "default": "[]",
             "description": "one job can hold several"},
            {"name": "type", "type": "string", "default": "callsheet",
             "description": "entity discriminator"},
            {"name": "status", "type": "enum", "values": ["a", "b"], "description": "still works"},
            {"name": "undescribed", "type": "string"},
        ],
        "sections": [],
    })
    assert "city:          # Farago office that ran the job, not the shoot location" in section
    assert "shoot_start:          # first day on the sheet" in section
    assert "campaigns: []          # one job can hold several" in section
    assert "type: callsheet          # entity discriminator" in section
    assert "status: a | b          # still works" in section
    # A field with no description keeps its bare form, with no trailing comment marker.
    assert "\nundescribed:\n" in section
