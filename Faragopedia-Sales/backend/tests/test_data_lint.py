"""Deterministic lint rules (agent/data_lint.py) — the shapes the 2026-10-26 callsheet
import incident produced, and the guarantee that they never reach the LLM fixer."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from agent import data_lint
from agent.wiki_manager import WikiManager, LintFinding, LintReport


def _page(root, path, text):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def wiki(tmp_path):
    w = tmp_path / "wiki"
    _page(w, "companies/y-3.md", '---\nname: "Y-3"\n---\n')
    _page(w, "companies/adidas.md", '---\nname: "adidas"\n---\n')
    _page(w, "contacts/lena-bruening.md", '---\nname: "Lena Bruening"\ncompany: "[[companies/y-3]]"\n---\n')
    _page(w, "callsheets/0422-y3.md",
          '---\nclient: "[[companies/y-3]]"\n---\n# Y-3\n\n## People\n\n'
          "| Role | Name | Company / agency | Contact |\n|------|------|------------------|---------|\n"
          "| Y3 / COMMS | [[contacts/lena-bruening]] | [[companies/y-3]] | — |\n\n## Source\n")
    return w


def _descs(w):
    return [f["description"] for f in data_lint.run_rules(str(w))]


def test_clean_wiki_has_no_findings(wiki):
    assert _descs(wiki) == []


def test_non_farago_wiki_is_left_alone(tmp_path):
    _page(tmp_path / "w", "clients/louis-vuitton.md", "---\nname: Louis Vuitton\n---\n")
    assert data_lint.run_rules(str(tmp_path / "w")) == []


def test_shifted_row_and_junk_pages_from_the_incident(wiki):
    _page(wiki, "contacts/spoma.md", '---\nname: "SPOMA"\n---\n')
    _page(wiki, "contacts/adidas.md", '---\nname: "ADIDAS"\n---\n')
    _page(wiki, "contacts/jordan-example.md", '---\nname: "Jordan Example"\n---\n')
    _page(wiki, "companies/jordan-example.md", '---\nname: "Jordan Example"\n---\n')
    _page(wiki, "callsheets/0422-y3.md",
          '---\nclient: "[[companies/y-3]]"\n---\n# Y-3\n\n## People\n\n'
          "| Role | Name | Company / agency | Contact |\n|------|------|------------------|---------|\n"
          "| Y3 \\ | [[contacts/spoma]] | [[companies/jordan-example]] | — |\n"
          "| Y3 | SPOMA | Jordan Example | Y-3 | — |\n\n## Source\n")
    d = " ".join(_descs(wiki))
    assert "role or section label" in d                      # contacts/spoma
    assert "same name as a company page" in d                # contacts/adidas
    assert "likely a person filed as a company" in d         # companies/jordan-example
    assert "role ends in a backslash" in d
    assert "wrong number of cells" in d


def test_staff_with_a_pipeline_relationship(wiki):
    _page(wiki, "contacts/alex-placeholder.md",
          '---\nname: "Alex Placeholder"\ncompany: "[[companies/farago-projects]]"\nrelationship: Client\n---\n')
    _page(wiki, "companies/farago-projects.md", '---\nname: "Farago Projects"\n---\n')
    assert any("pipeline relationship 'Client'" in d for d in _descs(wiki))


def test_link_to_a_missing_page(wiki):
    _page(wiki, "contacts/x-y.md", '---\nname: "X Y"\ncompany: "[[companies/gone]]"\n---\n')
    assert any("missing page(s): companies/gone" in d for d in _descs(wiki))


def test_every_finding_is_tagged_and_manual(wiki):
    _page(wiki, "contacts/sales.md", '---\nname: "SALES"\n---\n')
    for f in data_lint.run_rules(str(wiki)):
        assert f["description"].startswith(data_lint.PREFIX)
        assert f["fix_confidence"] == "needs_source"
        LintFinding(**f)  # valid for the API model


def _manager(tmp_path, wiki):
    schema = tmp_path / "schema"
    schema.mkdir()
    (schema / "SCHEMA.md").write_text("# Schema")
    (schema / "company_profile.md").write_text("# Profile")
    with patch("agent.wiki_manager.WikiManager._init_llm", return_value=MagicMock()):
        return WikiManager(sources_dir=str(tmp_path / "sources"), wiki_dir=str(wiki), schema_dir=str(schema))


@pytest.mark.asyncio
async def test_lint_puts_data_rules_first(tmp_path, wiki):
    _page(wiki, "contacts/sales.md", '---\nname: "SALES"\n---\n')
    m = _manager(tmp_path, wiki)
    llm = LintReport(findings=[LintFinding(severity="suggestion", page="global", description="add more")],
                     summary="1 suggestion.")
    with patch.object(m, "_run_lint_llm", new_callable=AsyncMock, return_value=llm):
        report = await m.lint()
    assert report.findings[0].description.startswith(data_lint.PREFIX)
    assert report.findings[-1].description == "add more"
    assert report.summary.startswith("1 data-rule finding(s); ")


@pytest.mark.asyncio
async def test_data_rule_findings_never_reach_the_llm_fixer(tmp_path, wiki):
    m = _manager(tmp_path, wiki)
    rule = LintFinding(severity="error", page="contacts/sales.md", description=f"{data_lint.PREFIX} junk",
                       fix_confidence="needs_source", fix_description="By hand: archive it")
    with patch.object(m, "_run_fix_llm", new_callable=AsyncMock) as fixer:
        report = await m.fix_lint_findings([rule])
    fixer.assert_not_called()
    assert report.files_changed == [] and "manual fix" in report.summary
    assert report.skipped == [f"{data_lint.PREFIX} junk — By hand: archive it"]
