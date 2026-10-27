"""Job-folder link table: anchoring on the job-number path segment, stripping Dropbox's
duplicate-folder suffix, and resolving via a fake Dropbox client.

job_folders_from_manifest() reads from the module-level MANIFEST path, so tests
monkeypatch that constant to a tmp_path fixture rather than touching the real
(gitignored) manifest.json.
"""

import json

import build_job_links as bjl
from build_job_links import dropbox_web_url, job_folders_from_manifest, resolve


def write_manifest(path, entries: dict):
    path.write_text(json.dumps({"files": entries}), encoding="utf-8")


def entry(dropbox_path, status="done"):
    return {"status": status, "dropbox_path": dropbox_path}


# --- job_folders_from_manifest: anchoring and dedup -------------------------------------

def test_anchors_on_job_segment_regardless_of_depth(tmp_path, monkeypatch):
    write_manifest(tmp_path / "manifest.json", {
        "a": entry("/Sylvia Farago LTD Team Folder/01_Past Shoots/2026/London/"
                    "ADVERTISING/526_MCQUEEN MANTA SHOOT/PRODUCTION/sheet.xlsx"),
    })
    monkeypatch.setattr(bjl, "MANIFEST", tmp_path / "manifest.json")
    folders = job_folders_from_manifest()
    assert folders == {
        "526": "/Sylvia Farago LTD Team Folder/01_Past Shoots/2026/London/"
               "ADVERTISING/526_MCQUEEN MANTA SHOOT",
    }


def test_matches_range_form_job_segment(tmp_path, monkeypatch):
    write_manifest(tmp_path / "manifest.json", {
        "a": entry("/Team Folder/01_Past Shoots/2026/London/EDITORIAL/"
                    "446:449_VAARA/PRODUCTION/sheet.xlsx"),
    })
    monkeypatch.setattr(bjl, "MANIFEST", tmp_path / "manifest.json")
    folders = job_folders_from_manifest()
    assert "446" in folders
    assert folders["446"].endswith("446:449_VAARA")


def test_skips_entries_not_marked_done(tmp_path, monkeypatch):
    write_manifest(tmp_path / "manifest.json", {
        "a": entry("/Team/01_Past Shoots/2026/London/ADVERTISING/526_JOB/sheet.xlsx",
                   status="pending"),
    })
    monkeypatch.setattr(bjl, "MANIFEST", tmp_path / "manifest.json")
    assert job_folders_from_manifest() == {}


def test_strips_duplicate_folder_suffix(tmp_path, monkeypatch):
    write_manifest(tmp_path / "manifest.json", {
        "a": entry("/Team/01_Past Shoots/2026/London/ADVERTISING/"
                    "526_MCQUEEN MANTA SHOOT (1)/PRODUCTION/sheet.xlsx"),
    })
    monkeypatch.setattr(bjl, "MANIFEST", tmp_path / "manifest.json")
    folders = job_folders_from_manifest()
    assert folders["526"] == "/Team/01_Past Shoots/2026/London/ADVERTISING/526_MCQUEEN MANTA SHOOT"


def test_first_seen_folder_wins_for_a_job_number(tmp_path, monkeypatch):
    # setdefault semantics: two manifest entries with the same job number resolve to
    # whichever folder was seen first, not the last.
    write_manifest(tmp_path / "manifest.json", {
        "a": entry("/Team/2026/London/ADVERTISING/526_FIRST/sheet1.xlsx"),
        "b": entry("/Team/2026/London/ADVERTISING/526_SECOND/sheet2.xlsx"),
    })
    monkeypatch.setattr(bjl, "MANIFEST", tmp_path / "manifest.json")
    folders = job_folders_from_manifest()
    assert folders["526"].endswith("526_FIRST")


def test_no_job_segment_in_path_is_silently_skipped(tmp_path, monkeypatch):
    write_manifest(tmp_path / "manifest.json", {
        "a": entry("/Team/Miscellaneous/random-notes.xlsx"),
    })
    monkeypatch.setattr(bjl, "MANIFEST", tmp_path / "manifest.json")
    assert job_folders_from_manifest() == {}


# --- dropbox_web_url ---------------------------------------------------------------------

def test_dropbox_web_url_quotes_path_but_keeps_slashes():
    url = dropbox_web_url("/Team Folder/526_MCQUEEN MANTA SHOOT")
    assert url == "https://www.dropbox.com/home/Team%20Folder/526_MCQUEEN%20MANTA%20SHOOT"


# --- resolve: fake dropbox client --------------------------------------------------------

class FakeMetadata:
    def __init__(self, id_, path_display):
        self.id = id_
        self.path_display = path_display


class FakeDropboxClient:
    """resolve() calls files_get_metadata twice per job: once by path (the manifest's
    harvested location) and once by the returned ID (today's location) — modelling a
    folder move requires the two calls to answer differently."""

    def __init__(self, by_path: dict, by_id: dict):
        self.by_path = by_path
        self.by_id = by_id

    def files_get_metadata(self, arg):
        return self.by_path[arg] if arg in self.by_path else self.by_id[arg]


def test_resolve_returns_link_with_dropbox_id_and_url():
    dbx = FakeDropboxClient(
        by_path={"/Team/526_JOB": FakeMetadata("id123", "/Team/526_JOB")},
        by_id={"id123": FakeMetadata("id123", "/Team/526_JOB")},
    )
    links, failures = resolve(dbx, {"526": "/Team/526_JOB"})
    assert failures == []
    assert links["job-526"]["id"] == "id123"
    assert links["job-526"]["path"] == "/Team/526_JOB"
    assert links["job-526"]["url"] == "https://www.dropbox.com/home/Team/526_JOB"


def test_resolve_flags_folders_that_moved_since_harvest():
    dbx = FakeDropboxClient(
        by_path={"/Team/526_OLD_NAME": FakeMetadata("id123", "/Team/526_OLD_NAME")},
        by_id={"id123": FakeMetadata("id123", "/Team/526_NEW_NAME")},
    )
    links, failures = resolve(dbx, {"526": "/Team/526_OLD_NAME"})
    assert links["job-526"]["path"] == "/Team/526_NEW_NAME"


def test_resolve_reports_failure_without_guessing():
    import dropbox

    class RaisingDbx:
        def files_get_metadata(self, path):
            raise dropbox.exceptions.ApiError("req-id", "not_found", "user message", "localized")

    links, failures = resolve(RaisingDbx(), {"526": "/Team/526_MOVED_OUT_OF_SCOPE"})
    assert links == {}
    assert len(failures) == 1
    assert failures[0][0] == "526"
