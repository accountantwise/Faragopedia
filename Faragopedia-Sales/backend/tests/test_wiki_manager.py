import asyncio
import os
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from agent.wiki_manager import (
    WikiManager, WikiPage, FaragoIngestionResult, LintFinding, LintReport,
    LintFixPlan, FixReport, Snapshot
)

@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "AI_PROVIDER": "openai",
        "AI_MODEL": "gpt-4o-mini"
    }):
        yield

@pytest.fixture
def temp_dirs(tmp_path):
    sources = tmp_path / "sources"
    wiki = tmp_path / "wiki"
    sources.mkdir()
    wiki.mkdir()
    return str(sources), str(wiki)

def test_wiki_manager_init(temp_dirs):
    sources, wiki = temp_dirs
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki)
    assert manager.sources_dir == sources
    assert manager.wiki_dir == wiki
    assert os.path.exists(sources)
    assert os.path.exists(wiki)

def test_wiki_manager_log(temp_dirs):
    sources, wiki = temp_dirs
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki)
    manager._append_to_log("test_action", "test_details")
    
    log_path = os.path.join(wiki, "log.md")
    assert os.path.exists(log_path)
    with open(log_path, "r") as f:
        content = f.read()
        assert "test_action" in content
        assert "test_details" in content

def test_wiki_manager_has_write_lock(temp_dirs):
    """_write_lock must exist and be an asyncio.Lock."""
    sources, wiki = temp_dirs
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki)
    assert hasattr(manager, '_write_lock')
    assert isinstance(manager._write_lock, asyncio.Lock)


@pytest.mark.asyncio
async def test_archive_and_restore_page(temp_dirs):
    sources, wiki = temp_dirs
    archive = os.path.join(os.path.dirname(wiki), "archive")
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki, archive_dir=archive)
    
    # Setup: Create a page
    filename = "test_page.md"
    path = os.path.join(manager.wiki_dir, filename)
    with open(path, "w") as f:
        f.write("# Test")
    
    # 1. Archive
    await manager.archive_page(filename)
    assert not os.path.exists(path)
    assert os.path.exists(os.path.join(manager.archive_wiki_dir, filename))
    
    # 2. Restore
    await manager.restore_page(filename)
    assert os.path.exists(path)
    assert not os.path.exists(os.path.join(manager.archive_wiki_dir, filename))

@pytest.mark.asyncio
async def test_archive_and_restore_source(temp_dirs):
    sources, wiki = temp_dirs
    archive = os.path.join(os.path.dirname(wiki), "archive")
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki, archive_dir=archive)
    
    # Setup: Create a source
    filename = "test_source.txt"
    path = os.path.join(manager.sources_dir, filename)
    with open(path, "w") as f:
        f.write("test content")
    
    # 1. Archive
    await manager.archive_source(filename)
    assert not os.path.exists(path)
    assert os.path.exists(os.path.join(manager.archive_sources_dir, filename))
    
    # 2. Restore
    await manager.restore_source(filename)
    assert os.path.exists(path)
    assert not os.path.exists(os.path.join(manager.archive_sources_dir, filename))

@pytest.mark.asyncio
async def test_permanent_delete(temp_dirs):
    sources, wiki = temp_dirs
    archive = os.path.join(os.path.dirname(wiki), "archive")
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki, archive_dir=archive)
    
    # Setup: Create and archive a page
    filename = "delete_me.md"
    path = os.path.join(manager.wiki_dir, filename)
    with open(path, "w") as f:
        f.write("# Delete Me")
    
    await manager.archive_page(filename)
    archive_path = os.path.join(manager.archive_wiki_dir, filename)
    assert os.path.exists(archive_path)
    
    # Permanent delete
    await manager.delete_archived_page(filename)
    assert not os.path.exists(archive_path)

@pytest.mark.asyncio
async def test_list_archived(temp_dirs):
    sources, wiki = temp_dirs
    archive = os.path.join(os.path.dirname(wiki), "archive")
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki, archive_dir=archive)
    
    # Setup: Archive something
    p_filename = "archived_page.md"
    s_filename = "archived_source.txt"
    
    with open(os.path.join(manager.wiki_dir, p_filename), "w") as f:
        f.write("# Page")
    with open(os.path.join(manager.sources_dir, s_filename), "w") as f:
        f.write("Source")
        
    await manager.archive_page(p_filename)
    await manager.archive_source(s_filename)
    
    pages = manager.list_archived_pages()
    sources = manager.list_archived_sources()
    
    assert p_filename in pages
    assert s_filename in sources

@pytest.mark.asyncio
async def test_metadata_tracking(temp_dirs):
    sources, wiki = temp_dirs
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki)
    
    filename = "test.txt"
    with open(os.path.join(sources, filename), "w") as f:
        f.write("content")
        
    # Initially not ingested
    meta = manager.get_sources_metadata()
    assert filename in meta
    assert meta[filename]["ingested"] is False
    
    # Mark as ingested
    manager.mark_source_ingested(filename, True)
    meta = manager.get_sources_metadata()
    assert meta[filename]["ingested"] is True
    assert meta[filename]["ingested_at"] is not None
    
    # Persistent across manager re-init
    manager2 = WikiManager(sources_dir=sources, wiki_dir=wiki)
    meta2 = manager2.get_sources_metadata()
    assert meta2[filename]["ingested"] is True


