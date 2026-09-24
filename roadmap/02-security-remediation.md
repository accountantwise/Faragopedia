# 02 — Security Remediation (Path Traversal, Zip Safety, Secrets, Prompt Injection)

| Field | Value |
| --- | --- |
| Priority | P0 — C4/C5 are exploitable **today** on the public deployment |
| Effort | M (1–2 sessions) |
| Dependencies | None (independent of 01, but ship alongside it) |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/security-remediation` |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — every finding re-verified against code. Two findings materially re-graded: C1 (secrets) was largely already mitigated; C2/C3 (zip-slip) is **not exploitable** on Python 3.11 and is re-scoped to zip-bomb/defense-in-depth. C4/C5 confirmed critical with exact anchors. See `00-review-log.md`. |

## Problem

A defensive security review of the FastAPI backend found 15 issues; this doc covers the code-level ones (roadmap 01 covers CORS, headers, rate limiting, upload size). Until authentication (roadmap 03) exists, everything here is reachable by anyone on the internet. **This revision re-verified each finding against the actual code** — two were overstated in the original audit and are re-graded below with evidence, so build sessions don't burn time on non-bugs.

## Findings & fixes

### CRITICAL (verified exploitable)

**C4. Path traversal via import conflict-resolution rename.**
Verified: `wiki_manager.import_pages()` takes `target_name = resolution["rename"]` (wiki_manager.py:1407) and uses it directly in `os.path.join(folder_path, target_name)` (line 1411) — **no sanitization is applied**. A caller can pass `{"rename": "../../_meta/index.md"}` (or escape the wiki dir entirely) and write arbitrary `.md`-or-not content at an attacker-chosen path.
- Fix: sanitize `target_name` with the existing helpers — `secure_filename()` (routes.py:102-109) or reject any value containing `/`, `\`, or `..`; then assert the resolved path stays under the entity folder (realpath prefix check, mirroring `safe_wiki_filename()` at routes.py:111-165, which already implements the correct pattern including the Windows-casing branch).

**C5. Snapshot ID not validated.**
Verified: `POST /snapshots/{snapshot_id}/restore` (routes.py:527) and `DELETE /snapshots/{snapshot_id}` (routes.py:538) pass `snapshot_id` straight to the manager, which interpolates it into `os.path.join(self.snapshots_dir, f"{snapshot_id}.zip")` (wiki_manager.py:921). `../../somezip` reads/deletes zips outside the snapshots dir; combined with restore's behavior (see H2 below) an attacker-placed zip could replace wiki content.
- Fix: validate `^[A-Za-z0-9_-]+$` at the route layer before it reaches the manager; 422 otherwise. Same guard on any other route that takes a snapshot id.

### HIGH

**H1. Secrets hygiene — mostly mitigated, verify & rotate (was "C1", downgraded).**
The original audit claimed `.env` is baked into the image with no `.dockerignore`. **Verified reality:** `backend/.dockerignore` exists and excludes `.env` (line 3), `.gitignore` excludes `.env` (line 20), and `git ls-files`/history show `.env` was **never committed**. Residual risk, in order:
1. **Image layers built before `.dockerignore` existed** may contain the key material. Run `docker history`/dive on the deployed image; if in doubt, **rotate the OpenRouter, WiseCrawler, Cloudflare and `FARAGOPEDIA_API_KEY` secrets anyway** — rotation is cheap, forensics isn't.
2. `frontend/.dockerignore` doesn't exclude `.env*` — add it (defense-in-depth; no secrets belong in the frontend build context, and any `VITE_*` value is public by construction anyway).
3. Keys should only arrive via Portainer stack env vars (already the case); the on-disk `.env` is for local dev only. Document this in `docs/deployment.md`.

**H2. Snapshot restore deletes the wiki before extracting.**
Verified (wiki_manager.py:920-940): `restore_snapshot()` runs `zf.testzip()`, then **deletes the entire wiki directory contents**, then `zf.extractall(self.wiki_dir)`. `testzip()` only catches CRC corruption — a structurally valid but wrong/empty zip still results in the old wiki being destroyed first. Not attacker-driven by itself, but it converts C5 (unvalidated id) or a bad import into data loss.
- Fix: extract to a temp staging dir first (validated by `safe_extract`, below), then swap directories (rename old → `.bak`, move staging in, delete `.bak` on success).

**H3. Unauthenticated LLM spend.** `/chat`, `/paste`, `/lint`, `/lint/fix`, `/sources/{f}/ingest`, `/sources/bulk-ingest`, `/scrape-urls`, `/search` all spend tokens/paid API calls and are open (routes verified in roadmap 01, Problem #3). Roadmap 01's rate limiting is the stopgap; roadmap 03's auth is the real fix. **Cross-reference both** — do not consider this closed until auth ships. Note `/search` and `/scrape-urls` go through the WiseCrawler service (Brave-backed internally), so spend lands on that stack's bill.

### MEDIUM (re-graded down from CRITICAL: zip-slip → zip safety)

**M1. Zip extraction hardening (was "C2/C3 zip-slip", corrected).**
The audit claimed `zf.extractall()` allows `../../` member escape. **This is wrong for Python's `zipfile`:** CPython's `extract`/`extractall` sanitize member names — leading slashes and drive letters are stripped and `..` components are removed — since well before the 3.11 this backend runs (`python:3.11-slim`, backend/Dockerfile:1). Classic zip-slip is a `tarfile` problem, not a `zipfile` one. **What remains real** at the two verified sites — `export_routes.py:136` (`zf.extractall(staging)`) and `wiki_manager.py:937` (`restore_snapshot`):
- **Zip bombs**: no limit on uncompressed size or member count → disk/memory exhaustion.
- **Defense-in-depth**: an explicit path check is cheap insurance against interpreter-behavior changes and future refactors to `tarfile`/`zipfile.Path` (which does NOT sanitize).

Fix — shared helper in `backend/agent/archive_safety.py`, called from both sites:

```python
import os, zipfile

