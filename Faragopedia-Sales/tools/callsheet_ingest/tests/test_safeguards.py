"""Safeguards added after the 2026-10-26 escaped-pipe incident (README "Safeguards").

Fixtures use the shapes that incident actually produced (job 422, Y-3 FW25)."""
import pytest

import quarantine as q
from mdtable import MalformedRow, read_table, split_cells, split_raw
from postprocess import page_path, people_links, wikilink_companies, wikilink_people
from wiki_filter import (FilterReport, ReconciliationError, RoleVocabulary, filter_people,
                         parse_callsheet)

# --------------------------------------------------------------- B1 shared parser

ROW = r"| client_contact | Y3 \| SPOMA | Jordan Example | Y-3 | yes | unknown | unknown |"


def test_escaped_pipe_stays_in_its_cell():
    cells = split_cells(ROW)
    assert len(cells) == 7
    assert cells[1] == "Y3 / SPOMA"
    assert cells[2] == "Jordan Example" and cells[3] == "Y-3"


def test_split_raw_is_lossless():
    line = r"| Y3 \| SPOMA | [[contacts/jordan-example]] | Y-3 | — |"
    assert "|".join(split_raw(line)) == line


def test_read_table_rejects_a_row_wider_than_its_header():
    lines = ["| Canonical role | Role (as written) | Name |", "|---|---|---|",
             "| client_contact | Y3 | SPOMA | Jordan Example |"]  # unescaped pipe: 4 cells
    with pytest.raises(MalformedRow):
        read_table(lines, "Canonical role")


def test_read_table_accepts_escaped_rows():
    lines = ["| Canonical role | Role (as written) | Name |", "|---|---|---|",
             r"| client_contact | Y3 \| SPOMA | Jordan Example |"]
    header, rows = read_table(lines, "canonical role")
    assert rows == [["client_contact", "Y3 / SPOMA", "Jordan Example"]]


EXTRACT = """---
job_reference_number: 422
shoot_date: 2025-01-25
---

## Contacts

| Canonical role | Role (as written) | Name | Company | On set | Phone | Email |
|---|---|---|---|---|---|---|
{rows}
"""


def _sheet(tmp_path, rows):
    p = tmp_path / "2025-01-25-y3.md"
    p.write_text(EXTRACT.format(rows="\n".join(rows)), encoding="utf-8")
    return parse_callsheet(p)


def test_parse_callsheet_raises_on_an_unescaped_pipe(tmp_path):
    with pytest.raises(MalformedRow):
        _sheet(tmp_path, ["| client_contact | Y3 | SPOMA | Jordan Example | Y-3 | yes | unknown | unknown |"])


def test_parse_callsheet_keeps_name_and_company_in_place(tmp_path):
    sheet = _sheet(tmp_path, [ROW])
    p = sheet.people[0]
    assert (p.role_raw, p.name, p.company) == ("Y3 / SPOMA", "Jordan Example", "Y-3")


# --------------------------------------------------------------- B2 reconciliation

def test_every_row_is_accounted_for(tmp_path):
    sheet = _sheet(tmp_path, [
        ROW,
        "| photographer | PHOTOGRAPHER | Tim Walker | — | yes | unknown | unknown |",
        "| crew | RUNNER | Sam Smith | — | yes | unknown | unknown |",          # excluded by keep-list
        "| photographer | PHOTOGRAPHER | TBC | — | yes | unknown | unknown |",   # unfilled
        "| agent | AGENT (for Tim Walker, Photographer) | Jo Bloggs | CLM | no | +44 700 000 | unknown |",
    ])
    report = FilterReport()
    kept = filter_people(sheet, RoleVocabulary.load(), None, report)
    name, n, tally = report.reconciled[0]
    assert n == 5 and sum(tally.values()) == 5
    assert tally["kept"] == len(kept) == 2
    assert tally["agent_merged"] == 1 and tally["unfilled"] == 1 and tally["excluded_by_keep_list"] == 1


def test_a_lost_row_stops_the_run(tmp_path, monkeypatch):
    import wiki_filter
    sheet = _sheet(tmp_path, [ROW, "| photographer | PHOTOGRAPHER | Tim Walker | — | yes | unknown | unknown |"])
    real = wiki_filter._filter_people

    def leaky(sheet, vocab, staff, report, tally):  # simulates a filter path that forgets to count
        kept = real(sheet, vocab, staff, report, tally)
        tally["kept"] -= 1
        return kept[:-1]
    monkeypatch.setattr(wiki_filter, "_filter_people", leaky)
    with pytest.raises(ReconciliationError):
        filter_people(sheet, RoleVocabulary.load(), None, FilterReport())


# --------------------------------------------------------------- B3 quarantine

