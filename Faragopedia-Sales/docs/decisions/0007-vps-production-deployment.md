# ADR-0007: VPS production deployment, separate from the NUC

> **Status:** Accepted
> **Date:** 2026-09-09
> **Decided by:** Nick + Claude

## Context

Faragopedia-Sales ran as a single Portainer stack on an office NUC — the only
deployment. Its frontend container ran the Vite **dev server** in production
(`npm run dev -- --host`), and it was the office's only always-on instance:
a power cut or lost internet at the office took the wiki down entirely.

Nick provisioned an OVHcloud VPS (4 vCPU / 8GB, London) specifically to remove
that single point of failure. The intent, decided partway through setup: the
NUC becomes the dev/test environment; the VPS becomes production. Change flow
stays edit locally → push to GitHub → deploy/verify on the NUC → promote the
same commit to the VPS.

## Decision

### Infrastructure

- VPS hardened per OVH's own guide: SSH key-only auth, moved off port 22,
  UFW default-deny with only the SSH port open, fail2ban on SSH.
- Docker + Portainer CE installed directly on the VPS (`docker run`, not a
  stack — Portainer manages everything else, nothing manages Portainer).
- A single Docker user-defined network, `edge`, joins Portainer, `cloudflared`,
  and every container that needs a public hostname. No container publishes a
  host port; `cloudflared` is the only thing with any inbound path.
- Cloudflare Tunnel (`ovh-vps-portainer`) makes the whole VPS reachable with
  **zero open inbound ports** beyond SSH — not even 80/443 on the public
  firewall. Ingress rules route by hostname to the right container by Docker
  DNS name (`http://backend:8300`, etc.), same pattern as the NUC.

### Frontend: a real production build

The NUC's `frontend/Dockerfile` running the Vite dev server was flagged as a
known risk in earlier planning (unminified/unbundled JS, live HMR websocket,
no cache headers, historically the target of dev-server-specific CVEs) but
left as-is there, since the NUC was originally the only public-facing
instance and changing it carried its own risk with no fallback to catch a
regression.

Added `frontend/Dockerfile.prod` — a multi-stage build (`vite build`,
then `nginx:1.27-alpine` serving the static output) — as a **new, additive**
file. The NUC's `frontend/Dockerfile` and `docker-compose.yml` are untouched;
the VPS uses a separate `docker-compose.prod.yml` that references
`Dockerfile.prod` instead. Two Portainer stacks, two compose files, one repo.

### Backend: two hostnames, not one

The NUC's `.env.example` already documented the intended design:
`FARAGOPEDIA_API_HOSTNAME` names a **dedicated automation-only** hostname —
`external_api_key_middleware` (`main.py`) only checks `X-API-Key` for
requests whose `Host` header matches it exactly. The frontend was never
supposed to call that hostname directly; on the NUC it never does, because
the dev server proxies `/api` same-origin (`vite.config.ts`) and the browser
never leaves that origin.

The VPS frontend and backend are two separate origins by design (no dev-server
proxy in production), so pointing `VITE_API_BASE_URL` at the gated automation
hostname broke ordinary UI use — every real page load's `fetch()` call has no
way to attach `X-API-Key`, so the middleware 401'd the wiki itself. Fixed by
giving the backend **two** hostnames on the same tunnel, both routed to the
same container:

