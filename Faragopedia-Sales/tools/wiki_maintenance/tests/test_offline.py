"""No network, no credentials. Each test pins a behaviour that broke at least once on live data."""
import datetime as dt
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clear_notes as cn  # noqa: E402
import enrich_companies as ec  # noqa: E402


def fake_wiki(companies: dict[str, str], contacts: list[str]) -> ec.Wiki:
    """A Wiki whose pages come from memory. companies: slug -> page content."""
    w = object.__new__(ec.Wiki)
    w.index = {"companies": [f"companies/{s}.md" for s in companies], "contacts": [f"contacts/{c}.md" for c in contacts]}
    w.companies = set(w.index["companies"])
    w.contacts = set(w.index["contacts"])
    w._page_cache = {f"companies/{s}.md": c for s, c in companies.items()}
    w._company_keys = None
    w._contact_keys = w._unique({ec.norm(c): f"contacts/{c}" for c in contacts})
    return w


def page(name, aliases=None):
    extra = f"\naliases: {aliases!r}" if aliases else ""
    return f'---\nname: "{name}"{extra}\n---\n## Company Overview\n\n'


def test_norm_matches_punctuation_and_ampersand_variants():
    assert ec.norm("Ace & Tate") == ec.norm("ace-and-tate")
    assert ec.norm("Catherine O'Tool") == ec.norm("catherine-otool")
    assert ec.norm("M.A.P.") == ec.norm("map")
    assert ec.norm("Stüssy") == "stussy"


def test_resolver_uses_name_alias_and_ignores_ambiguity():
    w = fake_wiki({"alexander-mcqueen": page("Alexander McQueen", ["McQueen"]), "ace-and-tate": page("Ace & Tate")},
                  ["catherine-otool"])
    assert w.resolve_company("McQueen") == "alexander-mcqueen"
    assert w.resolve_company("[[Ace & Tate]]") == "ace-and-tate"
    assert w.resolve_company("unknown") is None
    assert w.resolve_contact("[[Catherine O'Tool]]") == "contacts/catherine-otool"


def test_joint_clients_credit_every_part_and_strip_parent_in_brackets():
    # regression: "A / B" once resolved to B only (a companies/x path-strip applied to plain text)
    w = fake_wiki({"rimowa": page("Rimowa"), "another-man-china": page("Another Man China"),
                   "johnnie-walker": page("Johnnie Walker")}, [])
    assert w.resolve_clients("Rimowa / Another Man China") == ["rimowa", "another-man-china"]
    assert w.resolve_clients("Johnnie Walker (Diageo)") == ["johnnie-walker"]
    assert w.resolve_company("Rimowa / Another Man China") is None


def test_tidy_role_keeps_acronyms_and_small_words():
    assert ec.tidy_role("CHANEL BRAZIL PR COORDINATOR") == "Chanel Brazil PR Coordinator"
    assert ec.tidy_role("EXECUTIVE PRODUCER AND HEAD OF CREATIVE SERVICES") == "Executive Producer and Head of Creative Services"
    assert ec.tidy_role("1ST AC") == "1st AC"
    assert ec.tidy_role("Senior Creative Producer") == "Senior Creative Producer"


def test_outreach_free_text_classification():
    assert ec.classify("Meeting 17th July")[1] == "Meeting logged"
    assert ec.classify("E-mailed 22nd May | Replied & call scheduled!")[1] == "Call / meeting agreed"
    assert ec.classify("Reached out, did not respond")[1] == "Contacted, no reply recorded"
    assert ec.classify("E-mailed 21st May | Email bounced")[1].startswith("Dead end")
    assert ec.parse_dates("E-mailed 27th May") == [dt.date(2026, 5, 27)]


def test_generated_lines_are_not_kept_as_manual_text():
    # regression: Meeting History re-kept its own output each run and duplicated (AbbVie had 4 copies)
    generated = ["- Listed as an outreach target: Rick Lynn (Art Director). No activity recorded in the log.",
                 "- 2026-05-21: Contacted — Marta Ardid (X). Log: “E-mailed 21st May”",
                 "- 2026-05-13: [[outreach/2026-05-byredo-ida-walle]] — Replied"]
    assert all(ec.GENERATED_MEETING.search(l) for l in generated)
    assert not ec.GENERATED_MEETING.search("- 2026-06-01: met at the showroom (typed by a person)")
    assert ec.GENERATED_CONTACT.search("- Ida Walle (no wiki page yet)")
    assert not ec.GENERATED_CONTACT.search("- Agent: Gary Example, +44 0000 000000")


def test_news_section_dedupes_by_url_and_keeps_footer_without_new_research():
    old = ["- **2026-08 — Campaign.** Summary ([WWD](https://wwd.com/x))", "", "_Web research, September 2026._"]
    ec.RESEARCH.clear()
    assert ec.news_section("x", old).endswith("_Web research, September 2026._")
    ec.RESEARCH["x"] = {"news": [{"date": "2026-08", "headline": "Campaign", "url": "https://wwd.com/x"}]}
    assert ec.news_section("x", old).count("https://wwd.com/x") == 1
    ec.RESEARCH.clear()


def test_rendered_frontmatter_is_valid_yaml():
    fm = {"name": "Ace & Tate", "key_contacts": ["[[contacts/hetty-flude]]"], "company_size": 525, "notes": "",
          "aliases": ["Ace and Tate"]}
    parsed = yaml.safe_load(ec.render_frontmatter(fm).strip().strip("-"))
    assert parsed["name"] == "Ace & Tate" and parsed["key_contacts"] == ["[[contacts/hetty-flude]]"]


def test_notes_cleanup_handles_orphans_multiline_and_human_flags():
    orphan = "---\nname: Byredo\nnotes: ''\n  for stills, video, and events.\ntags:\n- beauty\n---\nbody\n"
    new, why = cn.cleaned(orphan)
    assert why == "cleared" and yaml.safe_load(cn.frontmatter(new)[0])["tags"] == ["beauty"]
    multi = "---\nname: X\nnotes: 'Line one\n  line two.'\nstatus: Prospect\n---\nbody\n"
    new, why = cn.cleaned(multi)
    assert why == "cleared" and yaml.safe_load(cn.frontmatter(new)[0]) == {"name": "X", "notes": "", "status": "Prospect"}
    assert cn.cleaned('---\nnotes: "HUMAN: check surname"\n---\n')[1] == "kept (human flag)"
    assert cn.cleaned("---\nnotes: ''\n---\n")[1] == "already empty"
