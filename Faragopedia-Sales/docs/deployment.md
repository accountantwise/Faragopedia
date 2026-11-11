# Deployment & Setup Guide

This guide covers how to deploy Faragopedia-Sales using Docker, Docker Compose, and Portainer Stacks.

> **Two live deployments exist.** The office NUC (dev/test — deploys from
> `main`, dev-server frontend) and an OVHcloud VPS (production — deploys from
> `vps-prod-deploy`, production nginx build, Cloudflare Tunnel, no open
> ports). See [ADR 0007](decisions/0007-vps-production-deployment.md) for why
> they differ and the [VPS production stack](#vps-production-stack) section
> below for its specifics. **`vps-prod-deploy` does not track `main`
> automatically** — after merging anything to `main`, merge `main` into
> `vps-prod-deploy` and redeploy the VPS stack, or it silently serves stale
> code (this has already happened once — see ADR 0007's Cons).

## Environment Variables

The following variables can be configured in your `.env` file or passed as environment variables in Portainer.

### AI Configuration
| Variable | Description | Default |
| :--- | :--- | :--- |
| `AI_PROVIDER` | The default LLM provider (`openai`, `anthropic`, `google`, `openrouter`) — used for query and any operation without its own override | `openai` |
| `AI_MODEL` | The default model (e.g., `gpt-4o-mini`, `claude-3-5-sonnet-20240620`) | `gpt-4o-mini` |
| `INGEST_AI_PROVIDER` / `INGEST_AI_MODEL` | Optional override used only for source ingestion. Omit to fall back to `AI_PROVIDER`/`AI_MODEL`. | - |
| `LINT_AI_PROVIDER` / `LINT_AI_MODEL` | Optional override used for both wiki linting and applying lint fixes. Omit to fall back to `AI_PROVIDER`/`AI_MODEL`. | - |
| `OPENAI_API_KEY` | Your OpenAI API key | - |
| `ANTHROPIC_API_KEY` | Your Anthropic API key | - |
| `GOOGLE_API_KEY` | Your Google AI (Gemini) API key | - |
| `OPENROUTER_API_KEY` | Your OpenRouter API key | - |

### Deployment & Permissions
These variables are critical for ensuring files created by the AI are accessible on your host machine.

| Variable | Description | Recommended |
| :--- | :--- | :--- |
| `DATA_DIR` | Absolute path on your host to store the wiki and sources. | `/home/user/docker/faragopedia` |
| `PUID` | The User ID of your host user (run `id -u` to find it). | `1000` |
| `PGID` | The Group ID of your host user (run `id -g` to find it). | `1000` |
| `BACKEND_PORT` | The host port for the FastAPI backend. | `8300` |
| `FRONTEND_PORT` | The host port for the React frontend. | `5173` |

### Web & Networking
| Variable | Description | Default |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | The URL the frontend uses to contact the backend. | `http://localhost:8300` |
| `VITE_ALLOWED_HOST` | Allowed hostname for the frontend. | `localhost` |
| `WISECRAWLER_BASE_URL`| (Optional) URL for a WiseCrawler instance for web scraping. | - |
| `WISECRAWLER_API_KEY` | (Optional) API key for WiseCrawler. | - |

---

## Deployment Options

### 1. Local Docker Compose
Best for local development or individual use.

1. Clone the repo: `git clone https://github.com/accountantwise/Faragopedia-Sales.git`
2. Create your `.env` file from the example.
3. Run `docker-compose up -d`.
4. Access at `http://localhost:5173`.

### 2. Portainer Stacks (Recommended for Self-Hosting)
Best for persistent deployments on a server.

1. In Portainer, create a new **Stack**.
2. Select **Repository** and enter the Git URL.
3. In the **Environment Variables** section, add the variables listed above.
   - **Crucial**: Set `DATA_DIR` to a permanent path on your server (e.g., `/home/colacho/docker/faragopedia`).
   - Set `PUID` and `PGID` so you can manage the markdown files directly via SFTP/SMB.
4. Deploy the stack.

### ⚠️ Frontend Asset Caching Behind Cloudflare

The frontend container runs the Vite **dev server**, whose module URLs never
change between deploys (`/src/index.css`, `/src/components/*.tsx`). When the
site is served through a Cloudflare tunnel, Cloudflare caches `.css` by file
extension but not `.tsx` — so after a redeploy, browsers can receive **new
component JavaScript with a stale pre-deploy stylesheet**. Any Tailwind class
that is new to the codebase in that deploy will silently be missing.

This caused a real outage on 2026-07-04: the Link View rendered as a blank
page because the reading panel's (then class-based) hide transform wasn't in
the cached CSS, leaving an invisible full-width sheet over the map (see
`docs/status.md`, Link View round 3).

**After every redeploy that touches frontend styling:** purge the Cloudflare
cache for the zone (or enable Development Mode while testing). Note
(2026-09-10): the `CLOUDFLARE_AIWISE_API_TOKEN` in the internal `.env` is
scoped to `zone:read`/`zone_settings:read`/`dns_records:edit`/`dns_records:read`
only — it cannot call `purge_cache` (confirmed: 401). Either add Cache Purge
permission to that token, or purge manually via the Cloudflare dashboard
(`ai-wise.uk` zone → Caching → Configuration → Purge Cache).

**Durable fixes (not yet implemented):** add a Cloudflare cache-bypass rule
for the frontend hostname, or serve a production `vite build` (hashed asset
filenames) instead of the dev server in the container.

---

## VPS Production Stack

The VPS (OVHcloud, London, 4 vCPU / 8GB) hosts the production instance. Full
rationale in [ADR 0007](decisions/0007-vps-production-deployment.md) — this
section is the "how to touch it" reference.

### Topology

- **Branch:** `vps-prod-deploy` (long-lived, not a feature branch). Portainer
  stack `faragopedia-vps` (endpoint `local`) deploys from
  `Faragopedia-Sales/docker-compose.prod.yml` on this branch.
- **Frontend build:** `frontend/Dockerfile.prod` — multi-stage, `vite build`
  then served as static files by nginx. Separate from the NUC's
  `frontend/Dockerfile` (Vite dev server) — do not conflate the two.
- **Networking:** every container joins the Docker network `edge`, alongside
  `portainer` and `cloudflared`. Nothing publishes a host port. Cloudflare
  Tunnel `ovh-vps-portainer` is the only inbound path, routing by hostname to
  a container's Docker DNS name (e.g. `http://backend:8300`).
- **Public hostnames** (all on the `ai-wise.uk` zone, a **different**
  Cloudflare account than the one this repo's other integrations use —
  ask for the scoped API token rather than assuming account-wide access):

  | Hostname | Routes to | Gate |
  | --- | --- | --- |
  | `portainer.ai-wise.uk` | Portainer UI and API | Cloudflare Access: Nick's email, or the `portainer-vps-automation` service token (ADR 0010) |
  | `faragopedia-vps.ai-wise.uk` | frontend container (nginx; also proxies `/api/` to `backend:8300`) | Cloudflare Access (email allowlist); `/api/job/*` bypassed for the job-link resolver |
  | `faragopedia-api-vps.ai-wise.uk` | backend container | `X-API-Key` via `FARAGOPEDIA_API_HOSTNAME` — external automation only |
  | `wisecrawler-vps.ai-wise.uk` | Wisecrawler API (separate stack) | its own API key |

  The backend has **no browser-facing hostname**. `faragopedia-backend-vps`
  was removed on 2026-11-11 (ADR 0010): it was ungated and served wiki data
  to anyone. The stack's `VITE_API_BASE_URL` is `/api`, so the browser calls
  `/api` on the frontend hostname and nginx proxies it inside the `edge`
  network. **Do not point `VITE_API_BASE_URL` at the `-api-` hostname** (every
  browser request would 401) and do not re-add a public backend hostname.

### Redeploying after a `main` merge

```bash
git checkout vps-prod-deploy
git merge origin/main
git push origin vps-prod-deploy
```

Then trigger a rebuild via Portainer's API (no UI webhook is configured).
Portainer sits behind Cloudflare Access, so every API call needs the service
token headers as well as the Portainer key:

```bash
curl -X PUT "https://portainer.ai-wise.uk/api/stacks/1/git/redeploy?endpointId=3" \
  -H "X-API-Key: $PORTAINER_API_TOKEN" \
  -H "CF-Access-Client-Id: $PORTAINER_VPS_CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $PORTAINER_VPS_CF_ACCESS_CLIENT_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"repositoryReferenceName":"refs/heads/vps-prod-deploy","repositoryAuthentication":false,"pullImage":true}'
```

- **Use `"pullImage": true`.** With `false`, Portainer rebuilds the image but
  can leave the old container running (seen 2026-11-11: new frontend image
  built, container not recreated). `true` forces the recreate.
- **To change an env var**, add `"env": [...]` with **all 15** stack variables
  (read them first with `GET /api/stacks/1`). An empty or partial `env` list
  replaces the stack's variables wholesale (2026-09-10 incident). Omitting
  `env` keeps them as they are.
- The service token (`portainer-vps-automation`) expires **2027-11-10**; renew
  it in Cloudflare Zero Trust before then. Credentials live with the other
  VPS secrets, not in this repo. If the `.env` you load them from has CRLF
  line endings, strip `\r` or the headers are rejected.

Confirm the rebuild actually happened — `docker ps` on the VPS should show
both `faragopedia-vps-*` containers with a fresh `CREATED` time, and the
response's `GitConfig.ConfigHash` should match the branch's latest commit.

### Data

Bind-mounted from the VPS host at `~/faragopedia-data/` (the `DATA_DIR` env
var), under a **workspace-scoped** path —
`~/faragopedia-data/workspaces/<workspace-id>/{wiki,sources,archive,snapshots,schema}/`
— not the flat top-level layout the NUC's `.env.example` describes. This
because the VPS instance went through the multi-workspace `create_workspace`
path (via "Import from backup" on first setup) rather than the legacy
single-workspace migration the NUC's checked-in `.env.example` was written
against. Persists across `docker compose` rebuilds since it's a bind mount,
not a named volume.

---

## Permissions Troubleshooting

If you see "Permission Denied" errors in the logs:
1. Ensure the directory you pointed `DATA_DIR` to exists on the host.
2. Ensure that directory is owned by the user matching your `PUID`/`PGID`.
   ```bash
   sudo chown -R 1000:1000 /your/data/path
   ```
