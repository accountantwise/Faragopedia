"""Stage-4 filtering: canonical role resolution, the keep-list, supplier detection,
placeholder/agent handling, and callsheet parsing.

Fixtures build minimal RoleVocabulary/Person/Callsheet objects directly rather than
loading the real roles.yml, so a test failure points at wiki_filter.py and not at a
future edit to the vocabulary file.
"""

from pathlib import Path

from wiki_filter import (
    Callsheet,
    FilterReport,
    Person,
    RoleVocabulary,
    _is_separator,
    _split_row,
    filter_people,
    is_supplier,
    parse_callsheet,
    resolve_canonical,
)


def make_vocab(roles: dict, patterns=None, not_people=None) -> RoleVocabulary:
    return RoleVocabulary({
        "roles": roles,
        "patterns": patterns or [],
        "not_people": not_people or [],
    })


def make_person(canonical="crew", role_raw="Grip", name="Jane Doe", company="unknown",
                 on_set="yes", phone="unknown", email="unknown") -> Person:
    return Person(canonical, role_raw, name, company, on_set, phone, email)


# --- RoleVocabulary.resolve --------------------------------------------------------

def test_resolve_exact_alias_match():
    vocab = make_vocab({"photographer": {"aliases": ["Photographer"]}})
    assert vocab.resolve("Photographer") == "photographer"


def test_resolve_alias_match_is_case_insensitive():
    vocab = make_vocab({"photographer": {"aliases": ["Photographer"]}})
    assert vocab.resolve("PHOTOGRAPHER") == "photographer"


def test_resolve_falls_through_to_pattern():
    vocab = make_vocab(
        {"assistant": {"aliases": []}},
        patterns=[{"shape": r"(?i)assistant", "canonical": "assistant"}],
    )
    assert vocab.resolve("Photo Assistant") == "assistant"


def test_resolve_alias_wins_over_pattern():
    # "Hair Stylist" must resolve to hair_lead, never be swallowed by a /stylist/ shape.
    vocab = make_vocab(
        {"hair_lead": {"aliases": ["Hair Stylist"]}, "stylist_lead": {"aliases": []}},
        patterns=[{"shape": r"(?i)stylist", "canonical": "stylist_lead"}],
    )
    assert vocab.resolve("Hair Stylist") == "hair_lead"


def test_resolve_unmatched_role_is_other():
    vocab = make_vocab({"photographer": {"aliases": ["Photographer"]}})
    assert vocab.resolve("Someone Entirely New") == "other"


# --- RoleVocabulary.keep / caveat ---------------------------------------------------

def test_keep_reads_wiki_keep_flag():
    vocab = make_vocab({"photographer": {"wiki_keep": True}, "crew": {"wiki_keep": False}})
    assert vocab.keep("photographer") is True
    assert vocab.keep("crew") is False


def test_keep_defaults_true_for_canonical_absent_from_roles_yml():
    # A canonical the vocabulary has never seen is a divergence bug to surface, not a
    # person to hide — so the default has to be permissive, not restrictive.
    vocab = make_vocab({"photographer": {"wiki_keep": True}})
    assert vocab.keep("some_future_canonical") is True


def test_keep_can_return_represents_for_agent():
    vocab = make_vocab({"agent": {"wiki_keep": "represents"}})
    assert vocab.keep("agent") == "represents"


def test_caveat_returns_none_when_absent():
    vocab = make_vocab({"crew": {"wiki_keep": True}})
    assert vocab.caveat("crew") is None


def test_caveat_returns_configured_text():
    vocab = make_vocab({"talent": {"display_caveat": "may be a placeholder"}})
    assert vocab.caveat("talent") == "may be a placeholder"


# --- resolve_canonical: the asymmetric override rule --------------------------------

def test_resolve_canonical_keeps_recorded_when_it_matches_expected():
    vocab = make_vocab({"photographer": {"wiki_keep": True, "aliases": ["Photographer"]}})
    report = FilterReport()
    result = resolve_canonical(vocab, "photographer", "Photographer", report, "Tim Walker")
    assert result == "photographer"
    assert report.role_overrides == []
    assert report.role_trusted == []