@pytest.fixture
def schema_dirs(tmp_path):
    """Create fake schema files for tests."""
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Test Schema\nYou are the Farago wiki agent.")
    (schema_dir / "company_profile.md").write_text("# Farago Projects\nA creative production house.")
    return str(schema_dir)


@pytest.fixture
def temp_dirs_with_schema(tmp_path, schema_dirs):
    sources = tmp_path / "sources"
    wiki = tmp_path / "wiki"
    sources.mkdir()
    wiki.mkdir()
    return str(sources), str(wiki), schema_dirs


def test_wiki_page_model():
    page = WikiPage(
        path="clients/louis-vuitton.md",
        content="---\ntype: client\nname: Louis Vuitton\n---\n# Louis Vuitton\n",
        action="create"
    )
    assert page.path == "clients/louis-vuitton.md"
    assert page.action == "create"
    assert "Louis Vuitton" in page.content


def test_wiki_page_action_values():
    create_page = WikiPage(path="clients/foo.md", content="# Foo", action="create")
    update_page = WikiPage(path="clients/foo.md", content="# Foo updated", action="update")
    assert create_page.action == "create"
    assert update_page.action == "update"


def test_farago_ingestion_result_model():
    result = FaragoIngestionResult(
        pages=[
            WikiPage(path="clients/louis-vuitton.md", content="# LV", action="create"),
            WikiPage(path="contacts/jane-doe.md", content="# Jane", action="create"),
        ],
        log_entry="Ingested LV press release. Created 2 pages: clients/louis-vuitton, contacts/jane-doe."
    )
    assert len(result.pages) == 2
    assert result.pages[0].path == "clients/louis-vuitton.md"
    assert "jane-doe" in result.log_entry


def test_lint_finding_model():
    finding = LintFinding(
        severity="warning",
        page="clients/louis-vuitton.md",
        description="Missing 'last_contact' field in frontmatter."
    )
    assert finding.severity == "warning"
    assert finding.page == "clients/louis-vuitton.md"


def test_lint_report_model():
    report = LintReport(
        findings=[
            LintFinding(severity="error", page="global", description="Orphan page: photographers/unknown.md"),
            LintFinding(severity="warning", page="clients/chanel.md", description="tier field is empty"),
            LintFinding(severity="suggestion", page="global", description="Consider adding Dior as a prospect"),
        ],
        summary="1 error, 1 warning, 1 suggestion found."
    )
    assert len(report.findings) == 3
    errors = [f for f in report.findings if f.severity == "error"]
    assert len(errors) == 1


def test_lint_finding_has_fix_fields():
    finding = LintFinding(
        severity="warning",
        page="clients/louis-vuitton.md",
        description="Missing 'last_contact' field.",
        fix_confidence="full",
        fix_description="Add a last_contact field to the frontmatter.",
    )
    assert finding.fix_confidence == "full"
    assert finding.fix_description == "Add a last_contact field to the frontmatter."


def test_lint_finding_fix_fields_default():
    finding = LintFinding(
        severity="warning",
        page="clients/acme.md",
        description="Some issue.",
    )
    assert finding.fix_confidence == "stub"
    assert finding.fix_description == ""


def test_lint_fix_plan_model():
    from agent.wiki_manager import LintFixPlan
    plan = LintFixPlan(
        pages=[WikiPage(path="concepts/e-sign.md", content="# E-Sign\n\nStub.", action="create")],
        skipped=["needs_source: Whitmore bottleneck pages"],
        summary="Fixed 1 finding: created 1 stub.",
    )
    assert len(plan.pages) == 1
    assert plan.pages[0].path == "concepts/e-sign.md"
    assert len(plan.skipped) == 1


def test_fix_report_model():
    from agent.wiki_manager import FixReport
    report = FixReport(
        files_changed=["concepts/e-sign.md"],
        skipped=["needs_source: Whitmore bottleneck pages"],
        summary="Fixed 1 finding: created 1 stub.",
        snapshot_id="20260420-143201",
    )
    assert report.snapshot_id == "20260420-143201"
    assert "concepts/e-sign.md" in report.files_changed


def test_snapshot_model():
    from agent.wiki_manager import Snapshot
    snap = Snapshot(
        id="20260420-143201",
        label="pre-lint 2026-04-20 14:32",
        created_at="2026-04-20T14:32:01",
        file_count=12,
    )
    assert snap.id == "20260420-143201"
    assert snap.file_count == 12


def test_system_prompt_loaded_from_schema_dir(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# SCHEMA CONTENT")
    (schema_dir / "company_profile.md").write_text("# PROFILE CONTENT")

    sources = tmp_path / "sources"
    wiki = tmp_path / "wiki"
    sources.mkdir()
    wiki.mkdir()

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(sources),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )

    assert "SCHEMA CONTENT" in manager.system_prompt
    assert "PROFILE CONTENT" in manager.system_prompt


