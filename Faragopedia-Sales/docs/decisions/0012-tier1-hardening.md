# ADR-0012: Tier 1 hardening (backups, path checks, CORS, headers, pinned deps)

> **Status:** Accepted
> **Date:** 2026-11-18
> **Decided by:** Nick + Claude

## Context

The July 2026 roadmap (`roadmap/01`, `roadmap/02` at the repo root) listed
production and security fixes. By 2026-11-18 only the same-origin `/api` proxy
(ADR 0010) had shipped. A re-check of `main` @ `acc221c` and the VPS found:

1. **No off-site backups.** No cron or timer on the VPS. The only in-app
   snapshots were from April and May, on the same disk as the data.
2. **Path traversal in page import.** `import_pages` used the client-supplied
   `rename` value unchecked, so `{"rename": "../x.md"}` wrote outside the wiki.
   Reachable by anyone past Cloudflare Access, or anyone holding the API key.
3. **Destructive snapshot restore.** `restore_snapshot` emptied the wiki and
   then extracted. Any extract error left no wiki.
4. **Unvalidated `snapshot_id`** went straight into a file path.
5. **CORS `*` with `allow_credentials=True`.** With cookies present, Starlette
   echoes the caller's origin, so any site could read the API using a
   visitor's Access cookie. The frontend sends no credentials, so this was
   never needed.
6. **API schema public.** `/docs` and `/openapi.json` answered without a key
   on the external API hostname, because the key check only covers `/api/*`.
7. The API key was compared with `!=` (not constant-time).
8. No security headers from nginx. Unpinned Python dependencies. No
   Dependabot. Node 20 (end of life 2026-04-30) in the frontend build.
9. No liveness endpoint or container healthcheck, so nothing could alert.

## Decision

- **Import:** a rename target must be a bare `name.md` (no separators, no
  leading dot). Both the folder and the target are checked to resolve inside
  the wiki.
- **Snapshots:** ids must match `[A-Za-z0-9_-]{1,64}` (a bad id returns 400).
  Restore extracts to a sibling staging folder, then swaps. If the swap fails,
  the previous wiki is put back; if that also fails, its copy is kept on disk.
  Archive entries that escape the target, or exceed 2 GiB uncompressed, are
  refused. The same check guards the backup import (`POST /api/export/import`).
- **CORS:** `allow_credentials=False` always. Origins come from
  `CORS_ALLOWED_ORIGINS` (comma list). Unset means `*`, for local dev where the
  frontend calls `:8300` directly. Production sets it to empty, so there's no
  cross-origin access at all.
- **API docs** off unless `ENABLE_API_DOCS=true`.
- **API key** compared with `hmac.compare_digest`.
- **`GET /api/health`** returns `{"status": "ok"}`, ungated even on the
  external hostname (it reveals nothing). The prod compose has a Docker
  healthcheck on it.
- **nginx:** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Permissions-Policy`, `server_tokens off`, all in `security-headers.conf`,
  included at server level and in each location that sets its own headers.
  CSP ships as **Report-Only** first, because Cloudflare may inject scripts on
  the live hostname that local testing can't see. Enforce it once the live
  console shows no reports.
- **Dependencies:** `requirements.txt` pinned to the versions tested on
  Python 3.11 and 3.12. Dependabot (pip, npm, docker, actions) proposes
  upgrades. Node 22 in CI and in `Dockerfile.prod`.
- **Backups:** restic, nightly, from the VPS to off-site storage. Keeps 14
  daily, 8 weekly and 12 monthly snapshots, and reads back 5% of the data on
  each run. Files and runbook: `ops/backup/`, `docs/backup.md`.

## Consequences

### Pros

- The two exploitable bugs from the July audit are closed, with tests
  (`tests/test_security_hardening.py`).
- A failed restore can no longer destroy the wiki.
- Losing the VPS disk or the OVH account no longer means losing the data.
- Upgrades arrive as tested PRs instead of silently at image build time.

### Cons

- Pinned versions need Dependabot PRs merged now and then.
- The CSP hash in `security-headers.conf` must be recomputed if the inline
  theme script in `index.html` changes (`docs/deployment.md`).
- The backup destination costs a little and holds client personal data, so
  it must be in the UK/EU and its credentials kept with the other VPS secrets.

## Alternatives Considered

- **Remove CORS entirely:** breaks local dev, where the frontend calls the
  backend cross-origin when `VITE_API_BASE_URL` is unset.
- **Gate every path on the external hostname:** wider change to the API-key
  middleware and its tests. Turning the docs off solves the leak directly.
- **Enforcing CSP immediately:** risk of a blank page on the live site from
  Cloudflare-injected scripts. Report-Only first is the standard rollout.
- **Relying on in-app snapshots for backup:** they live on the same disk and
  are cleared by a full backup import.