def test_resolve_canonical_overrides_when_extract_would_drop_someone_roles_yml_keeps():
    # Extraction blanket-mapped the technical bench to `crew` (dropped); roles.yml has a
    # `crew_lead` tier for the same people that IS shown. This is the one direction the
    # rule overrides.
    vocab = make_vocab({
        "crew": {"wiki_keep": False, "aliases": []},
        "crew_lead": {"wiki_keep": True, "aliases": ["DOP"]},
    })
    report = FilterReport()
    result = resolve_canonical(vocab, "crew", "DOP", report, "Alex Chen")
    assert result == "crew_lead"
    assert report.role_overrides == [("Alex Chen", "DOP", "crew", "crew_lead")]


def test_resolve_canonical_does_not_override_the_other_direction():
    # "PRODUCER" under CLIENT is a brand producer; roles.yml's alias table would resolve
    # it to production_lead (Farago's producer). Both keep the person, so overriding here
    # only corrupts meaning — the extract's label (with the section heading) must win.
    vocab = make_vocab({
        "client_contact": {"wiki_keep": True, "aliases": []},
        "production_lead": {"wiki_keep": True, "aliases": ["Producer"]},
    })
    report = FilterReport()
    result = resolve_canonical(vocab, "client_contact", "Producer", report, "Oliver Mann")
    assert result == "client_contact"
    assert report.role_trusted == [("Oliver Mann", "Producer", "client_contact", "production_lead")]


def test_resolve_canonical_does_not_override_when_both_drop():
    # Neither label survives the keep-list, so overriding would be pure noise — the
    # trusted/overridden reports exist to be read, and a report nobody reads is useless.
    vocab = make_vocab({
        "crew": {"wiki_keep": False, "aliases": []},
        "assistant": {"wiki_keep": False, "aliases": ["Grip Assistant"]},
    })
    report = FilterReport()
    result = resolve_canonical(vocab, "crew", "Grip Assistant", report, "Sam Lee")
    assert result == "crew"
    assert report.role_overrides == []
    assert report.role_trusted == []


def test_resolve_canonical_reports_other_roles_before_the_keep_decision():
    vocab = make_vocab({"crew": {"wiki_keep": False, "aliases": []}})
    report = FilterReport()
    resolve_canonical(vocab, "crew", "Totally Uncatalogued Title", report, "Sam Lee")
    assert report.other_roles == [("Sam Lee", "Totally Uncatalogued Title")]


# --- is_supplier ---------------------------------------------------------------------

def test_is_supplier_true_for_not_people_role():
    vocab = make_vocab({}, not_people=["Hospital", "Medic"])
    p = make_person(role_raw="Medic", company="unknown")
    assert is_supplier(p, vocab) is True


def test_is_supplier_true_when_role_label_equals_company_name():
    vocab = make_vocab({})
    p = make_person(role_raw="Aquatic Impact", company="Aquatic Impact")
    assert is_supplier(p, vocab) is True


def test_is_supplier_false_for_ordinary_crew_member():
    vocab = make_vocab({})
    p = make_person(role_raw="Gaffer", company="unknown")
    assert is_supplier(p, vocab) is False


def test_is_supplier_false_when_company_is_placeholder_dash():
    vocab = make_vocab({})
    p = make_person(role_raw="—", company="—")
    assert is_supplier(p, vocab) is False


# --- filter_people: keep-list, agent merge, placeholders, suppliers -----------------

def base_vocab() -> RoleVocabulary:
    return make_vocab({
        "photographer": {"wiki_keep": True, "aliases": ["Photographer"]},
        "crew": {"wiki_keep": False, "aliases": ["Grip"]},
        "agent": {"wiki_keep": "represents", "aliases": ["Agent"]},
    }, not_people=["Medic"])


def make_sheet(people: list[Person]) -> Callsheet:
    return Callsheet(Path("fake.md"), {"shoot_date": "2026-01-22", "job_reference_number": "526"},
                     people, [], [], [], "")


def test_filter_people_drops_role_marked_false():
    sheet = make_sheet([make_person(canonical="crew", role_raw="Grip", name="Sam Lee")])
    report = FilterReport()
    kept = filter_people(sheet, base_vocab(), None, report)
    assert kept == []
    assert report.dropped == [("Sam Lee", "Grip", "crew")]