def test_system_prompt_returns_stub_if_schema_missing(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    # Only create SCHEMA.md, not company_profile.md — should return stub, not raise

    sources = tmp_path / "sources"
    wiki = tmp_path / "wiki"
    sources.mkdir()
    wiki.mkdir()

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        wm = WikiManager(
            sources_dir=str(sources),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )
    assert "Setup required" in wm.system_prompt


def test_list_pages_returns_subdirectory_paths(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "photographers").mkdir()
    (wiki / "clients" / "louis-vuitton.md").write_text("---\ntype: client\n---\n# LV")
    (wiki / "photographers" / "jamie-hawkesworth.md").write_text("---\ntype: photographer\n---\n# JH")
    (wiki / "index.md").write_text("# Index")
    (wiki / "log.md").write_text("# Log")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )

    pages = manager.list_pages()
    assert "clients/louis-vuitton.md" in pages
    assert "photographers/jamie-hawkesworth.md" in pages
    assert "index.md" not in pages
    assert "log.md" not in pages


def test_update_index_groups_by_subdirectory(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    entity_meta = {
        "clients": "Clients", "prospects": "Prospects", "contacts": "Contacts",
        "photographers": "Photographers", "productions": "Productions",
    }
    for sub, name in entity_meta.items():
        (wiki / sub).mkdir()
        (wiki / sub / "_type.yaml").write_text(
            f"name: {name}\nsingular: {sub.rstrip('s')}\nfields: []\nsections: []\n"
        )
    (wiki / "clients" / "louis-vuitton.md").write_text("# LV")
    (wiki / "prospects" / "chanel.md").write_text("# Chanel")
    (wiki / "photographers" / "jamie-hawkesworth.md").write_text("# JH")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )

    manager.update_index()
    index_content = (wiki / "index.md").read_text()

    assert "## Clients" in index_content
    assert "[[clients/louis-vuitton]]" in index_content
    assert "## Prospects" in index_content
    assert "[[prospects/chanel]]" in index_content
    assert "## Photographers" in index_content
    assert "[[photographers/jamie-hawkesworth]]" in index_content


def test_get_backlinks_across_subdirectories(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "contacts").mkdir()
    (wiki / "productions").mkdir()

    (wiki / "clients" / "louis-vuitton.md").write_text(
        "# LV\n\nKey contact: [[contacts/jane-doe]]"
    )
    (wiki / "productions" / "2026-02-lv-editorial.md").write_text(
        "# LV Editorial\n\nClient: [[clients/louis-vuitton]]"
    )
    (wiki / "contacts" / "jane-doe.md").write_text("# Jane Doe\n\nWorks at [[clients/louis-vuitton]]")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )

    backlinks = manager.get_backlinks("clients/louis-vuitton.md")
    assert "productions/2026-02-lv-editorial.md" in backlinks
    assert "contacts/jane-doe.md" in backlinks


import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("OPENAI_API_KEY", "test_key_for_import")
from api.routes import safe_wiki_filename


def test_safe_wiki_filename_allows_known_subdirs():
    from unittest.mock import MagicMock
    known = {"clients", "prospects", "contacts", "photographers", "productions"}
    entity_types = {sub: {"name": sub.capitalize()} for sub in known}
    mock_wm = MagicMock()
    mock_wm.get_entity_types.return_value = entity_types
    for sub in known:
        result = safe_wiki_filename(f"{sub}/some-page.md", mock_wm)
        assert result == f"{sub}/some-page.md"


def test_safe_wiki_filename_rejects_unknown_subdir():
    from unittest.mock import MagicMock
    mock_wm = MagicMock()
    mock_wm.get_entity_types.return_value = {}
    with pytest.raises(ValueError, match="Invalid entity subdirectory"):
        safe_wiki_filename("evil/foo.md", mock_wm)


def test_safe_wiki_filename_rejects_flat_path():
    from unittest.mock import MagicMock
    mock_wm = MagicMock()
    mock_wm.get_entity_types.return_value = {}
    with pytest.raises(ValueError, match="Invalid entity subdirectory"):
        safe_wiki_filename("louis-vuitton.md", mock_wm)


def test_safe_wiki_filename_rejects_traversal():
    from unittest.mock import MagicMock
    mock_wm = MagicMock()
    mock_wm.get_entity_types.return_value = {}
    with pytest.raises(ValueError):
        safe_wiki_filename("../etc/passwd.md", mock_wm)
    with pytest.raises(ValueError):
        safe_wiki_filename("clients/../secrets.md", mock_wm)


def test_safe_wiki_filename_rejects_non_md():
    from unittest.mock import MagicMock
    mock_wm = MagicMock()
    mock_wm.get_entity_types.return_value = {"clients": {}}
    with pytest.raises(ValueError, match=".md"):
        safe_wiki_filename("clients/foo.txt", mock_wm)


