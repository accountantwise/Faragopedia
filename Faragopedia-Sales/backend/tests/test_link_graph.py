import os
import yaml
import pytest
from unittest.mock import patch, MagicMock
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


def _write_type_yaml(folder, name, description):
    (folder / "_type.yaml").write_text(yaml.dump({
        "name": name,
        "description": description,
        "singular": name.lower().rstrip("s"),
        "fields": [{"name": "name", "type": "string", "required": True}],
        "sections": ["Overview"],
    }))


@pytest.fixture
def linked_wiki(tmp_path):
    """Wiki with two entity folders, cross-folder wikilinks, and edge cases:
    broken link, self link, duplicate link, frontmatter link, untyped folder."""
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "company_profile.md").write_text("# Farago Projects")
    (schema_dir / "SCHEMA_TEMPLATE.md").write_text(
        "# SCHEMA.md\n\n{{ENTITY_TYPES_DIRECTORY}}\n\n{{ENTITY_TYPES_SCHEMAS}}\n"
    )
    (schema_dir / "SCHEMA.md").write_text("# Schema placeholder")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (tmp_path / "sources").mkdir()

    clients = wiki / "clients"
    clients.mkdir()
    _write_type_yaml(clients, "Clients", "Active client brands")
    contacts = wiki / "contacts"
    contacts.mkdir()
    _write_type_yaml(contacts, "Contacts", "People we work with")

    # acme links to a contact (cross-folder), itself (skipped), a broken
    # target (skipped), and repeats the contact link (deduplicated).
    (clients / "acme.md").write_text(
        "---\ntype: client\nname: Acme Corp\n---\n# Acme Corp\n\n"
        "Main contact [[contacts/jane-doe]]. See [[clients/acme]] and "
        "[[clients/does-not-exist]]. Again: [[contacts/jane-doe]].\n"
    )
    # jane-doe links back to acme from FRONTMATTER, and has no name field
    # fallback issue (name present).
    (contacts / "jane-doe.md").write_text(
        "---\ntype: contact\nname: Jane Doe\nworks_for: \"[[clients/acme]]\"\n---\n"
        "# Jane Doe\n"
    )
    # Page with no frontmatter name — title falls back to de-slugged filename.
    (clients / "big-brand.md").write_text("# Big Brand\n\nNo links here.\n")

    # Folder without _type.yaml — its pages are not part of the graph.
    untyped = wiki / "untyped"
    untyped.mkdir()
    (untyped / "stray.md").write_text("# Stray\n\n[[clients/acme]]\n")

    with patch("agent.wiki_manager.WikiManager._init_llm", return_value=MagicMock()):
        mgr = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            archive_dir=str(tmp_path / "archive"),
            schema_dir=str(schema_dir),
        )
    return mgr


def test_graph_nodes_edges_groups(linked_wiki):
    graph = linked_wiki.get_link_graph()

    node_ids = {n["id"] for n in graph["nodes"]}
    assert node_ids == {"clients/acme.md", "clients/big-brand.md", "contacts/jane-doe.md"}

    # Self link, broken link, and duplicate link are all excluded.
    edges = {(e["source"], e["target"]) for e in graph["edges"]}
    assert edges == {
        ("clients/acme.md", "contacts/jane-doe.md"),
        ("contacts/jane-doe.md", "clients/acme.md"),  # frontmatter wikilink
    }
    assert len(graph["edges"]) == 2


def test_graph_node_titles(linked_wiki):
    titles = {n["id"]: n["title"] for n in graph_nodes(linked_wiki)}
    assert titles["clients/acme.md"] == "Acme Corp"
    assert titles["contacts/jane-doe.md"] == "Jane Doe"
    # No frontmatter name → de-slugged filename
    assert titles["clients/big-brand.md"] == "Big Brand"


def graph_nodes(mgr):
    return mgr.get_link_graph()["nodes"]


def test_graph_groups_from_entity_types(linked_wiki):
    graph = linked_wiki.get_link_graph()
    groups = {g["id"]: g for g in graph["groups"]}
    assert set(groups) == {"clients", "contacts"}
    assert groups["clients"]["name"] == "Clients"
    assert groups["clients"]["description"] == "Active client brands"


def test_graph_node_group_matches_folder(linked_wiki):
    for node in graph_nodes(linked_wiki):
        assert node["group"] == node["id"].split("/")[0]


def test_graph_route_not_shadowed_by_page_path():
    """GET /api/pages/graph must hit the graph route, not /pages/{path:path}
    (which would 400 because 'graph' does not end in .md)."""
    from api.routes import set_wiki_manager

    mock_wm = MagicMock()
    mock_wm.get_link_graph.return_value = {"nodes": [], "edges": [], "groups": []}
    set_wiki_manager(mock_wm)
    try:
        from main import app
        with TestClient(app) as client:
            response = client.get("/api/pages/graph")
        assert response.status_code == 200
        assert response.json() == {"nodes": [], "edges": [], "groups": []}
        mock_wm.get_link_graph.assert_called_once()
    finally:
        set_wiki_manager(None)
