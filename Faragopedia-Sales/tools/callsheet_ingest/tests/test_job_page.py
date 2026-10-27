"""Stage-4 assembly: rostering people across days, slug generation, and page rendering.

Uses real Callsheet/Person objects from wiki_filter rather than mocks — the roster
merge logic is about real dataclass fields (contact_via, phone/email/company
back-fill), and a mock would hide exactly the bugs this guards against.
"""

from pathlib import Path

import pytest

from job_page import Day, _resolver_url, _services, build_roster, render_job_page, slug_for
from wiki_filter import Callsheet, Person


def make_person(canonical="crew_lead", name="Alex Chen", role_raw="Gaffer",
                 company="unknown", phone="unknown", email="unknown") -> Person:
    return Person(canonical, role_raw, name, company, "yes", phone, email)


def make_day(frontmatter: dict, people: list[Person], services=None, locations=None) -> Day:
    sheet = Callsheet(Path("fake.md"), frontmatter, [], services or [], [],
                       locations or [], "")
    return Day(sheet, people)


# --- slug_for -------------------------------------------------------------------------

def test_slug_for_uses_campaign_name():
    day = make_day({"campaign": "McQueen Manta"}, [])
    assert slug_for("526", [day]) == "job-526-mcqueen-manta"


def test_slug_for_falls_back_to_production_when_no_campaign():
    day = make_day({"production": "Range Rover Launch"}, [])
    assert slug_for("549", [day]) == "job-549-range-rover-launch"


def test_slug_for_falls_back_to_job_when_neither_present():
    day = make_day({}, [])
    assert slug_for("300", [day]) == "job-300-job"


def test_slug_for_strips_punctuation_and_lowercases():
    day = make_day({"campaign": "COS: Summer In The City!"}, [])
    assert slug_for("400", [day]) == "job-400-cos-summer-in-the-city"


# --- build_roster: dedup, contact merge, talent non-merge ------------------------------

def test_build_roster_dedupes_same_person_across_days_by_role_and_name():
    p1 = make_person(canonical="photographer", name="Tim Walker")
    p2 = make_person(canonical="photographer", name="Tim Walker")
    day1 = make_day({"shoot_date": "2026-01-22"}, [p1])
    day2 = make_day({"shoot_date": "2026-01-23"}, [p2])
    roster = build_roster([day1, day2])
    assert len(roster) == 1
    person, dates = roster[0]
    assert dates == ["2026-01-22", "2026-01-23"]


def test_build_roster_same_name_different_role_is_two_rows():
    p1 = make_person(canonical="photographer", name="Jo Smith")
    p2 = make_person(canonical="crew_lead", name="Jo Smith", role_raw="Gaffer")
    day = make_day({"shoot_date": "2026-01-22"}, [p1, p2])
    roster = build_roster([day])
    assert len(roster) == 2


def test_build_roster_never_merges_talent_across_days():
    # Talent names are deliberately unreliable placeholders — repetition across days is
    # not evidence of the same person, so each appearance must stand on its own.
    t1 = make_person(canonical="talent", name="TALENT A")
    t2 = make_person(canonical="talent", name="TALENT A")
    day1 = make_day({"shoot_date": "2026-01-22"}, [t1])
    day2 = make_day({"shoot_date": "2026-01-23"}, [t2])
    roster = build_roster([day1, day2])
    assert len(roster) == 2


def test_build_roster_never_merges_two_talent_rows_on_the_same_day():
    # An artist credited for two separate works on one event day (job 531: Shaan Bevan,
    # "Cerebral Cortex" via Palmer Gallery and "Specular Orefield" via Jala Wahid) is two
    # appearances, not one — merging them silently drops the second work's credit and
    # gallery contact. (canonical, name, shoot_date) alone is not a unique key here
    # because both rows share all three.
    credit_1 = make_person(canonical="talent", name="Shaan Bevan",
                            role_raw="ARTIST COLLABORATOR (Cerebral Cortex)",
                            company="c/o Palmer Gallery")
    credit_2 = make_person(canonical="talent", name="Shaan Bevan",
                            role_raw="ARTIST COLLABORATOR (Specular Orefield)",
                            company="c/o Jala Wahid")
    day = make_day({"shoot_date": "2026-02-18"}, [credit_1, credit_2])
    roster = build_roster([day])
    assert len(roster) == 2
    companies = {p.company for p, _ in roster}
    assert companies == {"c/o Palmer Gallery", "c/o Jala Wahid"}


def test_build_roster_merges_contact_via_without_duplicating():
    p1 = make_person(canonical="photographer", name="Tim Walker")
    p1.contact_via = ["Camilla Lowther, CL Agency, +44 780"]
    p2 = make_person(canonical="photographer", name="Tim Walker")
    p2.contact_via = ["Camilla Lowther, CL Agency, +44 780"]
    day1 = make_day({"shoot_date": "2026-01-22"}, [p1])
    day2 = make_day({"shoot_date": "2026-01-23"}, [p2])
    roster = build_roster([day1, day2])
    assert roster[0][0].contact_via == ["Camilla Lowther, CL Agency, +44 780"]


def test_build_roster_backfills_missing_contact_detail_from_later_day():
    p1 = make_person(canonical="photographer", name="Tim Walker", phone="unknown")
    p2 = make_person(canonical="photographer", name="Tim Walker", phone="+44 780 000")
    day1 = make_day({"shoot_date": "2026-01-22"}, [p1])
    day2 = make_day({"shoot_date": "2026-01-23"}, [p2])
    roster = build_roster([day1, day2])
    assert roster[0][0].phone == "+44 780 000"