@pytest.mark.asyncio
async def test_ingest_writes_pages_to_correct_subdirectory(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    sources = tmp_path / "sources"
    wiki = tmp_path / "wiki"
    sources.mkdir()
    wiki.mkdir()
    entity_meta = {
        "clients": "Clients", "contacts": "Contacts", "prospects": "Prospects",
        "photographers": "Photographers", "productions": "Productions",
    }
    for sub, name in entity_meta.items():
        (wiki / sub).mkdir()
        (wiki / sub / "_type.yaml").write_text(
            f"name: {name}\nsingular: {sub.rstrip('s')}\nfields: []\nsections: []\n"
        )
    (wiki / "index.md").write_text("# Index\n\n## Clients\n\n*No clients yet.*\n")

    source_file = sources / "lv-brief.txt"
    source_file.write_text("Louis Vuitton is an A-tier client. Contact: Sophie Martin.")

    mock_result = FaragoIngestionResult(
        pages=[
            WikiPage(
                path="clients/louis-vuitton.md",
                content="---\ntype: client\nname: Louis Vuitton\ntier: A\nstatus: active\n---\n# Louis Vuitton\n\n## Overview\n\nLuxury fashion house.\n",
                action="create"
            ),
            WikiPage(
                path="contacts/sophie-martin.md",
                content="---\ntype: contact\nname: Sophie Martin\norg: Louis Vuitton\n---\n# Sophie Martin\n\n## Role & Responsibilities\n\nKey contact at [[clients/louis-vuitton]].\n",
                action="create"
            ),
        ],
        log_entry="Ingested lv-brief.txt. Created 2 pages: clients/louis-vuitton, contacts/sophie-martin."
    )

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(sources),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )

    with patch.object(manager, '_run_ingest_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_result
        await manager.ingest_source("lv-brief.txt")

    assert (wiki / "clients" / "louis-vuitton.md").exists()
    lv_content = (wiki / "clients" / "louis-vuitton.md").read_text()
    assert "tier: A" in lv_content

    assert (wiki / "contacts" / "sophie-martin.md").exists()
    sophie_content = (wiki / "contacts" / "sophie-martin.md").read_text()
    assert "[[clients/louis-vuitton]]" in sophie_content

    index_content = (wiki / "index.md").read_text()
    assert "[[clients/louis-vuitton]]" in index_content

    log_content = (wiki / "log.md").read_text()
    assert "lv-brief.txt" in log_content

    metadata = manager.get_sources_metadata()
    assert metadata["lv-brief.txt"]["ingested"] is True


@pytest.mark.asyncio
async def test_ingest_source_not_found(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(tmp_path / "wiki"),
            schema_dir=str(schema_dir)
        )

    with pytest.raises(FileNotFoundError):
        await manager.ingest_source("nonexistent.txt")


@pytest.mark.asyncio
async def test_ingest_retries_on_llm_failure(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    sources = tmp_path / "sources"
    wiki = tmp_path / "wiki"
    sources.mkdir()
    wiki.mkdir()
    (wiki / "index.md").write_text("# Index")
    (sources / "test.txt").write_text("Test content")

    success_result = FaragoIngestionResult(
        pages=[WikiPage(path="clients/test.md", content="# Test", action="create")],
        log_entry="Ingested test.txt"
    )

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(sources),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )

    # Fail once, succeed on second attempt
    (wiki / "clients").mkdir()
    call_count = [0]
    async def flaky_llm(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("LLM output validation failed")
        return success_result

    with patch.object(manager, '_run_ingest_llm', side_effect=flaky_llm):
        await manager.ingest_source("test.txt")

    assert call_count[0] == 2
    assert (wiki / "clients" / "test.md").exists()


class _CapturingLLM:
    """Fake LLM that records the messages passed to a structured-output call."""

    def __init__(self):
        self.captured_messages = None

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.captured_messages = messages
        return FaragoIngestionResult(pages=[], log_entry="ok")


def _make_ingest_manager(tmp_path, fake_llm):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=fake_llm):
        return WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir),
        )


@pytest.mark.asyncio
async def test_ingest_uses_cache_control_for_anthropic_provider(tmp_path):
    fake_llm = _CapturingLLM()
    with patch.dict(os.environ, {"INGEST_AI_PROVIDER": "anthropic", "INGEST_AI_MODEL": "claude-haiku-4-5"}):
        manager = _make_ingest_manager(tmp_path, fake_llm)
        await manager._run_ingest_llm(
            filename="brief.txt",
            source_content="Some source text.",
            index_content="# Index",
            existing_pages="--- clients/acme.md ---\n# Acme",
        )

    system_message, human_message = fake_llm.captured_messages

    assert isinstance(system_message.content, list)
    assert system_message.content[0]["cache_control"] == {"type": "ephemeral"}
    assert system_message.content[0]["text"] == manager.system_prompt

    assert isinstance(human_message.content, list)
    assert human_message.content[0]["cache_control"] == {"type": "ephemeral"}
    assert "Current wiki index" in human_message.content[0]["text"]
    assert "# Index" in human_message.content[0]["text"]
    assert "Existing pages that may need updating" in human_message.content[0]["text"]
    assert "clients/acme.md" in human_message.content[0]["text"]

    assert "cache_control" not in human_message.content[1]
    assert "Source document filename: brief.txt" in human_message.content[1]["text"]
    assert "Some source text." in human_message.content[1]["text"]
    assert "Instructions:" in human_message.content[1]["text"]


