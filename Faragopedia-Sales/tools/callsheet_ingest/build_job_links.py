"""Build the job-folder link table and push it to Faragopedia.

    python build_job_links.py --dry-run     # resolve and print, upload nothing
    python build_job_links.py               # resolve and PUT the table

Wiki pages carry a key (`job-526`), not a URL. This resolves each key to wherever that
job's folder currently lives and replaces the table behind `GET /api/job/{key}`. Pages
are never rewritten, so re-running this after a Dropbox reorganisation re-points every
link across the wiki.

Keyed on the Dropbox folder ID, not its path. IDs survive moves and renames — the whole
point, since the archive is actively reorganised and `00_Current Jobs` folders migrate
into `01_Past Shoots` as jobs wrap. The stored URL is derived from the ID each run, so a
folder that moved yesterday resolves correctly today.

Run this:
  - after any push of new job pages, so their keys resolve;
  - whenever folders have been moved or renamed in Dropbox;
  - after the migration to Google Drive, against Drive instead (see MIGRATION below).

MIGRATION. Post-cutover the table holds Drive folder IDs and
`https://drive.google.com/drive/folders/<id>` URLs, which are ID-based and so immune to
reorganisation by construction. Only this script changes; the resolver, the pages and
the keys all stay as they are.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

HERE = Path(__file__).parent
MANIFEST = HERE / "manifest.json"

JOB_SEGMENT = re.compile(r"^(\d{3})(?:[:\-]\d{3})?[_ -]")
DUPLICATE_FOLDER = re.compile(r"\s*\(\d+\)\s*$")


def job_folders_from_manifest() -> dict[str, str]:
    """{job number: job folder path} for every extracted callsheet.

    Anchors on the job-number segment and reads upward, never counting directory levels
    — depth in this archive ranges from 8 to 13. Strips Dropbox's "(1)" duplicate-folder
    suffix so both copies of a job resolve to the real folder, matching
    canonical_job_folder in backfill_source_pointers.py.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    out: dict[str, str] = {}
    for entry in manifest.values():
        if entry.get("status") != "done":
            continue
        segments = entry["dropbox_path"].strip("/").split("/")
        for i, seg in enumerate(segments):
            m = JOB_SEGMENT.match(seg)
            if m:
                folder = "/" + "/".join(segments[: i + 1])
                head, _, tail = folder.rpartition("/")
                out.setdefault(m.group(1), f"{head}/{DUPLICATE_FOLDER.sub('', tail)}")
                break
    return out


def dropbox_client():
    import dropbox
    from dropbox.common import PathRoot

    dbx = dropbox.Dropbox(
        oauth2_refresh_token=os.environ["DROPBOX_REFRESH_TOKEN"],
        app_key=os.environ["DROPBOX_APP_KEY"],
        app_secret=os.environ["DROPBOX_APP_SECRET"],
    )
    # All content lives in the team root namespace; the default root sees almost nothing.
    ns = dbx.users_get_current_account().root_info.root_namespace_id
    return dbx.with_path_root(PathRoot.root(ns))


def dropbox_web_url(path: str) -> str:
    """Dropbox resolves /home/<path> against the signed-in user's namespace, which for a
    team member includes the team folders. Someone without permission on the folder gets
    Dropbox's own access screen, which is expected rather than a broken link."""
    return "https://www.dropbox.com/home" + quote(path, safe="/")


def resolve(dbx, folders: dict[str, str]) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    import dropbox

    links, failures = {}, []
    for job, path in sorted(folders.items()):
        try:
            md = dbx.files_get_metadata(path)
            # Re-read by ID so the recorded path is whatever Dropbox says today, not what
            # the manifest captured at harvest time.
            current = dbx.files_get_metadata(md.id)
            links[f"job-{job}"] = {
                "provider": "dropbox",
                "id": md.id,
                "path": current.path_display,
                "url": dropbox_web_url(current.path_display),
            }
        except dropbox.exceptions.ApiError as e:
            # Reported, never guessed. A job whose folder has been moved out of the
            # harvested scope needs a human to say where it went.
            failures.append((job, str(e)[:160]))
    return links, failures


def main() -> int:
    load_dotenv(HERE / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="resolve and print, upload nothing")
    args = ap.parse_args()

    folders = job_folders_from_manifest()
    print(f"jobs with extracted callsheets: {len(folders)}")
    if not folders:
        print("nothing to resolve — no manifest entry is marked done")
        return 1

    links, failures = resolve(dropbox_client(), folders)
    for key, entry in links.items():
        moved = entry["path"] != folders[key.removeprefix("job-")]
        print(f"  {key:12} {entry['id']:26} {'MOVED SINCE HARVEST' if moved else ''}")
        print(f"               {entry['path']}")
    if failures:
        print(f"\nUNRESOLVED ({len(failures)}) — these keys will 404 until fixed:")
        for job, err in failures:
            print(f"  job-{job}: {err}")

    if args.dry_run:
        print(f"\ndry run — {len(links)} link(s) resolved, nothing uploaded")
        return 0

    from faragopedia_client import Faragopedia

    api = Faragopedia()
    res = api.put_job_links(links)
    print(f"\ntable replaced: {res.get('count')} link(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
