# 01 — Production-Grade Deployment & Security Hardening

| Field | Value |
| --- | --- |
| Priority | P0 — do this first; it protects everything else |
| Effort | M (2–3 focused sessions) |
| Dependencies | None |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/production-hardening` |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — anchors verified against code; CORS snippet bug fixed; same-origin nginx proxy adopted; Node base bumped. See `00-review-log.md`. |

## Problem

The production deployment at `faragopedia.ai-wise.uk` currently:

1. **Serves the Vite dev server as production.** `frontend/Dockerfile` (verified) is a single-stage `node:20-alpine` image ending in `CMD ["npm", "run", "dev", "--", "--host"]`, with `RUN chmod -R 777 /app`. This is slower, ships source maps + HMR websockets to the public internet, and already caused a real outage: Cloudflare cached a stale `.css` while serving fresh `.tsx` module URLs, leaving the Link View panel covering the whole map (see `docs/status.md` entry 2026-07-04 round 3). Any new-to-codebase Tailwind class can break prod this way until the cache is purged. Note also `node:20` passed EOL on 2026-04-30 — no more security patches.
2. **Has wide-open CORS**: `backend/main.py:21-27` (verified) sets `allow_origins=["*"]` **with** `allow_credentials=True`. Once cookies/sessions exist (roadmap 03), this combination is dangerous; even today it lets any website script the API from a visitor's browser.
3. **Has no rate limiting or spend protection.** Verified LLM/paid-API endpoints, all callable anonymously: `POST /api/chat` (routes.py:223), `POST /api/paste` (195, ingests), `POST /api/sources/{filename}/ingest` (274), `POST /api/sources/bulk-ingest` (287), `POST /api/lint` (500), `POST /api/lint/fix` (509), `POST /api/scrape-urls` (840, WiseCrawler), `POST /api/search` (867, WiseCrawler → Brave). A bot loop could run up a real bill.
4. **Sends no security headers** (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy).
5. **Has no upload limits** (verified): `POST /api/upload` (routes.py:167-193) writes `shutil.copyfileobj` with no size check; same for import endpoints.

## Current state (verified code anchors)

- `frontend/Dockerfile` — single-stage dev image, `npm install` (not `npm ci`), `chmod -R 777 /app`, `CMD npm run dev`.
- `frontend/src/config.ts` — one line: `export const API_BASE = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8300/api``. Baked at **build** time in a static build.
- `frontend/vite.config.ts` — dev server already **proxies `/api` → `http://backend:8300`** (`changeOrigin: true`). This is the pattern to replicate in nginx.
- `docker-compose.yml` — frontend maps `${FRONTEND_PORT:-5173}:5173`, runs as `user: "${PUID:-1000}:${PGID:-1000}"`, passes `VITE_ALLOWED_HOST` + `VITE_API_BASE_URL` at runtime (which a static build will no longer read — see Design A).
- `backend/main.py:29-46` — `external_api_key_middleware` gates only requests whose Host header equals `FARAGOPEDIA_API_HOSTNAME` (the dedicated Trigger.dev hostname; see ADR 0003, which includes the incident report on the earlier CF-Connecting-IP mistake). cloudflared sets Host per tunnel ingress rule, so client spoofing requires being behind the tunnel — keep documenting that assumption in the ADR.

## Design

### A. Build the frontend; serve static + **proxy `/api`** via nginx (same-origin)

