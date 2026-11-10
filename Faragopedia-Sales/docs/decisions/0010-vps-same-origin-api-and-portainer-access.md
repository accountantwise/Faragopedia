# ADR-0010: Same-origin API on the VPS, no public backend hostname, Portainer behind Access

> **Status:** Accepted
> **Date:** 2026-11-11
> **Decided by:** Nick + Claude
> **Amends:** [ADR 0007](0007-vps-production-deployment.md) (backend hostnames, Cloudflare Access)

## Context

ADR 0007 gave the VPS backend two public hostnames and removed Cloudflare
Access from the browser-facing one, `faragopedia-backend-vps.ai-wise.uk`,
because a browser `fetch()` could not satisfy a separate Access app. That
hostname therefore had no gate at all. On 2026-11-11 an unauthenticated
`GET /api/pages` on it returned the full page list (46 KB); the wiki holds
contact details from callsheets. The frontend's email login protected the UI,
but anyone could skip it by calling the backend directly.

Separately, `portainer.ai-wise.uk` (Portainer UI and API, i.e. control of the
whole VPS) was public with only Portainer's own login in front of it.

## Decision

### Same-origin API through the frontend's nginx

- `frontend/nginx.conf` proxies `/api/` to `http://backend:8300` on the `edge`
  network (PR #16). The backend is resolved per request via Docker DNS
  (`resolver 127.0.0.11`), so nginx starts even if the backend is down.
  `Host` is passed through, so the `X-API-Key` middleware (which only gates
  `FARAGOPEDIA_API_HOSTNAME`) never applies to UI traffic. 500 MB uploads,
  900 s timeouts, buffering off.
- The Portainer stack's `VITE_API_BASE_URL` changed from
  `https://faragopedia-backend-vps.ai-wise.uk/api` to `/api`.
- The `faragopedia-backend-vps` route was removed from the tunnel (config
  v4 → v5) and its DNS record deleted. It now returns 404.

This is the "single hostname, nginx proxies `/api`" alternative that ADR 0007
deferred.

### Portainer behind Cloudflare Access

New Access app `portainer-vps` on `portainer.ai-wise.uk` with two policies:
Allow for Nick's email only (not the wiki's wider allowlist, since Portainer
is server admin), and Service Auth for a new service token,
`portainer-vps-automation` (expires 2027-11-10), so API redeploys keep
working. API calls now need `CF-Access-Client-Id`/`CF-Access-Client-Secret`
as well as `X-API-Key`.

## Verification (2026-11-11)

- New frontend bundle contains no reference to the old hostname; nginx proxy
  returns the real data inside the container.
- Nick's browser session: 101 backend requests, all via the frontend
  container, none via cloudflared directly.
- Old hostname: 404. Frontend and `/api/*` unauthenticated: 302 to Access
  login. Automation hostname without key: 401.
- `/api/job/*` stays public (existing bypass app for the job-link resolver,
  ADR 0006); `/api/job-links` and all other paths require login.
- Portainer: no login → 302 to Access; Portainer key alone → 302; service
  token + key → 200; service token alone → 401.

Before removing the hostname, every caller was checked: the frontend uses a
single `API_BASE`; `tools/wiki_maintenance`, `tools/callsheet_ingest` and
`farago-callsheet-migration` use `faragopedia-api-vps`; the backend only calls
*out* to Wisecrawler (`wisecrawler-vps.ai-wise.uk`, no callbacks); the
Trigger.dev project Farago-leadSheetUpdater uses `faragopedia-api.ai-wise.uk`
(the NUC).

## Consequences

### Pros

- Wiki data is only reachable behind the email login (UI) or the API key
  (automation hostname). There is one door per kind of traffic.
- No cross-origin requests from the browser, so no CORS or Access-redirect
  failure modes.
- Server administration is no longer exposed to the internet.

### Cons

- Every Portainer API call needs the service token, and it expires yearly.
- The frontend container now sits in the request path for every API call;
  if nginx is down the UI and its API go down together (they effectively did
  already).
- The VPS and NUC frontends now differ in how they reach the backend (nginx
  proxy vs. Vite dev-server proxy), though both are same-origin.

## Alternatives Considered

### Re-add Cloudflare Access to the backend hostname with an identity policy

Would need every browser session to log in to two Access apps and still
depends on cross-origin `fetch()` carrying the Access cookie. Rejected in
favour of removing the hostname.

### Portainer reachable only over an SSH tunnel

Strongest option, but would end API redeploys from anywhere without SSH.
Kept as a possible later step.