def test_filter_people_keeps_role_marked_true():
    sheet = make_sheet([make_person(canonical="photographer", role_raw="Photographer", name="Tim Walker")])
    report = FilterReport()
    kept = filter_people(sheet, base_vocab(), None, report)
    assert [p.name for p in kept] == ["Tim Walker"]


def test_filter_people_drops_placeholder_name():
    sheet = make_sheet([make_person(canonical="photographer", role_raw="Photographer", name="TBC")])
    report = FilterReport()
    kept = filter_people(sheet, base_vocab(), None, report)
    assert kept == []
    assert report.unfilled_roles == [("Photographer", "TBC")]


def test_filter_people_moves_supplier_to_services_not_people():
    sheet = make_sheet([make_person(canonical="photographer", role_raw="Medic", name="Nurse Joy",
                                     phone="+44 700 000")])
    report = FilterReport()
    kept = filter_people(sheet, base_vocab(), None, report)
    assert kept == []
    assert sheet.services == [("Medic", "Nurse Joy", "+44 700 000")]
    assert report.moved_to_services == [("Medic", "Nurse Joy")]


def test_filter_people_merges_agent_onto_kept_principal():
    sheet = make_sheet([
        make_person(canonical="photographer", role_raw="Photographer", name="Tim Walker"),
        make_person(canonical="agent", role_raw="Agent (for Tim Walker, Photographer)",
                    name="Camilla Lowther", company="CL Agency", phone="+44 780 000"),
    ])
    report = FilterReport()
    kept = filter_people(sheet, base_vocab(), None, report)
    assert [p.name for p in kept] == ["Tim Walker"]
    assert kept[0].contact_via == ["Camilla Lowther, CL Agency, +44 780 000"]


def test_filter_people_drops_agent_whose_principal_was_dropped():
    sheet = make_sheet([
        make_person(canonical="crew", role_raw="Grip", name="Sam Lee"),
        make_person(canonical="agent", role_raw="Agent (for Sam Lee, Grip)", name="An Agent"),
    ])
    report = FilterReport()
    kept = filter_people(sheet, base_vocab(), None, report)
    assert kept == []
    assert ("An Agent", "Agent (for Sam Lee, Grip)", "agent") in report.dropped


def test_filter_people_reports_orphan_agent_with_no_named_principal():
    sheet = make_sheet([make_person(canonical="agent", role_raw="Agent", name="An Agent",
                                     company="Some Agency")])
    report = FilterReport()
    kept = filter_people(sheet, base_vocab(), None, report)
    assert kept == []
    assert report.orphan_agents == [("An Agent", "Some Agency", "Agent")]


def test_filter_people_resolves_employment_for_farago_company_only():
    class FakeStaff:
        def classify(self, name, shoot_date):
            return "staff (UK)"

    sheet = make_sheet([make_person(canonical="photographer", role_raw="Photographer",
                                     name="Tim Walker", company="Farago Projects")])
    report = FilterReport()
    kept = filter_people(sheet, base_vocab(), FakeStaff(), report)
    assert kept[0].employment == "staff (UK)"


def test_filter_people_does_not_resolve_employment_for_non_farago_company():
    class FakeStaff:
        def classify(self, name, shoot_date):
            raise AssertionError("must not be called for a non-Farago company")

    sheet = make_sheet([make_person(canonical="photographer", role_raw="Photographer",
                                     name="Tim Walker", company="Alexander McQueen")])
    report = FilterReport()
    kept = filter_people(sheet, base_vocab(), FakeStaff(), report)
    assert kept[0].employment is None


# --- markdown table parsing helpers --------------------------------------------------

def test_split_row_strips_and_splits_cells():
    assert _split_row("| Name | Role |") == ["Name", "Role"]


def test_is_separator_true_for_rule_row():
    assert _is_separator(["------", ":---:"]) is True


def test_is_separator_false_for_row_with_no_hyphens():
    # Regression guard: an earlier version tested "is the row's charset a subset of
    # {'-', ':', ' '}" the wrong way round, which happened to also match ordinary rows
    # like a schedule time that contains no hyphen. Cells must actually contain "-"/":".
    assert _is_separator(["08:00", "Lighting call"]) is False


