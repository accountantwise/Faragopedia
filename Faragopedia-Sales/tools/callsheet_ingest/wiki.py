"""The live-wiki primitives the ingest scripts share: list, read, write, archive, snapshot.

(Formerly `ingest_as_agent.py` in the callsheet-migration folder. Its stub
`render_callsheet_page()` / `render_contact_page()` were left behind on purpose: the
callsheet stub produced 17 non-compliant pages on 2026-09-12. job_page.render_job_page()
is the only callsheet renderer; push_job.py renders contacts.)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import unicodedata
import zipfile
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

from faragopedia_client import Faragopedia, FaragopediaError  # noqa: E402

_api: Faragopedia | None = None
_pages_cache: dict[str, list[str]] | None = None


def api() -> Faragopedia:
    global _api
    if _api is None:
        _api = Faragopedia()
    return _api


def slugify(name: str) -> str:
    """'Seán McGirr' -> 'sean-mcgirr'. Transliterates accents rather than dropping them, and
    is THE page-slug rule: never hand-roll lower().replace(' ', '-') — it diverges on 'P.M'."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.strip().lower()).strip("-")


def all_pages(refresh: bool = False) -> dict[str, list[str]]:
    """Every folder -> page list in the live wiki. Cached per process; refresh=True after
    writing new pages so a later find_contact() sees them."""
    global _pages_cache
    if _pages_cache is None or refresh:
        r = api()._call("GET", "/api/pages")
        if not r.ok:
            raise FaragopediaError(f"GET /api/pages -> {r.status}: {r.body[:200]}")
        _pages_cache = json.loads(r.body)
    return _pages_cache


def find_contact(name: str) -> str | None:
    """contacts/<slug>.md if a page exists under the exact slug, else None. Exact only: two
    different people can share a near-identical name, so a near miss is never linked."""
    path = f"contacts/{slugify(name)}.md"
    return path if path in all_pages().get("contacts", []) else None


def find_company(name: str) -> str | None:
    if not name or name.lower() in ("unknown", "-", "—", ""):
        return None
    path = f"companies/{slugify(name)}.md"
    return path if path in all_pages().get("companies", []) else None


def get_page(path: str) -> str:
    r = api()._call("GET", f"/api/pages/{path}")
    if not r.ok:
        raise FaragopediaError(f"GET {path} -> {r.status}: {r.body[:200]}")
    return (r.json() or {}).get("content", "")


def write_page(path: str, content: str) -> dict:
    """Create or overwrite. PUT accepts anything with a 200 — check structure, not status."""
    r = api()._call("PUT", f"/api/pages/{path}",
                    ["-H", "Content-Type: application/json", "-d", json.dumps({"content": content})])
    if not r.ok:
        raise FaragopediaError(f"PUT {path} -> {r.status}: {r.body[:300]}")
    return r.json() or {}


def archive_pages(paths: list[str]) -> None:
    """Soft delete: DELETE /api/pages/bulk moves pages to the wiki's archive."""
    r = api()._call("DELETE", "/api/pages/bulk",
                    ["-H", "Content-Type: application/json", "-d", json.dumps({"paths": paths})])
    if not r.ok:
        raise FaragopediaError(f"archive failed: {r.status} {r.body[:200]}")


def snapshot_dir() -> Path:
    return Path(os.environ.get("WIKI_SNAPSHOT_DIR") or HERE / "backups")


def require_snapshot(label: str) -> Path:
    """Full-wiki export (GET /api/export/bundle/full) before any live write (safeguard B7).
    Raises — and so stops the caller before it writes anything — unless a readable, non-empty
    bundle was saved. POST /api/export/import restores it. Exports hold every contact page
    verbatim: WIKI_SNAPSHOT_DIR must be outside git (backups/ here is git-ignored)."""
    dest = snapshot_dir() / f"{label}-{dt.datetime.now():%Y-%m-%d-%H%M%S}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = api()._call("GET", "/api/export/bundle/full", ["-o", str(dest)])
    if not r.ok:
        raise FaragopediaError(f"snapshot failed ({r.status}); refusing to write")
    try:
        n = len(zipfile.ZipFile(dest).namelist())
    except zipfile.BadZipFile as e:
        raise FaragopediaError(f"snapshot {dest} is not a valid zip; refusing to write") from e
    if n == 0:
        raise FaragopediaError(f"snapshot {dest} is empty; refusing to write")
    return dest
