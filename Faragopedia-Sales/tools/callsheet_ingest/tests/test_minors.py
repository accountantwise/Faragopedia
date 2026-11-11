"""Children on callsheets never reach the wiki (ADR 0011).

All names here are invented. This repo is public: never put a real child's name, a
parent's name or an agency phone number from a callsheet into a test.
"""
from pathlib import Path

from job_page import Day, render_job_page
from minors import agency_of, is_kids_job, why_withheld, withhold_minors
from quarantine import care_of_company, company_problems
from wiki_filter import Callsheet, Person


def person(canonical="talent", name="Testchild", role_raw="MODEL", company="unknown",
           phone="unknown", contact_via=None) -> Person:
    p = Person(canonical, role_raw, name, company, "yes", phone, "unknown")
    p.contact_via = list(contact_via or [])
    return p


def day(people, campaign="Brand SS26", shoot_date="2026-05-21") -> Day:
    fm = {"campaign": campaign, "shoot_date": shoot_date, "client": "Brand", "category": "Advertising",
          "city": "London", "job_folder_key": "job-900"}
    return Day(Callsheet(Path("fake.md"), fm, [], [], [], [], ""), list(people))


def test_kids_job_detected_from_campaign():
    assert is_kids_job([day([], campaign="Brand Kids | Summer")])
    assert is_kids_job([day([], campaign="Brand Baby Marine")])
    assert not is_kids_job([day([], campaign="Brand Man SS26")])


def test_all_talent_on_a_kids_job_is_withheld_but_crew_is_kept():
    crew = person(canonical="photographer", name="Pat Lens", role_raw="PHOTOGRAPHER")
    kid = person(name="Testchild", phone="+44 7000 000 001",
                 company="c/o Parentname, agent Agentname @ Example Kids Agency")
    days = [day([crew, kid], campaign="Brand Kids Flower Patchwork")]
    w = withhold_minors(days)
    assert days[0].people == [crew]
    assert w.children == {"testchild"}
    assert w.agencies == ["Example Kids Agency"]
    note = w.note()
    assert "1 child model" in note and "Example Kids Agency" in note
    assert "Testchild" not in note and "Parentname" not in note and "7000" not in note


def test_child_actor_on_an_adult_job_is_withheld_by_role_or_agency():
    adult = person(name="Band Member", role_raw="BAND / EXAMPLE BAND")
    young = person(name="Kidactor", role_raw="YOUNG LEAD")
    friend = person(name="Kidfriend", role_raw="FRIEND",
                    contact_via=["Agentname, Example Kidz, +44 7000 000 002"])
    mother = person(canonical="other", name="Parent Person", role_raw="MOTHER")
    days = [day([adult, young, friend, mother], campaign="Example Band Music Video")]
    w = withhold_minors(days)
    assert days[0].people == [adult]
    assert w.children == {"kidactor", "kidfriend"} and w.parents == {"parent person"}
    assert w.actors
    assert "**2 child actors** and 1 parent" in w.note()


def test_adult_talent_with_care_of_brand_is_kept():
    # 'c/o <brand>' alone is not a child signal: an adult model booked via the client.
    assert why_withheld(person(name="Adult Model", company="c/o Brand"), kids_job=False) is None


def test_agency_from_contact_via_skips_phone_and_email():
    p = person(contact_via=["Agentname, Example Kids Ltd, +44 7000 000 003"])
    assert agency_of(p) == "Example Kids Ltd"


def test_rendered_page_has_no_child_and_carries_the_note(monkeypatch):
    monkeypatch.setenv("FARAGOPEDIA_WIKI_URL", "https://wiki.example")
    kid = person(name="Testchild", phone="+44 7000 000 004")
    crew = person(canonical="photographer", name="Pat Lens", role_raw="PHOTOGRAPHER")
    days = [day([crew, kid], campaign="Brand Kids SS26")]
    w = withhold_minors(days)
    page = render_job_page("900", days, None, w.note())
    assert "Testchild" not in page and "7000 000 004" not in page
    assert "1 child model" in page and "Pat Lens" in page


def test_care_of_agent_route_becomes_the_agency():
    assert care_of_company("c/o Parentname, agent Agentname @ Example Kids Agency") == "Example Kids Agency"
    assert care_of_company("Example Studio") == "Example Studio"


def test_bare_care_of_company_is_quarantined():
    why = company_problems("c/o Example Magazine", person_keys=set(), row_person="AB", roles=set())
    assert any("c/o" in w for w in why)