@pytest.mark.asyncio
async def test_ingest_uses_cache_control_for_openrouter_anthropic_model(tmp_path):
    fake_llm = _CapturingLLM()
    with patch.dict(os.environ, {"INGEST_AI_PROVIDER": "openrouter", "INGEST_AI_MODEL": "anthropic/claude-sonnet-4.6"}):
        manager = _make_ingest_manager(tmp_path, fake_llm)
        await manager._run_ingest_llm(
            filename="brief.txt", source_content="x", index_content="# Index", existing_pages=""
        )

    system_message, human_message = fake_llm.captured_messages
    assert isinstance(system_message.content, list)
    assert system_message.content[0]["cache_control"] == {"type": "ephemeral"}
    assert isinstance(human_message.content, list)
    assert human_message.content[0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_ingest_no_cache_control_for_openrouter_non_anthropic_model(tmp_path):
    fake_llm = _CapturingLLM()
    with patch.dict(os.environ, {"INGEST_AI_PROVIDER": "openrouter", "INGEST_AI_MODEL": "meta-llama/llama-3-70b-instruct"}):
        manager = _make_ingest_manager(tmp_path, fake_llm)
        await manager._run_ingest_llm(
            filename="brief.txt", source_content="x", index_content="# Index", existing_pages=""
        )

    system_message, human_message = fake_llm.captured_messages
    assert isinstance(system_message.content, str)
    assert isinstance(human_message.content, str)


@pytest.mark.asyncio
async def test_ingest_no_cache_control_for_default_provider(tmp_path):
    """Explicitly force a non-Anthropic provider — don't rely on INGEST_AI_PROVIDER
    being merely absent, since main.py's load_dotenv() can leak the real .env's
    INGEST_AI_PROVIDER=openrouter into the test process when other test modules
    import main first."""
    fake_llm = _CapturingLLM()
    with patch.dict(os.environ, {"INGEST_AI_PROVIDER": "openai", "INGEST_AI_MODEL": "gpt-4o-mini"}):
        manager = _make_ingest_manager(tmp_path, fake_llm)
        await manager._run_ingest_llm(
            filename="brief.txt", source_content="Some source text.", index_content="# Index", existing_pages="existing"
        )

    system_message, human_message = fake_llm.captured_messages
    assert system_message.content == manager.system_prompt
    assert isinstance(human_message.content, str)
    assert "Current wiki index" in human_message.content
    assert "# Index" in human_message.content
    assert "existing" in human_message.content
    assert "Source document filename: brief.txt" in human_message.content
    assert "Some source text." in human_message.content
    assert "Instructions:" in human_message.content


@pytest.mark.asyncio
async def test_query_uses_system_prompt(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema — you are the Farago wiki agent")
    (schema_dir / "company_profile.md").write_text("# Farago Projects profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "louis-vuitton.md").write_text(
        "---\ntype: client\nname: Louis Vuitton\ntier: A\n---\n# Louis Vuitton\n\n## Overview\n\nA luxury fashion house."
    )
    (wiki / "index.md").write_text(
        "# Index\n\n## Clients\n\n- [[clients/louis-vuitton]] | last updated: 2026-04-16\n"
    )

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )

    captured_calls = []

    async def mock_run_query(user_query, context):
        captured_calls.append({
            "query": user_query,
            "context": context,
        })
        return "Louis Vuitton is an A-tier client. [[clients/louis-vuitton]]"

    with patch.object(manager, '_run_query_llm', side_effect=mock_run_query):
        response = await manager.query("Who are our top clients?")

    assert response == "Louis Vuitton is an A-tier client. [[clients/louis-vuitton]]"
    assert len(captured_calls) == 1
    assert "louis-vuitton" in captured_calls[0]["context"].lower()

    log_content = (wiki / "log.md").read_text()
    assert "query" in log_content


@pytest.mark.asyncio
async def test_lint_returns_report(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "louis-vuitton.md").write_text(
        "---\ntype: client\nname: Louis Vuitton\ntier: A\n---\n# Louis Vuitton\n"
    )
    (wiki / "index.md").write_text("# Index\n\n## Clients\n\n- [[clients/louis-vuitton]]\n")

    mock_report = LintReport(
        findings=[
            LintFinding(
                severity="warning",
                page="clients/louis-vuitton.md",
                description="Missing 'last_contact' field in frontmatter."
            )
        ],
        summary="1 warning found."
    )

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )

    with patch.object(manager, '_run_lint_llm', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_report
        report = await manager.lint()

    assert isinstance(report, LintReport)
    assert len(report.findings) == 1
    assert report.findings[0].severity == "warning"
    assert report.summary == "1 warning found."

    # Lint is read-only — no files written except log
    log_content = (wiki / "log.md").read_text()
    assert "lint" in log_content


def test_health_check_no_longer_exists(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(tmp_path / "wiki"),
            schema_dir=str(schema_dir)
        )

    assert not hasattr(manager, 'health_check'), \
        "health_check() should be removed — use lint() instead"


@pytest.mark.asyncio
async def test_create_new_page_in_entity_subdir(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    entity_meta = {
        "clients": "Clients", "prospects": "Prospects", "contacts": "Contacts",
        "photographers": "Photographers", "productions": "Productions",
    }
    for sub, name in entity_meta.items():
        (wiki / sub).mkdir()
        (wiki / sub / "_type.yaml").write_text(
            f"name: {name}\nsingular: {sub.rstrip('s')}\nfields: []\nsections: []\n"
        )

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir)
        )

    filename = await manager.create_new_page(entity_type="clients")
    assert filename == "clients/Untitled.md"
    assert (wiki / "clients" / "Untitled.md").exists()

    # Second creation → collision handling
    filename2 = await manager.create_new_page(entity_type="clients")
    assert filename2 == "clients/Untitled_1.md"

    # Photographers subdir
    filename3 = await manager.create_new_page(entity_type="photographers")
    assert filename3 == "photographers/Untitled.md"


@pytest.mark.asyncio
async def test_create_new_page_rejects_invalid_type(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(tmp_path / "wiki"),
            schema_dir=str(schema_dir)
        )

    with pytest.raises(ValueError, match="Invalid entity type"):
        await manager.create_new_page(entity_type="invoices")