The single highest-leverage decision: make nginx proxy `/api` to the backend container, exactly as the Vite dev proxy already does. Frontend and API become **same-origin** in prod, which (a) makes `config.ts` trivially runtime-safe (`'/api'`, no build-time env baking, Portainer env churn can't silently break it), (b) reduces CORS to a dev-only concern, and (c) means the Cloudflare tunnel only needs the one frontend ingress.

Multi-stage `frontend/Dockerfile`:

```dockerfile
FROM node:22-alpine AS build          # node:20 is past EOL (2026-04-30)
WORKDIR /app
COPY package*.json ./
RUN npm ci                             # requires package-lock.json — commit it if missing
COPY . .
RUN npm run build                      # no VITE_API_BASE_URL needed: API_BASE defaults to '/api'

FROM nginxinc/nginx-unprivileged:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

`frontend/src/config.ts` becomes:

```typescript
export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';
```

(`VITE_API_BASE_URL` stays as a dev/override escape hatch; local dev keeps working because Vite's own proxy already maps `/api`.)

`frontend/nginx.conf`:

```nginx
server {
    listen 8080;                      # unprivileged image can't bind 80
    root /usr/share/nginx/html;
    gzip on; gzip_types text/css application/javascript application/json image/svg+xml;
    client_max_body_size 30m;         # first-line upload cap (backend enforces its own)

    location /api/ {
        proxy_pass http://backend:8300/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header CF-Connecting-IP $http_cf_connecting_ip;
        proxy_read_timeout 300s;      # ingest/lint calls are slow
    }
    location = /index.html { add_header Cache-Control "no-cache"; }
    location /assets/ { add_header Cache-Control "public, max-age=31536000, immutable"; }
    location / { try_files $uri /index.html; }   # SPA fallback — required by roadmap 06
}
```

Key decisions:

- **Hashed filenames end the Cloudflare stale-cache class of bugs** — Vite outputs `assets/index-<hash>.js/css`; `index.html` is `no-cache`, hashed assets `immutable`. (Confirmed still the canonical pattern.)
- **Compose gotcha (verified):** the current `user: "${PUID:-1000}:${PGID:-1000}"` line on the frontend service will break stock `nginx:alpine` (needs root for port 80 + cache dirs). Using `nginxinc/nginx-unprivileged` on port 8080 keeps the non-root posture. Update the mapping to `"${FRONTEND_PORT:-5173}:8080"` so the Cloudflare tunnel target does not change.
- **Long-running LLM requests:** ingest/lint can exceed nginx's default 60s `proxy_read_timeout` — set 300s explicitly or chats/ingests will 504 through the proxy (they didn't through the dev server).
- Backend port 8300 no longer needs a public mapping once the proxy is in place; keep it bound for the Trigger.dev tunnel ingress (which targets the backend hostname directly per ADR 0003) — verify the tunnel config before removing anything.

### B. Fix CORS

With same-origin proxying, browser CORS applies only to dev and to the external-API hostname. Still fix the dangerous config. **Note:** the previous draft's snippet had a real bug — `os.getenv("CORS_ORIGINS", "").split(",") or [default]` never falls back, because `"".split(",")` is `[""]` (truthy). Use:

```python
_raw = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS = [o.strip() for o in _raw.split(",") if o.strip()] or ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Set `CORS_ORIGINS=https://faragopedia.ai-wise.uk` in the Portainer stack env (harmless when same-origin; necessary if any cross-origin client remains). Keep localhost defaults for dev.

### C. Rate limiting

Use `slowapi` (in-memory storage is fine for this single-container deploy). Considered and rejected: `fastapi-limiter` — it requires Redis, which violates the no-extra-services ethos here. If slowapi's ergonomics grate (it needs `request` in each endpoint signature), a ~60-line hand-rolled token-bucket middleware keyed by client IP is an acceptable, fully-testable alternative — pick one in the session and note it in the ADR.

- Global default: `200/minute` per IP.
- **Client IP helper:** `get_client_ip(request)` returns `CF-Connecting-IP` **only when the immediate peer is trusted** (the nginx/tunnel container network, or a `TRUSTED_PROXY_IPS` env list); otherwise `request.client.host`. Without this check, anyone who can reach the backend port directly spoofs the header and dodges per-IP limits.
- LLM-spending endpoints (the 8 listed in Problem #3): `10/minute` per IP, plus a crude daily cap (e.g. `50/day` for chat) via a counter file until auth (03) lands.
- Return 429 with a friendly JSON detail the frontend can toast.

### D. Security headers middleware

Simple `@app.middleware("http")` adding: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`. CSP is best added at the nginx layer for the frontend. Start with `Content-Security-Policy-Report-Only: default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'` — `@uiw/react-md-editor` and inline React styles need `'unsafe-inline'` for styles; watch the report-only console for a week before enforcing. HSTS can stay at the Cloudflare layer.

### E. Upload limits

- nginx `client_max_body_size 30m` is the first line (returns 413 before the body reaches Python).
- Backend second line (protects the direct/API-hostname path): reject early on `Content-Length` when present, and stream to disk with a byte counter that aborts at the cap (e.g. 25 MB) — `Content-Length` alone is insufficient for chunked bodies. Apply to `POST /api/upload`, `POST /api/export/import`, and the wiki import route.
- Zip imports: max uncompressed size + max member count during extraction — implemented as `safe_extract` in **roadmap 02** (shared helper; don't duplicate; 02 owns it, this doc just ensures the caps exist by cutover).

## Implementation plan (TDD where testable)

1. **Frontend build serving + proxy** — rewrite `frontend/Dockerfile` (multi-stage, node:22, `npm ci`), add `frontend/nginx.conf` (SPA fallback, `/api` proxy, cache headers, gzip, body cap, proxy timeout). Simplify `config.ts` to the `'/api'` default. Update `docker-compose.yml` (port `:8080` target; drop `VITE_API_BASE_URL`/`VITE_ALLOWED_HOST` from the frontend service or keep as no-ops during transition). Commit `package-lock.json` if absent.
2. **CORS from env** — change `main.py` with the corrected parsing above; add `CORS_ORIGINS` to `docker-compose.yml` + `.env.example` + `docs/deployment.md`.
3. **Security headers middleware** — new `backend/api/security_headers.py`, register in `main.py`; tests assert headers on `GET /`.
4. **Rate limiting** — `slowapi` in `requirements.txt` (pin it — the file currently pins nothing); `get_client_ip()` with trusted-proxy check + unit tests (spoofed header from untrusted peer ignored); decorate the 8 spend endpoints; tests: 11th call in a minute → 429 (isolate limiter storage per test).
5. **Upload/import size caps** — streaming cap in `routes.py` upload + import routes; tests with oversized payloads → 413.
6. **Local verification** — `docker compose up --build`; click through Wiki/Sources/Links/Chat against the nginx bundle; confirm no HMR/websocket errors, confirm an ingest > 60s doesn't 504.
7. **Deploy runbook** — update `docs/deployment.md`: new env vars, nginx proxy note, the one-time Cloudflare cache purge at cutover (hashed assets don't exist in the old cache), Trigger.dev hostname unaffected.

## Acceptance criteria

- Prod serves a built bundle (no `@vite/client` in page source; hashed asset URLs) and `/api/*` works same-origin through nginx.
- `curl -i` on the API shows the four security headers and env-restricted `Access-Control-Allow-Origin`.
- 11 rapid chat calls from one IP → 429; a spoofed `CF-Connecting-IP` from an untrusted peer does not reset the bucket.
- 50 MB upload → 413 without the file landing on disk.
- An ingest that takes 2+ minutes completes through the proxy.
- All existing backend tests still pass (`pytest backend/tests/` — 22 files, ~282 tests).

## Out of scope

- Authentication → **roadmap 03** (rate limiting is the stopgap protecting LLM spend until it ships).
- Path-traversal / zip-safety code fixes beyond size caps → **roadmap 02** (ship alongside).
