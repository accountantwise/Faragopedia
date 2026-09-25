"""The handful of wiki API calls the maintenance scripts share: list, read, write, archive.

Talks to a running Faragopedia over its external API (Cloudflare Access service token +
X-API-Key, see docs/decisions/0003-external-api-exposure-auth.md), so these scripts work
from any machine that can reach the wiki, not only inside the backend container.
"""
from __future__ import annotations

import json
import re
import unicodedata
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
    """'Seán McGirr' -> 'sean-mcgirr'. The wiki's page-slug convention: always use this for
    new pages, never a hand-rolled lower().replace(' ', '-') (they diverge on 'P.M')."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.strip().lower()).strip("-")


def all_pages(refresh: bool = False) -> dict[str, list[str]]:
    """folder -> page paths, cached per process; refresh=True after creating pages."""
    global _pages_cache
    if _pages_cache is None or refresh:
        r = api()._call("GET", "/api/pages")
        if not r.ok:
            raise FaragopediaError(f"GET /api/pages -> {r.status}: {r.body[:200]}")
        _pages_cache = json.loads(r.body)
    return _pages_cache


def get_page(path: str) -> str:
    r = api()._call("GET", f"/api/pages/{path}")
    if not r.ok:
        raise FaragopediaError(f"GET {path} -> {r.status}: {r.body[:200]}")
    return (r.json() or {}).get("content", "")


def write_page(path: str, content: str) -> dict:
    """Create or overwrite. PUT does not validate content shape: a 200 is not a schema check."""
    r = api()._call("PUT", f"/api/pages/{path}",
                    ["-H", "Content-Type: application/json", "-d", json.dumps({"content": content})])
    if not r.ok:
        raise FaragopediaError(f"PUT {path} -> {r.status}: {r.body[:300]}")
    return r.json() or {}


def archive_pages(paths: list[str]) -> None:
    """Soft delete (recoverable from the archive), used for merged-away duplicates."""
    r = api()._call("DELETE", "/api/pages/bulk",
                    ["-H", "Content-Type: application/json", "-d", json.dumps({"paths": paths})])
    if not r.ok:
        raise FaragopediaError(f"archive failed: {r.status} {r.body[:200]}")


def export_backup(dest: Path) -> int:
    """Full-wiki export bundle (GET /api/export/bundle/full). Take one before any live run;
    POST /api/export/import is the matching restore. Returns the number of files in it."""
    import zipfile
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = api()._call("GET", "/api/export/bundle/full", ["-o", str(dest)])
    if not r.ok:
        raise FaragopediaError(f"export failed: {r.status}")
    return len(zipfile.ZipFile(dest).namelist())