def safe_extract(zf: zipfile.ZipFile, dest: str,
                 max_total: int = 500 * 1024 * 1024, max_members: int = 5000) -> None:
    dest_abs = os.path.realpath(dest)
    infos = zf.infolist()
    if len(infos) > max_members:
        raise ValueError("Archive has too many members")
    total = 0
    for info in infos:
        total += info.file_size
        if total > max_total:
            raise ValueError("Archive too large when extracted")
        target = os.path.realpath(os.path.join(dest, info.filename))
        if os.path.commonpath([dest_abs, target]) != dest_abs:
            raise ValueError(f"Unsafe path in archive: {info.filename}")
    zf.extractall(dest)
```

(`commonpath` is more robust than the previous draft's `startswith(dest + os.sep)` — it can't be fooled by sibling dirs sharing a prefix.)

### LOW

**L13. Error message leakage.** Verified: dozens of `detail=f"...{str(e)}"` handlers in routes.py (e.g. lines 173, 185, 231, 246, 257) expose filesystem paths and internals. Add a small wrapper: log the real exception server-side, return a generic 500 detail. Keep 4xx validation messages (they're intentional) — the wrapper must **re-raise `HTTPException` untouched** and only genericize unexpected exceptions.

**L14. Prompt injection.** Source docs and page content flow into ingest/lint/query prompts. A malicious source can try "ignore previous instructions." Full defense is hard, but reduce blast radius:
- Wrap all user/document content in explicit delimiters (XML tags) in the `wiki_manager` prompt templates, with a system-prompt instruction that content inside the tags is data, never instructions.
- Ingestion already uses `.with_structured_output()` (verified at wiki_manager.py:661, 858, 961) so the output shape is constrained — good; note this defense-in-depth in the ADR.
- This matters more once auth exists and multiple users ingest each other's uploads.

## Implementation plan (TDD)

1. **C4 rename sanitization** — test `{"rename": "../evil.md"}` and `{"rename": "..\\evil.md"}` → rejected; normal rename works. *(Do this first — it's the live remote-write hole.)*
2. **C5 snapshot-ID regex guard** at route layer — test `../../etc/passwd` and `foo/bar` ids → 422; normal id works.
3. **`archive_safety.safe_extract()`** with unit tests: benign zip extracts; `../` member → `ValueError`; oversized → `ValueError`; too many members → `ValueError`. Wire into `export_routes.py:136` + `wiki_manager.restore_snapshot`.
4. **H2 staged restore** — restore extracts to staging then swaps; test: restore of a corrupt-after-testzip zip leaves the original wiki intact.
5. **Secrets hygiene (H1)** — add `.env*` to `frontend/.dockerignore`; `docker history` check documented; key-rotation note in `docs/deployment.md`. **(no test — ops; coordinate rotation with the user)**
6. **Error-message sanitization wrapper** — test a forced internal error returns generic detail (real error in logs) and a 422/404 `HTTPException` passes through unchanged.
7. **Prompt-delimiter hardening** in `wiki_manager` templates — string-assert the templates wrap content in the delimiter; ADR entry (next free number is **0006** — 0001–0005 exist).
8. Full suite green (`pytest backend/tests/`).

## Acceptance criteria

- Import with `rename: "../../_meta/index.md"` → rejected, nothing written outside the entity folder.
- Snapshot restore/delete with id `../../x` → 422.
- Malicious zip (member `../../x`, oversize, or 10k members) → 400/422, nothing written outside dest.
- A failed restore leaves the existing wiki untouched.
- `docker history` on a fresh backend image shows no `.env` layer; rotation performed or explicitly waived by the user.
- Forced 500s return generic detail; existing tests pass; new tests cover each fix.

## Out of scope

- Rate limiting, CORS, security headers, upload caps → **roadmap 01**.
- Authentication → **roadmap 03**.
