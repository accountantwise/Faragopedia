"""Minimal Faragopedia API client for pushing job pages into a wiki folder.

Shells out to `curl` rather than using requests/urllib, and retries hard. Both are
measured behaviours of this endpoint, not preferences:

- Requests through Cloudflare reset intermittently — roughly a third to a half fail
  during the TLS handshake, independently of method, HTTP version or payload size, and
  succeed on retry within one or two attempts. A bulk push of 91 pages cannot treat a
  reset as a failure.
- requests/urllib3 gets dropped where curl succeeds, which looks like a TLS-fingerprint
  mismatch against Cloudflare's bot rules. curl's fingerprint matches its User-Agent.

Auth is Cloudflare Access service token plus the backend's own API key; see
docs/decisions/0003-external-api-exposure-auth.md in the Faragopedia repo.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ATTEMPTS = 8
# curl exit codes worth retrying: connection reset / recv failure / send failure /
# couldn't connect / operation timeout. A 4xx is a real answer and is never retried.
RETRYABLE_CURL_CODES = {7, 28, 35, 52, 55, 56}


class FaragopediaError(RuntimeError):
    pass


@dataclass
class Response:
    status: int
    body: str

    def json(self):
        return json.loads(self.body) if self.body.strip() else None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class Faragopedia:
    def __init__(self, base_url=None, cf_id=None, cf_secret=None, api_key=None,
                 attempts=DEFAULT_ATTEMPTS):
        self.base = (base_url or os.environ.get("FARAGOPEDIA_API_URL", "")).rstrip("/")
        if not self.base:
            raise FaragopediaError("FARAGOPEDIA_API_URL is not set")
        self.cf_id = cf_id or os.environ.get("FARAGOPEDIA_CF_CLIENT_ID")
        self.cf_secret = cf_secret or os.environ.get("FARAGOPEDIA_CF_CLIENT_SECRET")
        self.api_key = api_key or os.environ.get("FARAGOPEDIA_API_KEY")
        self.attempts = attempts

    def _auth_args(self) -> list[str]:
        args = []
        if self.cf_id and self.cf_secret:
            args += ["-H", f"CF-Access-Client-Id: {self.cf_id}",
                     "-H", f"CF-Access-Client-Secret: {self.cf_secret}"]
        if self.api_key:
            args += ["-H", f"X-Api-Key: {self.api_key}"]
        # Cloudflare's WAF rejects the default Python user agent with error 1010 before
        # the request ever reaches the backend.
        return args + ["-H", "User-Agent: curl/8.5.0"]

    def _call(self, method: str, path: str, extra: list[str] | None = None) -> Response:
        cmd = ["curl", "-sS", "-X", method, *self._auth_args(),
               "-w", "\n%{http_code}", "--max-time", "90",
               *(extra or []), f"{self.base}{path}"]
        last = None
        for attempt in range(1, self.attempts + 1):
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if proc.returncode == 0:
                out = proc.stdout.rsplit("\n", 1)
                if len(out) == 2 and out[1].strip().isdigit():
                    return Response(int(out[1].strip()), out[0])
                last = f"unparseable curl output: {proc.stdout[:200]!r}"
            elif proc.returncode in RETRYABLE_CURL_CODES:
                last = f"curl exit {proc.returncode}: {proc.stderr.strip()[:160]}"
            else:
                raise FaragopediaError(
                    f"curl exit {proc.returncode} (not retryable): {proc.stderr.strip()[:300]}")
        raise FaragopediaError(f"{method} {path} failed after {self.attempts} attempts — {last}")

    # --- endpoints ---------------------------------------------------------------

    def entity_types(self) -> dict:
        r = self._call("GET", "/api/entity-types")
        if not r.ok:
            raise FaragopediaError(f"entity-types -> {r.status}: {r.body[:200]}")
        return r.json() or {}

    def create_folder(self, name, display_name, description="", fields=None,
                      sections=None, singular=None) -> tuple[bool, str]:
        """Returns (created, message). An existing folder is success, not failure: the
        push has to be re-runnable, since `00_Current Jobs` is a sibling of
        `01_Past Shoots` and jobs keep migrating across as they wrap.

        NOTE: fields/sections/singular need the deployed backend to carry the
        POST /folders schema support. Against an older build they are silently ignored
        and the folder is created with a minimal two-field type instead, which cannot
        then be corrected over the API — so `verify_folder_schema` checks afterward.
        """
        payload = {"name": name, "display_name": display_name, "description": description}
        if fields is not None: payload["fields"] = fields
        if sections is not None: payload["sections"] = sections
        if singular: payload["singular"] = singular
        r = self._call("POST", "/api/folders",
                       ["-H", "Content-Type: application/json", "-d", json.dumps(payload)])
        if r.ok:
            return True, (r.json() or {}).get("message", "created")
        detail = (r.json() or {}).get("detail", r.body[:200]) if r.body.strip() else r.body
        if r.status == 400 and "already exists" in str(detail):
            return False, str(detail)
        raise FaragopediaError(f"create_folder({name}) -> {r.status}: {detail}")

    def verify_folder_schema(self, name: str, expected_fields: list[dict]) -> list[str]:
        """Compare the live _type.yaml field names against what we asked for.

        Guards the silent-downgrade case above: a folder created by an older build, or by
        someone clicking New Folder in the UI, carries only `type` and `name`.
        """
        live = self.entity_types().get(name)
        if live is None:
            return [f"folder '{name}' is not a registered entity type"]
        have = {f.get("name") for f in live.get("fields", [])}
        want = {f.get("name") for f in expected_fields}
        return [f"missing field '{f}'" for f in sorted(want - have)]

    def import_pages(self, folder: str, pages: dict[str, str],
                     conflict: str = "overwrite") -> dict:
        """Upload {filename: markdown} into `folder`.

        `overwrite` is the default so re-pushing a job is idempotent. Pass "skip" when
        importing into a folder this pipeline did not create, so existing pages that
        happen to share a filename are not replaced.
        """
        files, tmp = [], Path(os.environ.get("TEMP", "/tmp")) / "faragopedia-upload"
        tmp.mkdir(parents=True, exist_ok=True)
        for fname, content in pages.items():
            p = tmp / fname
            p.write_text(content, encoding="utf-8")
            files += ["-F", f"files=@{p};type=text/markdown"]
        extra = ["-F", f"folder={folder}",
                 "-F", f"conflict_resolutions={json.dumps({f: conflict for f in pages})}",
                 *files]
        r = self._call("POST", "/api/wiki/import", extra)
        if not r.ok:
            detail = (r.json() or {}).get("detail", r.body[:300]) if r.body.strip() else r.body
            raise FaragopediaError(f"import into '{folder}' -> {r.status}: {detail}")
        return r.json() or {}

    def put_job_links(self, links: dict[str, dict]) -> dict:
        """Replace the source-link table behind GET /api/job/{key}.

        Whole-table replacement, because the table is generated from the archive: a
        partial update would let it drift from the source of truth.
        """
        r = self._call("PUT", "/api/job-links",
                       ["-H", "Content-Type: application/json",
                        "-d", json.dumps({"links": links})])
        if not r.ok:
            detail = (r.json() or {}).get("detail", r.body[:300]) if r.body.strip() else r.body
            raise FaragopediaError(f"put_job_links -> {r.status}: {detail}")
        return r.json() or {}

    def get_job_links(self) -> dict:
        r = self._call("GET", "/api/job-links")
        if not r.ok:
            raise FaragopediaError(f"get_job_links -> {r.status}: {r.body[:200]}")
        return r.json() or {}

    def get_page(self, path: str) -> str:
        r = self._call("GET", f"/api/pages/{path}")
        if not r.ok:
            raise FaragopediaError(f"get_page({path}) -> {r.status}: {r.body[:200]}")
        data = r.json() or {}
        return data.get("content", "") if isinstance(data, dict) else str(data)