def test_is_separator_false_for_empty_row():
    assert _is_separator([]) is False


# --- parse_callsheet ------------------------------------------------------------------

CURRENT_SCHEMA_EXTRACT = """---
production: TEST SHOOT
campaign: Test Campaign
shoot_date: 2026-01-22
job_reference_number: 526
---

## Contacts

| Canonical role | Role (verbatim) | Name | Company / agency | On set | Phone | Email |
|----------------|-----------------|------|------------------|--------|-------|-------|
| photographer | PHOTOGRAPHER | Tim Walker | unknown | yes | unknown | unknown |

## Production services

| Service | Provider | Phone |
|---------|----------|-------|
| Medic | Nurse Joy | unknown |

## Schedule

| Time | Call |
|------|------|
| 08:00 | Lighting call |

## Locations

- London Film Studios (studio)
  - Parking available onsite.

## Notes

Some free-text note.
"""

PRE_REWORK_EXTRACT = """---
production: OLD SHOOT
job_reference_number: 1
---

## Contacts

| Role | Name | Company | Phone |
|------|------|---------|-------|
| Photographer | Tim Walker | unknown | unknown |
"""


def test_parse_callsheet_returns_none_without_frontmatter(tmp_path):
    path = tmp_path / "no-frontmatter.md"
    path.write_text("# Just a heading\n", encoding="utf-8")
    assert parse_callsheet(path) is None


def test_parse_callsheet_returns_none_for_pre_rework_schema(tmp_path):
    # No "Canonical role" column means no keep/drop decision can be made — this is the
    # loud-failure path, not a bug to fix, so the test pins it rather than "fixing" it.
    path = tmp_path / "pre-rework.md"
    path.write_text(PRE_REWORK_EXTRACT, encoding="utf-8")
    assert parse_callsheet(path) is None


def test_parse_callsheet_reads_people_from_current_schema(tmp_path):
    path = tmp_path / "current.md"
    path.write_text(CURRENT_SCHEMA_EXTRACT, encoding="utf-8")
    sheet = parse_callsheet(path)
    assert sheet is not None
    assert len(sheet.people) == 1
    assert sheet.people[0] == Person("photographer", "PHOTOGRAPHER", "Tim Walker",
                                      "unknown", "yes", "unknown", "unknown")


def test_parse_callsheet_reads_production_services(tmp_path):
    path = tmp_path / "current.md"
    path.write_text(CURRENT_SCHEMA_EXTRACT, encoding="utf-8")
    sheet = parse_callsheet(path)
    assert sheet.services == [("Medic", "Nurse Joy", "unknown")]


def test_parse_callsheet_reads_schedule(tmp_path):
    path = tmp_path / "current.md"
    path.write_text(CURRENT_SCHEMA_EXTRACT, encoding="utf-8")
    sheet = parse_callsheet(path)
    assert sheet.schedule == [("08:00", "Lighting call")]


def test_parse_callsheet_keeps_nested_location_notes_indented(tmp_path):
    path = tmp_path / "current.md"
    path.write_text(CURRENT_SCHEMA_EXTRACT, encoding="utf-8")
    sheet = parse_callsheet(path)
    assert sheet.locations == ["London Film Studios (studio)", "  Parking available onsite."]


def test_parse_callsheet_shoot_date_and_job_properties(tmp_path):
    path = tmp_path / "current.md"
    path.write_text(CURRENT_SCHEMA_EXTRACT, encoding="utf-8")
    sheet = parse_callsheet(path)
    assert sheet.shoot_date == "2026-01-22"
    assert sheet.job == "526"


def test_parse_callsheet_returns_none_when_contacts_table_has_no_people(tmp_path):
    text = """---
job_reference_number: 1
---

## Contacts

| Canonical role | Role (verbatim) | Name | Company / agency | On set | Phone | Email |
|----------------|-----------------|------|------------------|--------|-------|-------|
"""
    path = tmp_path / "empty.md"
    path.write_text(text, encoding="utf-8")
    assert parse_callsheet(path) is None
