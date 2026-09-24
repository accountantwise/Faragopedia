# 03 — Authentication & User Management

| Field | Value |
| --- | --- |
| Priority | P0 — the single biggest gap; unblocks 04, 05, 07, 08 |
| Effort | L (3–5 sessions) |
| Dependencies | 01 (CORS/headers), 02 (so the auth layer isn't guarding a leaky base) |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/auth` |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — passlib replaced with argon2-cffi (passlib is unmaintained since 2020 and breaks with bcrypt ≥4.1); test-migration strategy switched to `dependency_overrides` (the original plan meant hand-editing 22 test files / ~282 tests); CSRF stance, session-token hashing, migration story, and DB location made explicit. fastapi-users evaluated and rejected (maintenance mode, no OIDC). See `00-review-log.md`. |

## Problem

The app is fully public with no login (verified: zero password/session/user code in the backend; the only gate is the Trigger.dev API-key middleware in `main.py:29-46`). Anyone can read, edit, delete pages, delete sources, run LLM operations, and switch/delete workspaces. Every competitor (Outline, BookStack, Wiki.js, Confluence) treats accounts as table stakes. This is the foundation the rest of the roadmap builds on — roles (04), audit logs & admin (05), page authorship for version history (07), and @mentions (08) all need a `User` identity.

## Design

### Data model

The wiki content stays file-based, but **users, sessions, and (later) permissions/audit need a real datastore**. Introduce **SQLite via SQLModel** (actively maintained, Pydantic-v2-native, fits the FastAPI stack; single-file DB in a mounted volume — no external DB service to run in Portainer).

```
users          (id, email UNIQUE, name, password_hash, role, is_active, created_at, last_login_at, avatar_url)
sessions       (id, user_id, token_hash, created_at, expires_at, last_seen_at, user_agent, ip)
identities     (id, user_id, provider, provider_subject)  # OIDC/OAuth linkage
invitations    (id, email, role, token_hash, invited_by, expires_at, accepted_at)
```

- **DB location:** a new dedicated data dir — `/app/data/faragopedia.db` — with a `data` volume added to `docker-compose.yml`. (Do **not** nest it inside `workspaces/`: users are global, workspaces are content, and backups/exports treat those trees differently.)
- **Session tokens are stored hashed** (`token_hash = sha256(token)`): the cookie holds the raw random token; a DB leak then doesn't yield valid sessions. Same pattern for invitation tokens.
- **Migrations:** start with `SQLModel.metadata.create_all()` plus a tiny `PRAGMA user_version`-based migration runner (a list of numbered SQL/Python steps). Docs 04/05/07/08 each add tables, so a migration story is required from day one — but Alembic is heavier than this app needs; note the choice (and the Alembic upgrade path) in the ADR. Next free ADR number is **0006**.

### Auth mechanism

- **Primary: session cookies** (HttpOnly, Secure, SameSite=Lax) over the server-side session table. Cookies are simplest to secure for a browser SPA and avoid token-in-localStorage XSS exposure. This is why 01 must fix CORS (real origin allowlist, not `*` + credentials). Sessions get an **idle timeout** (`last_seen_at` + e.g. 14 days) and an **absolute lifetime** (e.g. 90 days); the session row is replaced on login (fresh id/token).
- **CSRF stance (explicit):** `SameSite=Lax` blocks cross-site cookie sends on POST/PUT/DELETE, and the strict CORS allowlist stops readable cross-origin responses. Belt-and-braces: a lightweight middleware rejects unsafe-method requests whose `Origin`/`Referer` (when present) doesn't match the allowlist. Document this in the ADR; no token-based CSRF machinery needed for a same-origin SPA.
- **Password hashing: `argon2-cffi` directly** (argon2id; OWASP baseline `memory=19456 KiB, iterations=2, parallelism=1` — or one tier up if login latency allows). **Do not use passlib** — unmaintained since 2020, breaks with bcrypt ≥4.1. `pwdlib` is an acceptable batteries-included alternative if the session prefers it; pick one, note it in the ADR.
- **Local accounts:** email + password, minimum-strength check (length ≥ 12 is enough; no composition rules).
- **Login hardening:** rate-limit `POST /login` (reuse 01's limiter — e.g. `5/minute` per IP), uniform error message for wrong-email vs wrong-password (no account enumeration), uniform response timing (hash even when the user doesn't exist).
- **OIDC (phase 2 within this doc):** generic OIDC discovery + Google via **authlib** (verified actively maintained; still the standard). Config via env: `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`. Use `state` + `nonce` (authlib handles both; verify they're enabled) and PKCE where the provider supports it. On first OIDC login, auto-provision a user (role defaults to `viewer`, admin promotes). This mirrors Outline/BookStack.
- **Considered and rejected: `fastapi-users`** — in maintenance mode, OAuth-social only (no generic OIDC), and its abstractions cost more than hand-rolling ~300 lines of session auth for a self-hosted app. Record in the ADR.
- **MFA (phase 3, optional — can defer to 05):** TOTP via `pyotp`, enforced per-role.

### Bootstrapping the first admin

On first startup with an empty `users` table, the app is in **"setup" mode**: the existing setup wizard (`SetupWizard.tsx`, verified — 4 steps: start/import → identity → schema review → launch) gains a "create admin account" step-0. Until an admin exists, the app shows only that screen. This finally gates the destructive workspace/reconfigure actions currently exposed to anonymous visitors.

### Backend

- New `backend/api/auth_routes.py` under `/api/auth`:
  - `POST /register` (only for first-admin bootstrap, or via invitation token — never open registration by default; gate with `ALLOW_OPEN_REGISTRATION=false`)
  - `POST /login`, `POST /logout`, `GET /me`
  - `POST /invitations` (admin), `POST /invitations/accept`
  - `GET /oidc/login`, `GET /oidc/callback`, `GET /providers` (which login methods are configured — the frontend shows/hides buttons from this)
- New `backend/auth/` package: user CRUD, hashing, session issue/verify, `get_current_user` FastAPI dependency, `require_role(...)` dependency.
- **Guard every existing route** (verified route inventory: 54 in `routes.py`, 7 setup, 3 export, 8 workspace = 72). Add `user: User = Depends(get_current_user)` to all `/api/*` routes except `/api/auth/login`, the auth/OIDC endpoints, `/api/setup/status`, and health. Read routes require any authenticated user; write/LLM routes require `editor`+ (full role logic lands in 04, but wire the dependency now so nothing is anonymous). Prefer a **router-level dependency** (`APIRouter(dependencies=[Depends(get_current_user)])` per router, with the public routes on a separate unauthenticated router) over hand-editing 72 decorators.
- **Service account for Trigger.dev:** keep the API-key path as a `service` user row. The existing `external_api_key_middleware` (Host==`FARAGOPEDIA_API_HOSTNAME` + `x-api-key`, per ADR 0003 including its CF-Connecting-IP incident history) migrates to: valid API key → resolve to the service user → normal dependency chain. External automation and human auth then share one model. Update ADR 0003.

### Frontend

- `AuthContext` (`src/contexts/AuthContext.tsx`): `user`, `login`, `logout`, `loading`. Fetches `GET /api/auth/me` on mount.
- `LoginPage.tsx`: email/password form + "Sign in with Google/OIDC" button (shown only if `GET /api/auth/providers` says so).
- Gate the app: `me` → 401 and setup complete → `LoginPage`; no admin exists → admin-creation wizard step.
- Current user in the sidebar footer (avatar + name + logout), alongside the existing settings entry point.
- All `fetch` calls must send `credentials: 'include'` — centralize this in the API client from roadmap 06; if 06 hasn't shipped, add it per-fetch as an interim step (verified count: 77 fetches across 12 files — tedious but bounded; prefer landing 06 Phase B first).

## Implementation plan (TDD)

1. **DB layer** — SQLModel + SQLite; `User`/`Session`/`Invitation` models; `create_all` + `user_version` migration runner; `data` volume. Tests: create/fetch user, unique-email constraint, migration runner applies steps once.
2. **Password + session core** — argon2 hashing, session issue/verify/expiry (idle + absolute), token-hash storage. Tests: correct/incorrect password, expired session rejected, DB stores hash not token.
3. **`get_current_user` + `require_role` dependencies.** Tests: no cookie → 401, valid cookie → user, insufficient role → 403.
4. **Auth routes** — register(bootstrap)/login/logout/me/invitations/providers. Tests per endpoint incl. "registration closed once admin exists", login rate-limit, uniform login errors.
5. **Guard all existing routes** — router-level dependencies. **Test-suite strategy (important):** the suite is 22 files / ~282 tests with per-file fixtures and **no root conftest** (verified). Do **not** retrofit real logins into every test. Add a root `backend/tests/conftest.py` that installs `app.dependency_overrides[get_current_user] = lambda: TEST_ADMIN` by default, plus a `client_as(role)` fixture for the (new) tests that exercise auth for real. Existing tests then pass untouched; write explicit new tests proving unauthenticated requests 401.
6. **OIDC** — authlib discovery + Google; callback provisions a viewer. Test with a mocked OIDC provider (state/nonce round-trip).
7. **Frontend AuthContext + LoginPage + app gating + sidebar user menu.** `credentials: 'include'` everywhere.
8. **First-admin wizard step** in `SetupWizard.tsx`.
9. **Service-account path** for Trigger.dev; middleware → service-user resolution. Update ADR 0003; new ADR 0006 for the auth architecture (SQLite/SQLModel, argon2, sessions-not-JWT, fastapi-users rejection, CSRF stance).
10. **End-to-end verify** (webapp-testing skill): anonymous → login wall; wrong password → error; login → app; logout → wall; OIDC round trip if configured; Trigger.dev key still ingests.

## Acceptance criteria

- Anonymous request to any `/api/*` write route → 401.
- Fresh deploy with empty user table → forces admin creation before anything else.
- Login sets an HttpOnly Secure SameSite=Lax cookie; `GET /me` returns the user; logout clears it and invalidates the session row.
- Sessions expire (idle and absolute); DB contains token hashes only.
- 6th login attempt in a minute → 429; wrong-email and wrong-password responses are indistinguishable.
- OIDC login provisions a viewer.
- Trigger.dev automation still works via its service-account API key.
- Full backend suite green with the `dependency_overrides` conftest; new auth tests cover the real path.

## Out of scope / follow-ons

- Fine-grained roles & per-page permissions → **04** (this doc only distinguishes authenticated vs not, plus a coarse admin/editor/viewer enum on the user).
- Audit logging & admin user-management UI → **05**.
- MFA can ship here or in 05 — flagged optional.