| Hostname | Purpose | Gate |
| --- | --- | --- |
| `faragopedia-backend-vps.ai-wise.uk` | What the frontend's `VITE_API_BASE_URL` points at | none (Cloudflare Access, see below) |
| `faragopedia-api-vps.ai-wise.uk` | External automation (mirrors the NUC's `faragopedia-api.ai-wise.uk`) | `X-API-Key` via `FARAGOPEDIA_API_HOSTNAME` |

This is the NUC's actual intended design, made explicit rather than relying
on same-origin routing to keep the two kinds of traffic apart by accident.

### Cloudflare Access: matched to the NUC, then corrected

The NUC has two Access applications: `faragopedia` (frontend — email
allowlist: `@retirewise.uk` + two named addresses) and `faragopedia-api`
(backend — Cloudflare Access **service token only**, `decision: non_identity`).
Cloned both onto the `-vps` hostnames initially, including the service-token
policy on the backend.

That broke the browser flow a second, different way: a service-token-only
Access policy accepts *only* the `CF-Access-Client-Id`/`Secret` header pair,
which a browser `fetch()` from the wiki UI has no way to supply. Logging into
the frontend's Access app does not authenticate the browser to a *separate*
Access app on a different hostname — they're independent sessions — and even
visiting the backend directly to log in doesn't help, because `fetch()`
follows a same-origin-XHR path that a cross-origin Access login redirect
can't satisfy (surfaces in DevTools as a CORS error on a 302 to Access's
login flow, not as a clean 401/403).

Resolved by removing Cloudflare Access from the backend Access app entirely
for the VPS, relying solely on the app's own `X-API-Key` middleware — which
only ever gates the dedicated `faragopedia-api-vps` hostname the frontend
never calls. The frontend's Access app (email login) is untouched and still
gates the wiki UI itself.

## Consequences

### Pros

- The VPS survives an office power/internet outage; the NUC no longer being
  the sole live instance was the entire motivation for provisioning it.
- The frontend/backend hostname split and the removal of the backend's
  redundant Access gate make the security model **more correct**, not just
  duplicated — the two-layer NUC design was never actually exercised as
  intended (same-origin routing hid the gap where an ordinary browser can't
  present a service token), and this deployment is the first time it was
  tested against real browser traffic.
- `Dockerfile.prod` is purely additive — the NUC's dev-server-based
  deployment is byte-for-byte unchanged, so nothing about today's NUC
  workflow needed to change to ship this.

### Cons

- **Two deploy targets that don't sync automatically.** `vps-prod-deploy` is
  a long-lived branch, not a short-lived feature branch — merging `main`
  into it is a manual step someone has to remember every time `main` moves,
  or the VPS silently drifts behind (this happened once already: `main`
  picked up `job-page-import` — including the `remark-gfm` table-rendering
  fix — while `vps-prod-deploy` only had a small, unrelated bugfix branch
  merged in, so the VPS kept serving stale markdown rendering until the gap
  was caught by eye and `main` was merged in after the fact).
- Backend automation callers now need to know *which* hostname to use
  (`-api-` for `X-API-Key`, `-backend-` for browser/UI traffic) — a config
  mistake here reproduces the exact "frontend can't reach its own backend"
  failure this ADR fixes.
- The backend's `X-API-Key` is now the *only* thing standing between the
  internet and `faragopedia-backend-vps.ai-wise.uk`'s automation-shaped
  routes, since Cloudflare Access no longer sits in front of it. Acceptable
  because that hostname was never meant to be the gated one, but it means
  the VPS's real defense-in-depth is: Cloudflare Access on the frontend +
  `X-API-Key` on the dedicated automation hostname, not two independent
  layers stacked on the same door.

## Alternatives Considered

### Single shared hostname, frontend proxies `/api` via nginx (like the NUC's Vite proxy)

Would have kept one backend hostname and let Cloudflare Access gate it
uniformly, closer to the NUC's actual runtime shape. Rejected for this pass
to keep the two environments' Cloudflare/DNS configuration structurally
identical (two hostnames each) rather than architecturally different created
purely to route around a dev-server proxy pattern; may be worth revisiting
once the VPS is the promoted production target and the NUC's dev-server
config is no longer the reference implementation.

### Keep Cloudflare Access on both backend hostnames, add a machine-user identity policy for browser traffic

Considered before landing on removing Access from the backend outright. Would
preserve the two-layer defense-in-depth on paper, but the actual mechanism —
an identity (email-login) policy alongside the service-token policy on the
same Access app — was tested and does route around the CORS/redirect problem
for a logged-in session. Not chosen because it still requires every browser
session to separately authenticate to *two* Access apps (frontend's and
backend's) to load one page, and the added session-management complexity
wasn't judged worth it over a single `X-API-Key` check on a hostname
real users never hit.