def test_create_snapshot(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "acme.md").write_text("# Acme\n")
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    snap = manager.create_snapshot()
    assert snap.file_count >= 1
    assert (snapshots / f"{snap.id}.zip").exists()
    assert (snapshots / f"{snap.id}.meta.json").exists()


def test_list_snapshots(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    manager.create_snapshot(label="snap-1")
    time.sleep(0.01)  # ensure distinct timestamps
    manager.create_snapshot(label="snap-2")
    snaps = manager.list_snapshots()
    assert len(snaps) == 2
    labels = {s.label for s in snaps}
    assert "snap-1" in labels
    assert "snap-2" in labels
    assert snaps[0].label == "snap-2"  # newest first


def test_restore_snapshot(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    original_file = wiki / "clients" / "acme.md"
    original_file.write_text("# Original\n")
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    snap = manager.create_snapshot()
    # Modify the file after snapshot
    original_file.write_text("# Modified\n")
    assert original_file.read_text() == "# Modified\n"

    with patch.object(manager, 'update_index') as mock_idx, \
         patch.object(manager, '_rebuild_search_index') as mock_search:
        manager.restore_snapshot(snap.id)

    assert original_file.read_text() == "# Original\n"
    mock_idx.assert_called_once()
    mock_search.assert_called_once()


def test_restore_snapshot_not_found(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(tmp_path / "wiki"),
            snapshots_dir=str(tmp_path / "snapshots"),
            schema_dir=str(schema_dir),
        )

    with pytest.raises(FileNotFoundError):
        manager.restore_snapshot("nonexistent-id")


def test_delete_snapshot(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    snap = manager.create_snapshot()
    assert (snapshots / f"{snap.id}.zip").exists()
    manager.delete_snapshot(snap.id)
    assert not (snapshots / f"{snap.id}.zip").exists()
    assert not (snapshots / f"{snap.id}.meta.json").exists()


@pytest.mark.asyncio
async def test_fix_lint_findings(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "acme.md").write_text("---\ntype: client\nname: Acme\n---\n# Acme\n")
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    mock_fix_plan = LintFixPlan(
        pages=[WikiPage(
            path="concepts/e-sign.md",
            content="---\ntype: concept\nname: E-Sign\n---\n# E-Sign\n\nStub page.\n",
            action="create",
        )],
        skipped=[],
        summary="Fixed 1 finding: created 1 stub.",
    )

    findings = [
        LintFinding(
            severity="suggestion",
            page="global",
            description="E-sign concept page is missing.",
            fix_confidence="stub",
            fix_description="Create a stub concepts/e-sign.md page.",
        )
    ]

    with patch.object(manager, '_run_fix_llm', new_callable=AsyncMock) as mock_fix_llm:
        mock_fix_llm.return_value = mock_fix_plan
        report = await manager.fix_lint_findings(findings)

    assert isinstance(report, FixReport)
    assert "concepts/e-sign.md" in report.files_changed
    assert report.snapshot_id != ""
    assert (snapshots / f"{report.snapshot_id}.zip").exists()
    assert (wiki / "concepts" / "e-sign.md").exists()
    log_content = (wiki / "log.md").read_text()
    assert "lint-fix" in log_content


def test_rebuild_search_index_creates_index_md(temp_dirs):
    """_rebuild_search_index() must write wiki/_meta/index.md."""
    sources, wiki = temp_dirs
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki)

    # Create a page so index has content
    contacts_dir = os.path.join(wiki, "contacts")
    os.makedirs(contacts_dir, exist_ok=True)
    type_yaml = os.path.join(contacts_dir, "_type.yaml")
    with open(type_yaml, "w") as f:
        f.write("name: contacts\n")
    page_path = os.path.join(contacts_dir, "jane-doe.md")
    with open(page_path, "w") as f:
        f.write("---\nname: Jane Doe\ntags:\n  - prospect\n---\n# Jane Doe\n")

    manager._rebuild_search_index()

    index_md = os.path.join(wiki, "_meta", "index.md")
    assert os.path.exists(index_md), "_meta/index.md was not created"


def test_index_md_content(temp_dirs):
    """_meta/index.md must contain frontmatter, by-type sections, and A-Z list."""
    sources, wiki = temp_dirs
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki)

    contacts_dir = os.path.join(wiki, "contacts")
    os.makedirs(contacts_dir, exist_ok=True)
    with open(os.path.join(contacts_dir, "_type.yaml"), "w") as f:
        f.write("name: contacts\n")
    with open(os.path.join(contacts_dir, "jane-doe.md"), "w") as f:
        f.write("---\nname: Jane Doe\ntags:\n  - prospect\n---\n# Jane\n")
    with open(os.path.join(contacts_dir, "adam-smith.md"), "w") as f:
        f.write("---\nname: Adam Smith\ntags: []\n---\n# Adam\n")

    manager._rebuild_search_index()

    index_md = os.path.join(wiki, "_meta", "index.md")
    with open(index_md, "r", encoding="utf-8") as f:
        text = f.read()

    # Frontmatter
    assert "system: true" in text
    assert "generated_at:" in text

    # By-type section
    assert "## By Type" in text
    assert "### Contacts" in text
    assert "[[contacts/jane-doe]]" in text
    assert "`#prospect`" in text

    # A-Z section: Adam should appear before Jane
    assert "## All Pages (A" in text
    adam_pos = text.index("adam-smith")
    jane_pos = text.index("jane-doe")
    assert adam_pos < jane_pos, "A-Z list is not sorted alphabetically by title"


def test_list_pages_excludes_meta(temp_dirs):
    """list_pages() must not include _meta/index.md."""
    sources, wiki = temp_dirs
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki)

    meta_dir = os.path.join(wiki, "_meta")
    os.makedirs(meta_dir, exist_ok=True)
    with open(os.path.join(meta_dir, "index.md"), "w") as f:
        f.write("---\nsystem: true\n---\n# Index\n")

    contacts_dir = os.path.join(wiki, "contacts")
    os.makedirs(contacts_dir, exist_ok=True)
    with open(os.path.join(contacts_dir, "_type.yaml"), "w") as f:
        f.write("name: contacts\n")
    with open(os.path.join(contacts_dir, "jane-doe.md"), "w") as f:
        f.write("---\nname: Jane Doe\n---\n# Jane\n")

    pages = manager.list_pages()
    assert "_meta/index.md" not in pages
    assert "contacts/jane-doe.md" in pages


