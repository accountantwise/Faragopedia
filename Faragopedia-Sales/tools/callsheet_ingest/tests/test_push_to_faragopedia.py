"""Stage-4 orchestration: collecting extracts into per-job Day lists and reporting.

collect() reads from the module-level EXTRACTS path, so these tests monkeypatch that
constant to a tmp_path directory of fixture extracts rather than touching the real
callsheets-md/ corpus (which is gitignored, holds real people's contact details, and
should never be a test dependency).
"""

import push_to_faragopedia as ptf
from wiki_filter import RoleVocabulary

CURRENT_SCHEMA = """---
production: TEST SHOOT
campaign: Test Campaign
shoot_date: 2026-01-22
job_reference_number: {job}
job_folder_key: job-{job}
---

## Contacts

| Canonical role | Role (verbatim) | Name | Company / agency | On set | Phone | Email |
|----------------|-----------------|------|------------------|--------|-------|-------|
| photographer | PHOTOGRAPHER | Tim Walker | unknown | yes | unknown | unknown |
| crew | GRIP | Sam Lee | unknown | yes | unknown | unknown |
"""

PRE_REWORK_SCHEMA = """---
job_reference_number: 999
---

## Contacts

| Role | Name | Company | Phone |
|------|------|---------|-------|
| Photographer | Tim Walker | unknown | unknown |
"""


def write_extract(dir_, name, content):
    (dir_ / name).write_text(content, encoding="utf-8")


def test_collect_groups_multiple_days_under_one_job(tmp_path, monkeypatch):
    write_extract(tmp_path, "day1.md", CURRENT_SCHEMA.format(job="526"))
    write_extract(tmp_path, "day2.md", CURRENT_SCHEMA.format(job="526"))
    monkeypatch.setattr(ptf, "EXTRACTS", tmp_path)
    monkeypatch.setattr(RoleVocabulary, "load", classmethod(
        lambda cls, path=None: cls({
            "roles": {"photographer": {"wiki_keep": True, "aliases": ["Photographer"]},
                      "crew": {"wiki_keep": False, "aliases": ["Grip"]}},
            "patterns": [], "not_people": [],
        })))
    by_job, report, staff = ptf.collect()
    assert list(by_job.keys()) == ["526"]
    assert len(by_job["526"]) == 2


def test_collect_reports_pre_rework_extracts_as_schema_skipped(tmp_path, monkeypatch):
    write_extract(tmp_path, "old.md", PRE_REWORK_SCHEMA)
    monkeypatch.setattr(ptf, "EXTRACTS", tmp_path)
    monkeypatch.setattr(RoleVocabulary, "load", classmethod(
        lambda cls, path=None: cls({"roles": {}, "patterns": [], "not_people": []})))
    by_job, report, staff = ptf.collect()
    assert by_job == {}
    assert report.schema_skipped == [("old.md", "no canonical-role column (pre-rework schema)")]


def test_collect_job_filter_excludes_other_jobs(tmp_path, monkeypatch):
    write_extract(tmp_path, "job1.md", CURRENT_SCHEMA.format(job="100"))
    write_extract(tmp_path, "job2.md", CURRENT_SCHEMA.format(job="200"))
    monkeypatch.setattr(ptf, "EXTRACTS", tmp_path)
    monkeypatch.setattr(RoleVocabulary, "load", classmethod(
        lambda cls, path=None: cls({
            "roles": {"photographer": {"wiki_keep": True, "aliases": ["Photographer"]},
                      "crew": {"wiki_keep": False, "aliases": ["Grip"]}},
            "patterns": [], "not_people": [],
        })))
    by_job, report, staff = ptf.collect(job_filter="100")
    assert list(by_job.keys()) == ["100"]


def test_collect_filters_dropped_people_out_of_the_days(tmp_path, monkeypatch):
    write_extract(tmp_path, "day1.md", CURRENT_SCHEMA.format(job="526"))
    monkeypatch.setattr(ptf, "EXTRACTS", tmp_path)
    monkeypatch.setattr(RoleVocabulary, "load", classmethod(
        lambda cls, path=None: cls({
            "roles": {"photographer": {"wiki_keep": True, "aliases": ["Photographer"]},
                      "crew": {"wiki_keep": False, "aliases": ["Grip"]}},
            "patterns": [], "not_people": [],
        })))
    by_job, report, staff = ptf.collect()
    day = by_job["526"][0]
    assert [p.name for p in day.people] == ["Tim Walker"]
    assert report.dropped == [("Sam Lee", "GRIP", "crew")]
