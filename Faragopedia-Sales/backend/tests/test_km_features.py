import os
import pytest
import asyncio
from unittest.mock import MagicMock, patch
from agent.wiki_manager import WikiManager


@pytest.fixture
def temp_wiki(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    sources_dir = tmp_path / "sources"
    wiki_dir = tmp_path / "wiki"
    sources_dir.mkdir()
    wiki_dir.mkdir()

    # Create subdirectory structure
    for sub in ["clients", "contacts", "productions"]:
        (wiki_dir / sub).mkdir()

    # Create pages with cross-links
    (wiki_dir / "clients" / "brand-a.md").write_text(
        "# Brand A\n\nLinks to [[contacts/person-b]] and [[contacts/person-c]].",
        encoding="utf-8"
    )
    (wiki_dir / "contacts" / "person-b.md").write_text(
        "# Person B\n\nWorks at [[clients/brand-a]].", encoding="utf-8"
    )
    (wiki_dir / "contacts" / "person-c.md").write_text(
        "# Person C\n\nNo links here.", encoding="utf-8"
    )
    (wiki_dir / "productions" / "2026-01-brand-a-shoot.md").write_text(
        "# Brand A Shoot\n\nClient: [[clients/brand-a]].", encoding="utf-8"
    )

    manager = WikiManager(
        sources_dir=str(sources_dir),
        wiki_dir=str(wiki_dir),
        schema_dir=str(schema_dir),
        llm=MagicMock()
    )
    return manager, wiki_dir


def test_get_backlinks(temp_wiki):
    manager, wiki_dir = temp_wiki

    backlinks_brand_a = manager.get_backlinks("clients/brand-a.md")
    assert "contacts/person-b.md" in backlinks_brand_a
    assert "productions/2026-01-brand-a-shoot.md" in backlinks_brand_a
    assert len(backlinks_brand_a) == 2

    backlinks_person_b = manager.get_backlinks("contacts/person-b.md")
    assert "clients/brand-a.md" in backlinks_person_b
    assert len(backlinks_person_b) == 1

    backlinks_person_c = manager.get_backlinks("contacts/person-c.md")
    assert "clients/brand-a.md" in backlinks_person_c
    assert len(backlinks_person_c) == 1


@pytest.mark.asyncio
async def test_save_page_content(temp_wiki):
    manager, wiki_dir = temp_wiki

    new_content = "# Person C Updated\n\nNow links to [[clients/brand-a]]."
    await manager.save_page_content("contacts/person-c.md", new_content)

    saved = (wiki_dir / "contacts" / "person-c.md").read_text(encoding="utf-8")
    assert saved == new_content

    log_path = wiki_dir / "log.md"
    assert log_path.exists()
    assert "edit | Updated contacts/person-c.md" in log_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_sources_features(temp_wiki):
    manager, _ = temp_wiki
    sources_dir = manager.sources_dir

    with open(os.path.join(sources_dir, "test1.txt"), "w", encoding="utf-8") as f:
        f.write("Hello from test1")

    sources = manager.list_sources()
    assert "test1.txt" in sources

    content = await manager.get_source_content("test1.txt")
    assert content == "Hello from test1"

    with pytest.raises(FileNotFoundError):
        await manager.get_source_content("nonexistent.txt")