def test_get_backlinks_excludes_meta(temp_dirs):
    """_meta/index.md must not appear as a backlink source."""
    sources, wiki = temp_dirs
    manager = WikiManager(sources_dir=sources, wiki_dir=wiki)

    contacts_dir = os.path.join(wiki, "contacts")
    os.makedirs(contacts_dir, exist_ok=True)
    with open(os.path.join(contacts_dir, "_type.yaml"), "w") as f:
        f.write("name: contacts\n")
    with open(os.path.join(contacts_dir, "jane-doe.md"), "w") as f:
        f.write("---\nname: Jane Doe\n---\n# Jane\n")

    # Write a _meta/index.md that contains a wikilink to jane-doe
    meta_dir = os.path.join(wiki, "_meta")
    os.makedirs(meta_dir, exist_ok=True)
    with open(os.path.join(meta_dir, "index.md"), "w") as f:
        f.write("---\nsystem: true\n---\n\n- [[contacts/jane-doe]]\n")

    backlinks = manager.get_backlinks("contacts/jane-doe.md")
    assert "_meta/index.md" not in backlinks


def test_list_pages_excludes_underscore_prefixed_files(temp_dirs):
    """_template.md and any _-prefixed .md files must not appear in list_pages."""
    sources, wiki = temp_dirs
    clients = os.path.join(wiki, "clients")
    os.makedirs(clients, exist_ok=True)
    # Write _type.yaml so entity type is valid
    with open(os.path.join(clients, "_type.yaml"), "w") as f:
        f.write("name: Clients\nsingular: client\nfields: []\nsections: []\n")
    # Write a real page
    with open(os.path.join(clients, "acme.md"), "w") as f:
        f.write("---\ntype: client\nname: Acme\n---\n")
    # Write a template file that should be hidden
    with open(os.path.join(clients, "_template.md"), "w") as f:
        f.write("---\ntype: client\nname: \n---\n")

    manager = WikiManager(sources_dir=sources, wiki_dir=wiki)

    pages = manager.list_pages()
    assert "clients/acme.md" in pages
    assert "clients/_template.md" not in pages


@pytest.mark.asyncio
async def test_create_new_page_uses_template_when_present(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "_type.yaml").write_text(
        "name: Clients\nsingular: client\nfields: []\nsections: []\n"
    )
    template_content = (
        "---\ntype: client\nname: \ntier:  # options: A, B, C\n---\n\n# \n\n"
        "## Overview\n_Add overview here..._\n"
    )
    (wiki / "clients" / "_template.md").write_text(template_content)

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir),
        )

    filename = await manager.create_new_page(entity_type="clients")
    assert filename == "clients/Untitled.md"
    written = (wiki / "clients" / "Untitled.md").read_text()
    assert written == template_content


@pytest.mark.asyncio
async def test_create_new_page_falls_back_when_no_template(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "_type.yaml").write_text(
        "name: Clients\nsingular: client\nfields: []\nsections: []\n"
    )
    # No _template.md present

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir),
        )

    filename = await manager.create_new_page(entity_type="clients")
    written = (wiki / "clients" / "Untitled.md").read_text()
    assert "type: client" in written
    assert "name: " in written


def test_slugify_basic():
    from agent.wiki_manager import WikiManager
    assert WikiManager._slugify("Acme Corp") == "acme-corp"
    assert WikiManager._slugify("Jane O'Brien") == "jane-o-brien"
    assert WikiManager._slugify("  Hello  World  ") == "hello-world"
    assert WikiManager._slugify("ABC 123") == "abc-123"
    assert WikiManager._slugify("---") == "untitled"
    assert WikiManager._slugify("") == "untitled"


@pytest.mark.asyncio
async def test_auto_rename_if_untitled_renames_when_name_present(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "_type.yaml").write_text(
        "name: Clients\nsingular: client\nfields: []\nsections: []\n"
    )
    untitled_path = wiki / "clients" / "Untitled.md"
    untitled_path.write_text("---\ntype: client\nname: Acme Corp\n---\n\n# Acme Corp\n")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir),
        )

    new_path = await manager.auto_rename_if_untitled("clients/Untitled.md")
    assert new_path == "clients/acme-corp.md"
    assert (wiki / "clients" / "acme-corp.md").exists()
    assert not (wiki / "clients" / "Untitled.md").exists()