def test_build_roster_orders_by_seniority_not_alphabetically():
    photographer = make_person(canonical="photographer", name="Zed Zephyr")
    crew_lead = make_person(canonical="crew_lead", name="Amy Adams")
    day = make_day({"shoot_date": "2026-01-22"}, [photographer, crew_lead])
    roster = build_roster([day])
    assert [p.name for p, _ in roster] == ["Zed Zephyr", "Amy Adams"]


def test_build_roster_ranks_compound_role_by_its_most_senior_part():
    # "photographer + director" (one person wearing two hats, per EXTRACTION.md's
    # compound-role rule) is not itself in ROLE_ORDER, so it must not silently fall to
    # the bottom of the roster — Simon's rule is "a reader is looking for the
    # photographer", and that's exactly who this row is.
    compound = make_person(canonical="photographer + director", name="Aidan Zamiri")
    crew_lead = make_person(canonical="crew_lead", name="Amy Adams")
    day = make_day({"shoot_date": "2026-01-22"}, [crew_lead, compound])
    roster = build_roster([day])
    assert [p.name for p, _ in roster] == ["Aidan Zamiri", "Amy Adams"]


# --- _services: dedup across days ------------------------------------------------------

def test_services_dedupes_same_provider_across_days():
    day1 = make_day({}, [], services=[("Medic", "Nurse Joy", "unknown")])
    day2 = make_day({}, [], services=[("Medic", "Nurse Joy", "unknown")])
    assert _services([day1, day2]) == [("Medic", "Nurse Joy", "unknown")]


def test_services_prefers_a_day_that_has_the_phone_number():
    day1 = make_day({}, [], services=[("Medic", "Nurse Joy", "unknown")])
    day2 = make_day({}, [], services=[("Medic", "Nurse Joy", "+44 700 000")])
    assert _services([day1, day2]) == [("Medic", "Nurse Joy", "+44 700 000")]


# --- _resolver_url ------------------------------------------------------------------

def test_resolver_url_raises_when_wiki_url_unset(monkeypatch):
    monkeypatch.delenv("FARAGOPEDIA_WIKI_URL", raising=False)
    with pytest.raises(RuntimeError, match="FARAGOPEDIA_WIKI_URL"):
        _resolver_url("job-526")


def test_resolver_url_builds_from_env(monkeypatch):
    monkeypatch.setenv("FARAGOPEDIA_WIKI_URL", "https://faragopedia.accountantwise.uk/")
    assert _resolver_url("job-526") == "https://faragopedia.accountantwise.uk/api/job/job-526"


# --- render_job_page: presentation decisions that must not silently regress ------------

def test_render_job_page_omits_call_times(monkeypatch):
    # Call times are parsed and kept in callsheets-md/, but deliberately never rendered —
    # day-of-shoot operational detail, worthless months later. A regression here would
    # leak it back onto the page.
    day = make_day({"campaign": "Test", "client": "Acme", "shoot_date": "2026-01-22",
                     "job_folder_key": "job-526"}, [])
    monkeypatch.setenv("FARAGOPEDIA_WIKI_URL", "https://faragopedia.accountantwise.uk")
    page = render_job_page("526", [day], None)
    assert "08:00" not in page


def test_render_job_page_marks_talent_caveat_with_warning_symbol(monkeypatch):
    talent = make_person(canonical="talent", name="TALENT A")
    talent.caveat = "Name as printed on the callsheet; may be a placeholder."
    day = make_day({"campaign": "Test", "shoot_date": "2026-01-22",
                     "job_folder_key": "job-526"}, [talent])
    monkeypatch.setenv("FARAGOPEDIA_WIKI_URL", "https://faragopedia.accountantwise.uk")
    page = render_job_page("526", [day], None)
    assert "TALENT A ⚠" in page
    assert "Talent names may be placeholders" in page


def test_render_job_page_notes_multiple_campaigns_share_one_page(monkeypatch):
    day1 = make_day({"campaign": "COS A", "shoot_date": "2026-01-22",
                      "job_folder_key": "job-534"}, [])
    day2 = make_day({"campaign": "COS B", "shoot_date": "2026-01-23",
                      "job_folder_key": "job-534"}, [])
    monkeypatch.setenv("FARAGOPEDIA_WIKI_URL", "https://faragopedia.accountantwise.uk")
    page = render_job_page("534", [day1, day2], None)
    assert "This job covers 2 campaigns" in page
    assert "### COS A" in page
    assert "### COS B" in page


def test_render_job_page_escapes_pipe_characters_in_source_filename(monkeypatch):
    day = make_day({"campaign": "Test", "shoot_date": "2026-01-22",
                     "job_folder_key": "job-526",
                     "source_filename": "MCQ CALL SHEET | PRELIGHT 22 JAN.xlsx"}, [])
    monkeypatch.setenv("FARAGOPEDIA_WIKI_URL", "https://faragopedia.accountantwise.uk")
    page = render_job_page("526", [day], None)
    assert "MCQ CALL SHEET \\| PRELIGHT 22 JAN.xlsx" in page


def test_render_job_page_states_city_is_farago_office_not_shoot_location(monkeypatch):
    day = make_day({"campaign": "Test", "shoot_date": "2026-01-22", "city": "London",
                     "job_folder_key": "job-526"}, [])
    monkeypatch.setenv("FARAGOPEDIA_WIKI_URL", "https://faragopedia.accountantwise.uk")
    page = render_job_page("526", [day], None)
    assert "Run out of the London office" in page