ROLES = q.role_words(RoleVocabulary.load())
COMPANIES = {q.norm(c) for c in ("adidas", "y-3", "matiere-noire", "new-balance", "universal-music", "farago-projects")}


@pytest.mark.parametrize("junk", ["ADIDAS", "SPOMA", "SALES", "PRODUCER", "PHOTOGRAPHER", "COMMS",
                                  "PR (ADIDAS)", "NEW BALANCE)", "MATIERE NOIRE", "CULTURE MARKETING",
                                  "SOCIALS AND DIGITAL", "Y3 \\", "UNIVERSAL MUSIC"])
def test_every_junk_contact_from_the_incident_is_quarantined(junk):
    assert q.contact_problems(junk, company_keys=COMPANIES, roles=ROLES)


@pytest.mark.parametrize("person", ["Jordan Example", "Remy Sample", "Inés Ejemplo", "Petrova Anastasia",
                                    "Taylor Ashby-Carter", "Minjun", "Liam O'Testing"])
def test_real_people_pass(person):
    assert q.contact_problems(person, company_keys=COMPANIES, roles=ROLES,
                              existing_contacts={"lenabruening": "lena-bruening"}) == []


def test_spelling_variant_of_an_existing_contact_is_held():
    existing = {q.norm(s): s for s in ("lena-bruening", "kenta-morikawa", "maria-dacosta")}
    for name, slug in [("Lena Brüning", "lena-bruening"), ("Kenta Morikaw", "kenta-morikawa"),
                       ("Maria Da Costa", "maria-dacosta")]:
        why = q.contact_problems(name, company_keys=COMPANIES, roles=ROLES, existing_contacts=existing)
        assert any(slug in w for w in why), (name, why)


def test_initials_brackets_and_farago_staff_are_held():
    assert q.contact_problems("M.G", company_keys=COMPANIES, roles=ROLES)
    assert q.contact_problems("Kai Tanaka (at showroom)", company_keys=COMPANIES, roles=ROLES)
    assert q.contact_problems("Julien Testeur", company_keys=COMPANIES, roles=ROLES, company="Farago Projects Paris")


def test_person_named_companies_from_the_incident_are_quarantined():
    people = {q.norm(n) for n in ("Jordan Example", "Remy Sample", "Alex Placeholder")}
    assert q.company_problems("Jordan Example", person_keys=people, row_person="SPOMA", roles=ROLES)
    assert q.company_problems("Alex Placeholder", person_keys=set(), row_person="Alex Placeholder", roles=ROLES)
    assert q.company_problems("Farago Projects London", person_keys=set(), row_person="x", roles=ROLES)
    assert q.company_problems("Matière Noire", person_keys=people, row_person="Remy Sample", roles=ROLES) == []


# --------------------------------------------------------------- postprocess

PAGE = """# Y-3 FW25

## People

| Role | Name | Company / agency | Contact | Days |
|------|------|------------------|---------|------|
| Y3 / SPOMA | Jordan Example | adidas | — | 01-25 |
| Y3 / COMMS | Lena Brüning | Y-3 | — | 01-25 |
| TALENT | Talentname ⚠ | — | — | 01-24 |

## Source
"""


def test_wikilink_people_exact_and_alias_only():
    out = wikilink_people(PAGE, lambda n: "contacts/jordan-example.md" if n == "Jordan Example" else None,
                          {"Lena Brüning": "lena-bruening"})
    assert "| [[contacts/jordan-example]] |" in out
    assert "| [[contacts/lena-bruening]] |" in out
    assert "| Talentname ⚠ |" in out  # no match: stays plain text
    assert people_links(out) == [("jordan-example", "Y3 / SPOMA"), ("lena-bruening", "Y3 / COMMS")]


def test_wikilink_companies_keeps_the_employment_suffix_outside():
    page = PAGE.replace("| adidas |", "| Farago Projects `staff (UK)` |")
    out = wikilink_companies(page, lambda n: {"farago projects": "farago-projects", "y-3": "y-3"}.get(n.lower()))
    assert "| [[companies/farago-projects]] `staff (UK)` |" in out
    assert "| [[companies/y-3]] |" in out


def test_postprocess_refuses_a_malformed_people_row():
    bad = PAGE.replace("| TALENT | Talentname ⚠ | — | — | 01-24 |", "| TALENT | Talentname | x | — | — | 01-24 |")
    with pytest.raises(MalformedRow):
        wikilink_people(bad, lambda n: None)


def test_page_path_is_zero_padded():
    class FM:  # minimal Day stand-in for slug_for()
        def __init__(self, campaign):
            self.sheet = type("S", (), {"frontmatter": {"campaign": campaign}})()
    assert page_path("422", [FM("Y3 FW25 Presentation")]) == "callsheets/0422-y3-fw25-presentation.md"