@pytest.mark.asyncio
async def test_auto_rename_if_untitled_no_op_when_already_named(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "_type.yaml").write_text(
        "name: Clients\nsingular: client\nfields: []\nsections: []\n"
    )
    (wiki / "clients" / "acme-corp.md").write_text("---\ntype: client\nname: Acme Corp\n---\n")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir),
        )

    result = await manager.auto_rename_if_untitled("clients/acme-corp.md")
    assert result is None


@pytest.mark.asyncio
async def test_auto_rename_if_untitled_no_op_when_name_empty(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "_type.yaml").write_text(
        "name: Clients\nsingular: client\nfields: []\nsections: []\n"
    )
    untitled_path = wiki / "clients" / "Untitled.md"
    untitled_path.write_text("---\ntype: client\nname: \n---\n\n# \n")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir),
        )

    result = await manager.auto_rename_if_untitled("clients/Untitled.md")
    assert result is None
    assert (wiki / "clients" / "Untitled.md").exists()


@pytest.mark.asyncio
async def test_rename_page_renames_file(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "_type.yaml").write_text(
        "name: Clients\nsingular: client\nfields: []\nsections: []\n"
    )
    (wiki / "clients" / "old-name.md").write_text("---\ntype: client\nname: Old Name\n---\n")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir),
        )

    new_path = await manager.rename_page("clients/old-name.md", "New Name")
    assert new_path == "clients/new-name.md"
    assert (wiki / "clients" / "new-name.md").exists()
    assert not (wiki / "clients" / "old-name.md").exists()


@pytest.mark.asyncio
async def test_rename_page_rewrites_wikilinks(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "_type.yaml").write_text(
        "name: Clients\nsingular: client\nfields: []\nsections: []\n"
    )
    (wiki / "clients" / "old-name.md").write_text("---\ntype: client\nname: Old Name\n---\n")
    referencing = wiki / "clients" / "other.md"
    referencing.write_text("See also [[clients/old-name]] for more.\n")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir),
        )

    await manager.rename_page("clients/old-name.md", "New Name")
    updated = referencing.read_text()
    assert "[[clients/new-name]]" in updated
    assert "[[clients/old-name]]" not in updated


@pytest.mark.asyncio
async def test_rename_page_no_op_when_same_slug(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "_type.yaml").write_text(
        "name: Clients\nsingular: client\nfields: []\nsections: []\n"
    )
    (wiki / "clients" / "acme-corp.md").write_text("---\ntype: client\nname: Acme Corp\n---\n")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            schema_dir=str(schema_dir),
        )

    result = await manager.rename_page("clients/acme-corp.md", "Acme Corp")
    assert result == "clients/acme-corp.md"
    assert (wiki / "clients" / "acme-corp.md").exists()


def test_get_field_schema_returns_enum_fields(tmp_path):
    import yaml
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    contacts_dir = wiki_dir / "contacts"
    contacts_dir.mkdir()
    (contacts_dir / "_type.yaml").write_text(yaml.dump({
        "name": "Contacts",
        "singular": "contact",
        "fields": [
            {"name": "type", "type": "string", "default": "contact"},
            {"name": "name", "type": "string"},
            {"name": "status", "type": "enum", "values": ["Active", "Dormant"]},
            {"name": "relationship", "type": "enum", "values": ["Cold", "Warm", "Hot"]},
            {"name": "notes", "type": "string"},
            {"name": "tags", "type": "list", "default": "[]"},
        ],
    }))
    from agent.wiki_manager import WikiManager
    wm = WikiManager(wiki_dir=str(wiki_dir), sources_dir=str(tmp_path / "sources"))
    schema = wm.get_field_schema("contacts")
    assert schema == {
        "status": ["Active", "Dormant"],
        "relationship": ["Cold", "Warm", "Hot"],
    }


def test_get_field_schema_unknown_type_returns_empty(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    from agent.wiki_manager import WikiManager
    wm = WikiManager(wiki_dir=str(wiki_dir), sources_dir=str(tmp_path / "sources"))
    assert wm.get_field_schema("nonexistent") == {}


@pytest.mark.asyncio
async def test_patch_frontmatter_field_updates_value(tmp_path):
    import yaml
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    contacts_dir = wiki_dir / "contacts"
    contacts_dir.mkdir()
    page = contacts_dir / "alice.md"
    page.write_text("---\nname: Alice\nstatus: Active\n---\n\n## Summary\n")
    from agent.wiki_manager import WikiManager
    wm = WikiManager(wiki_dir=str(wiki_dir), sources_dir=str(tmp_path / "sources"))
    await wm.patch_frontmatter_field("contacts/alice.md", "status", "Dormant")
    updated = page.read_text()
    fm, _ = wm._parse_frontmatter(updated)
    assert fm["status"] == "Dormant"

@pytest.mark.asyncio
async def test_patch_frontmatter_field_bad_path_raises(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    from agent.wiki_manager import WikiManager
    wm = WikiManager(wiki_dir=str(wiki_dir), sources_dir=str(tmp_path / "sources"))
    with pytest.raises(FileNotFoundError):
        await wm.patch_frontmatter_field("contacts/missing.md", "status", "Active")
