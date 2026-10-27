# Project Status

> This is the living status document for Faragopedia-Sales.
> AI agents should read this at the start of every session and update it at the
> end of any session where meaningful work was done.

---

## Current Phase: 🟡 MVP Development / Prototype Functional — VPS production deployment live

**Last updated:** 2026-09-25

---

## Recent Activity

| Date       | Agent/Person | Summary                                       |
| ---------- | ------------ | --------------------------------------------- |
| 2026-09-25 | Nick + Claude | **Brought the production-wiki data-quality work into this repo as `tools/wiki_maintenance/` + three Claude Code skills (ADR 0008).** On 2026-09-24/25 the live wiki's company pages were rebuilt onto the entity-type schema (305 pages), duplicates merged after Nick's sign-off, 18 missing company pages and 9 contacts created, 236 raw-name contact `company:` links repaired, Vendor statuses cleared, and `notes` cleaned everywhere except `HUMAN:` flags — all from scripts in the client-projects repo, over the external API. Those scripts (made data-free: plans with contact details stay in ignored `plans/`), the rules Nick set, and the pitfalls that broke data once (non-idempotent Meeting History, a `/`-splitting resolver, orphaned YAML from an old notes cleanup, unfiltered Haiku research) now live here, with 9 offline tests added to CI. The backend does not enforce these rules yet — porting them into `backend/agent/` is the follow-up. **Next session: start from [`docs/superpowers/handoffs/2026-09-25-backend-data-rules.md`](superpowers/handoffs/2026-09-25-backend-data-rules.md).** |
| 2026-09-24 | Nick + Claude | **Fixed the populated-wiki empty-state view — it was missing the product intro, live stats, and getting-started tips the redesign was supposed to add.** The wiki empty-state redesign (commit `546fae6`, merged 2026-09-24) implemented two variants per the original design — zero-pages and populated-wiki — but only the zero-pages variant got the full treatment (product intro, live stats, getting-started tips); the populated-wiki variant (what every real wiki with content actually renders) was left as a bare "Select a page…" one-liner with a flat page count. Brought the intro copy and tips to the populated variant, and replaced the flat count with a per-section stats table (pages + unread count per section, clickable to jump into that section). Verified against live production data via SSH-tunneled backend + local `vite preview` + Playwright screenshot (1534 pages, 8 sections, 17 unread rendering correctly) before merging/deploying. |
| 2026-09-09 | Nick + Claude | **`job-page-import` (PR #4) and `fix/import-workspace-init` (PR #5) merged to `main`; `vps-prod-deploy` re-synced.** PR #4 sanity-checked independently before merge: reran the backend suite on both branches from a clean checkout with the same Python 3.14 environment (4 failed/316 passed on the branch vs. 12 failed/265 passed on `main` — matched the PR's own claimed numbers exactly, same 4 pre-existing unrelated failures on both), and a frontend `npm run build` came back clean. Reviewed the four functional diffs by hand (`job_links.py`'s closed-lookup redirect endpoint, `schema_builder.py`'s description-rendering fix, `routes.py`'s backward-compatible folder-schema params, `wiki_manager.py`'s `import_pages` write-lock + audit log) — no concerns, merged both. **Then discovered `vps-prod-deploy` had only picked up PR #5** (merged directly into it) **and never PR #4** — the VPS kept serving the pre-fix frontend bundle, visible as raw pipe-delimited markdown tables instead of rendered grids (the `remark-gfm` fix from PR #4 hadn't reached it). Merged `origin/main` into `vps-prod-deploy`, pushed, redeployed the Portainer stack — confirmed both containers rebuilt and the new bundle contains `remark-gfm`. **Lesson written into ADR 0007, `docs/deployment.md`, and `AGENTS.md`: `vps-prod-deploy` does not track `main` automatically — this has to be a merge-and-redeploy step every time, not an assumption.** |
| 2026-09-09 | Nick + Claude | **VPS production deployment stood up end-to-end** (OVHcloud, London, 4 vCPU/8GB) — see [ADR 0007](decisions/0007-vps-production-deployment.md) for full detail. VPS hardened (SSH key-only, moved off port 22, UFW default-deny, fail2ban), Docker + Portainer installed directly, everything else run as Portainer stacks. New `frontend/Dockerfile.prod` (multi-stage `vite build` → nginx) added alongside — not replacing — the NUC's dev-server `Dockerfile`; new `docker-compose.prod.yml` targets a Docker network (`edge`) shared with a Cloudflare Tunnel container, so the whole stack (Portainer UI included) is reachable with **zero open inbound ports** beyond SSH. Hit three real bugs getting there, in order: (1) the tunnel's `cloudflared` container needed the compose services' Docker DNS names in its ingress config, straightforward once identified; (2) `VITE_API_BASE_URL` pointed at `FARAGOPEDIA_API_HOSTNAME` — the hostname `main.py`'s middleware gates behind `X-API-Key` for *external automation only* — so the frontend's own browser calls 401'd on every page load; fixed by giving the backend a second, ungated hostname for the frontend to call, matching what `.env.example`'s existing comment already said the design should be; (3) cloned the NUC's Cloudflare Access service-token policy onto the new gated hostname, which then blocked the (already-fixed) frontend traffic a second way — a service-token-only Access app can't be satisfied by an ordinary browser `fetch()`, and logging into a *different* Access app (the frontend's) doesn't authenticate that session — removed Access from the backend hostname entirely, relying on the existing `X-API-Key` middleware alone. Along the way, found and fixed a real, deployment-independent bug: `POST /api/export/import` assumed an active workspace already existed, so on a genuinely fresh instance (no `workspaces/registry.json` yet) every data-directory accessor returned `""`, and the first `shutil` write against the resulting bogus relative path failed with a misleading `PermissionError: [Errno 13] Permission denied: 'snapshots'` that had nothing to do with actual filesystem permissions — see PR #5 above. Real wiki data (91 pages, imported from a NUC-exported `.zip` via the newly-fixed import flow) confirmed present and rendering correctly on the VPS afterward. |
| 2026-09-10 | Claude | **Added CI, merged `link-view` to `main`, fixed 4 flaky backend tests, redeployed to production.** No GitHub Actions workflow existed; added `.github/workflows/ci.yml` (pytest backend + `npm run build` frontend). Merging `link-view` → `main` (PR #7) required manual conflict resolution in `AGENTS.md` (both branches added a decision-table row) — a first merge attempt was run against a stale local `origin/main` and git's 3-way auto-merge silently dropped `WikiManager.get_link_graph()` and its `/pages/graph` route with no conflict markers; caught by diffing function/route names between `link-view` and the merge result before pushing, redone correctly. CI then surfaced 4 real backend-test failures (`test_update_page`, 3x `test_setup_routes.py`), confirmed pre-existing on `main` and unrelated to the merge (root-caused and fixed same day, see next entry). Merged `main` → `vps-prod-deploy` (no conflicts, only touches its own prod docker-compose/Dockerfile/nginx). Redeployed via the Portainer API (stack `faragopedia-vps`, id 1) — hit a self-inflicted issue: the first redeploy call passed `env:[]`, which Portainer applied literally and wiped the stack's persisted env vars (including `DATA_DIR`), causing the backend to fall back to a relative bind-mount path and briefly serve an empty workspace (`setup_required: true`) instead of the real data at `/home/ubuntu/faragopedia-data` — no data was lost or touched, just not mounted; fixed by redeploying again with all 13 env vars passed explicitly. Live site confirmed working manually by Nick post-deploy. **New known issue and required practice logged below.** |
| 2026-09-10 | Claude | **Root-caused and fixed 4 non-deterministic backend test failures** (PR #8, `fix/backend-test-isolation` → `main`, then merged into `vps-prod-deploy`). Both were test-only bugs, no production code changed. (1) `test_setup_routes.py` patched `sr.SCHEMA_DIR`/`sr.WIKI_DIR` — attributes nothing in `setup_routes.py` reads. The routes actually resolve paths via `agent.workspace_manager`'s real, disk-backed active-workspace singleton (`_active_dirs`, populated from `workspaces/registry.json` at `main.py` import time), so the tests were silently operating on a real `backend/workspaces/default/` directory instead of an isolated tempdir — results depended on whatever state prior runs left there. Fixed by patching `workspace_manager.WORKSPACES_BASE`/`REGISTRY_PATH` and writing a registry for a throwaway workspace before `main` is imported, matching the pattern `test_workspace_rename.py` already used correctly. (2) `test_api.py::test_update_page`'s shared `mock_wm` fixture never mocked `auto_rename_if_untitled` as an `AsyncMock`, so the route's `await wm.auto_rename_if_untitled(...)` raised `TypeError` on the bare `MagicMock`, caught by the route's broad exception handler and returned as a 500. Verified with 3 consecutive full-suite runs post-fix: 325 passed, 0 failed each time (previously non-deterministic — different subset failed depending on run/order). |
| 2026-07-08 | Claude | **10-point growth roadmap critically reviewed and approved for build** (saved in `roadmap/` at the repo root, one level up from this folder — production hardening, security remediation, auth, permissions/sharing, admin dashboard, routing/frontend refactor, version history, collaboration, semantic search/RAG, UX polish). Every code anchor was re-verified against the current codebase and every recommended library checked for 2026 maintenance status via parallel fact-check/research agents; all 10 docs were upgraded in place (none rejected, none survived unchanged). Highlights of what the review caught: the zip-slip finding in the security doc was wrong (Python's `zipfile.extractall` already sanitizes `..` — re-scoped to zip-bomb caps); a worse bug was found instead (`restore_snapshot()` deletes the wiki *before* extracting the replacement, verified `wiki_manager.py` `restore_snapshot()`); the backend's "active workspace" is server-global module state (`workspace_manager.py`) which blocks any multi-user permissions work until fixed; `passlib` (the originally recommended password-hashing lib) is unmaintained and breaks with modern bcrypt, replaced with `argon2-cffi`; `node:20-alpine` is past its EOL, bumped to 22; and the "chat stuffs the whole wiki into the prompt" framing was corrected (chat is a 2-pass relevance flow — lint is the actual whole-wiki path). Full verdict table and evidence in `roadmap/00-review-log.md`. No code changed — this is planning only; each doc is meant to be handed to a build session one at a time, sequenced per `roadmap/00-overview.md`. Next ADR when implementation starts: **0006**. |
| 2026-07-04 | Claude | **Link View round 4: docked reading panel + content search bar** (branch: `link-view`). The reading panel no longer overlays the map — it's a docked flex sibling (inline-style width animation, cache-safe per round 3) and the map reflows to fit between sidebar and panel; curves remeasure on reflow via ResizeObserver. Fixed a latent bug the new geometric checks caught: the ResizeObserver effect ran during the initial loading spinner when the wrapper ref was null, so it never observed anything — curves were never remeasured on any resize since round 1 (now keyed on `loading`). New search bar (top-right, per the original mockups): filters the map to pages whose CONTENT matches, using the existing client-side `GET /search/index` (title + path + tags + frontmatter values + 500-char content preview; falls back to title/path if the index is unavailable). Edges/hover/focus operate on the filtered subgraph; stats bar shows "N of M"; focused page filtered out → panel closes; panel-wikilink to a hidden page clears the query; Esc in the box clears the query, Esc elsewhere resets the view. 35/35 checks light+dark incl. panel-open hit-testing and curve-bounds geometry. |
| 2026-07-04 | Claude | **Link View round 3: fixed blank page on production (stale-CSS ghost panel)** (branch: `link-view`). Prod (`faragopedia.ai-wise.uk`) showed a totally blank Link View despite the stats bar reporting 439 nodes. Root cause: the reading panel's hide mechanism used two Tailwind classes new to the codebase (`translate-x-full`, `sm:w-[28rem]` — nothing else uses them; App.tsx only uses `-translate-x-full`). Prod serves the Vite dev server through Cloudflare, which caches `.css` by default but not `.tsx` module URLs — so the browser combined fresh component JS with a stale pre-deploy stylesheet missing both classes, leaving the closed panel as an untranslated, full-width `bg-gray-900` sheet permanently covering the map (the ✕ and header hairline visible in the user's screenshot were the empty panel's own chrome). Could not be reproduced by data shape: a 439-node/122-edge synthetic graph with unicode/XSS/long titles rendered fine locally. Fix: panel show/hide transform + visibility + transition moved to inline styles (immune to stylesheet staleness), width switched to `max-w-md` (28rem, in the app's CSS since forever). Verification now includes geometric checks (closed panel truly off-screen, chips hit-testable at rest) — the earlier suite only asserted `aria-hidden`, which is how this slipped through. 45/45 checks passing light+dark. **Note for deploys:** any new-to-codebase Tailwind class can break prod this way until the Cloudflare cache is purged; consider a cache rule for `/src/*` or serving a built bundle with hashed filenames in prod. |
| 2026-07-04 | Claude | **Link View round 2: hover-priority highlighting + slide-in reading panel** (branch: `link-view`). User-reported bug: hovering a linked page appeared dead — root cause was focus taking display priority over hover (`activeId = focusId ?? hoverId`), so any lingering click-focus (even on a page with no links) locked hover out entirely. Flipped precedence to `hoverId ?? focusId`: every hovered chip now glows and draws its curves immediately, focused or not; releasing hover restores the focused page's curves. New feature: clicking a chip now also slides in a right-side scrollable reading panel (`GET /pages/{path}`) rendering frontmatter as chips and the body via ReactMarkdown; `[[wikilinks]]` in the panel are clickable and re-focus/load that page (same `#folder__page` anchor scheme as WikiView); Escape and background click close it. Verified live in Chromium: 41/41 checks across light + dark, including the exact regression sequence (click unlinked chip → hover linked chip → glow + curves). `npm run build` clean. |
| 2026-07-04 | Claude | **Link View (backlog item 27, "Graph View") implemented** (branch: `link-view` — name requested explicitly, breaking the usual `feature/<desc>` convention). New sidebar view showing the whole wikilink structure as a grouped grid (Obsidian-style but not force-directed, per the mockups in `Visualization Page Concept/` at the repo root): pages as pill chips grouped into sections per entity folder (`_type.yaml` `name` + `description` become section title + subtitle), hover dims unrelated nodes and draws curved SVG connection lines across sections, click focuses (thicker/brighter curves, deeper dim), Escape or background click resets, footer stats bar shows node/connection counts. Backend: new `GET /api/pages/graph` (`WikiManager.get_link_graph()`) returns all nodes + deduplicated edges + groups in a single wiki scan — chosen over calling `GET /pages/{path}/backlinks` per page, which is N+1 on top of a function that already scans every page per call (N pages = N full scans). Route registered before the `GET /pages/{path:path}` catch-all so `graph` isn't parsed as a page path. Edges resolve `[[folder/page]]` links in body AND frontmatter; broken links, self-links, and duplicates excluded; hover/focus highlighting is undirected (out-links + backlinks). Frontend: `LinkView.tsx` (hand-rolled SVG/CSS, no graph library needed), `Links` nav entry (`Network` icon), `Links` case in `App.tsx`. 5 new backend tests (`test_link_graph.py`); 270 passed, same 12 pre-existing Python 3.14 env failures as baseline (confirmed via stash-and-rerun). `npm run build` clean. Verified live in Chromium (Playwright) against a 27-page seeded sample workspace (gitignored `backend/workspaces/default`): 29/29 checks passing across light + dark mode covering rest/hover/focus/Escape/background-reset. |
| 2026-07-03 | Nick | **Switched ingest off Sonnet to `anthropic/claude-haiku-4.5`** in the Portainer deploy variables, resolving the long-standing "evaluate a cheaper ingest model" item. Local `.env`'s `INGEST_AI_MODEL` synced to match by Claude. Extraction-quality-vs-cost tradeoff not yet validated against real ingests — see the caveat added to Immediate Next Steps item 7. |
| 2026-07-03 | Claude | **Added Anthropic prompt caching to the ingest LLM call.** `_run_ingest_llm()` was resending the full wiki context (index + every existing page) on every ingest with no caching — pure cost with no reuse. Split `INGEST_HUMAN_TEMPLATE` into a `_PREFIX` (wiki index + existing pages — the largely-stable, reused chunk) and `_SUFFIX` (source doc + instructions — always different); when the configured ingest provider is Anthropic (native, or OpenRouter routed to an `anthropic/*` model), both the system prompt and the prefix now carry `cache_control: {type: "ephemeral"}` breakpoints as structured content blocks. New `_supports_cache_control()` gates this off for other providers (OpenAI, Google, OpenRouter-to-non-Anthropic) so they keep getting plain string content — untested whether they'd accept or reject the extra field, so default to the known-safe path. Caveat: since `existing_pages` is rebuilt from every wiki page on each call and can change mid-batch as prior documents in the same bulk-ingest get written, the cache hits reliably within a tight burst before writes land, less so across a long-running batch. 8 new tests (`test_wiki_manager.py`); one of them initially failed only in full-suite runs because `main.py`'s `load_dotenv()` leaks the real `.env`'s `INGEST_AI_PROVIDER=openrouter` into the test process once another test module imports `main` first — fixed by having that test explicitly force a non-Anthropic provider instead of relying on the var being merely absent. 269 passed, same 12 pre-existing unrelated failures as baseline (confirmed via stash-and-rerun). Written while ingest was still on Sonnet, orthogonal to the model choice itself — see the entry above for the same-day switch to Haiku 4.5. |
| 2026-07-02 | Claude | **`rebuild_schema()` now fails loudly on a missing `SCHEMA_TEMPLATE.md`; fixed a test that was corrupting the real `SCHEMA.md` on every run.** Surfaced while walking through the dynamic-folder/`create_folder()` code path: `rebuild_schema()` silently returned if `schema/SCHEMA_TEMPLATE.md` was missing, so `SCHEMA.md` (and the LLM's view of entity types) could drift out of sync with zero error surfaced. Confirmed via `export_routes.py` that neither restore path (`_restore_full`, `_restore_template`) depends on that silent-skip for correctness — `_reinit_wiki_manager()` already treats a failed `WikiManager` construction as an anticipated, safely-handled state. Changed `rebuild_schema()` to raise `FileNotFoundError`; kept `WikiManager.__init__` crash-safe by catching that one case there (per `test_wiki_manager_init_without_schema_files`, which documents construction must never crash even on a bare schema dir). While verifying with the full test suite, discovered `tests/test_search_and_tags.py`'s `wiki_env` fixture constructed `WikiManager(...)` without a `schema_dir` override — so it defaulted to the real, checked-in `backend/schema/` dir and overwrote `SCHEMA.md` with test-fixture content (an empty/`clients`-only schema) on every local test run. Added an isolated tmp `schema_dir` to the fixture and both `WikiManager(...)` call sites in that file. 261 passed, same 12 pre-existing unrelated failures as baseline (confirmed via stash-and-rerun); no more repo-file pollution from `pytest tests/`. Commit `468d62f`, pushed to `main`. |
| 2026-07-02 | Claude | **Ingest gets its own AI model bucket; fix merges into lint.** Root cause: `WikiManager.__init__` built the shared `self.llm` (used by ingest, query, and tag suggestion) with `_init_llm()` and no operation prefix, so ingest silently used the global `AI_PROVIDER`/`AI_MODEL` — never a per-operation override — which read as "hardcoded." Added `self.ingest_llm = self._init_llm("ingest")` (new `INGEST_AI_PROVIDER`/`INGEST_AI_MODEL` env vars) and pointed `_run_ingest_llm` at it. Also collapsed `FIX_AI_PROVIDER`/`FIX_AI_MODEL` into the `LINT_AI_*` bucket (`_run_fix_llm` now calls `_init_llm("lint")`) since fix is a follow-on step of lint and both were already set to the same model — now exactly 3 buckets: ingest, lint (covers fix), and default (query/tags/fallback). `docker-compose.yml`, `.env.example`, `.env`, `docs/deployment.md` updated; ADR 0004 written. No behavior change for the live deployment — `INGEST_AI_*` left unset so ingest stays on Sonnet, and `LINT_AI_*` already matched the old `FIX_AI_*` value. |
| 2026-07-01 | Claude | **`/api/paste` now honors an explicit `filename` field.** The Trigger.dev automation sends `{"filename": "crm-john-doe-acme.md", "content": "..."}`, but the endpoint only ever read a `name` field (used by the frontend paste-modal UI for free-text titles) and force-appended `.txt` to it — so external callers' filenames were silently discarded in favor of a `paste-<timestamp>.txt` fallback. Added an `explicit_filename` path in `paste_source()` (`backend/api/routes.py`) that takes precedence over `name`, is sanitized via the existing `secure_filename()`, and is used verbatim (extension included, no `.txt` forcing) — the `name` field's behavior for the paste UI is unchanged. 3 new tests in `test_sources.py`; 261 passing (same 12 pre-existing unrelated Python 3.14 failures as before). |
| 2026-07-01 | Claude | **Fixed production outage caused by the external API-key middleware** (from the same-day commit `adfdbdd`). Root cause: the middleware gated `/api/*` requests on presence of Cloudflare's `CF-Connecting-IP` header, assuming that header only appeared on the external Trigger.dev automation's calls. Wrong — Cloudflare adds that header to every request tunneled through Cloudflare, including normal browser visits to the main site, since the whole site is Cloudflare-tunneled, not just the new API route. First redeploy after the middleware landed 401'd every real user request; the wiki UI showed "Failed to fetch pages" / empty page lists, which looked like lost volumes but no data was ever touched. Fixed by gating on `request.headers.get("host")` matching a new `FARAGOPEDIA_API_HOSTNAME` env var (the dedicated tunnel hostname) instead of header presence — see updated ADR 0003. Added regression test `test_frontend_request_with_cf_header_is_not_gated`; all 8 middleware tests pass. **Action needed from user before this fixes the live site:** set `FARAGOPEDIA_API_HOSTNAME=faragopedia-api.ai-wise.uk` in the Portainer stack's environment variables, then redeploy. |
| 2026-07-01 | Claude | **External API exposure & auth — backend middleware done** (branch: `feature/external-api-auth`). A Trigger.dev automation in the separate `FaragoProjects-Rocketreach-leads-research` project needs to call `POST /api/paste` + `POST /api/sources/{filename}/ingest` from off-network. Added `external_api_key_middleware` to `main.py`: requires `X-API-Key` matching `FARAGOPEDIA_API_KEY` on any `/api/*` request carrying Cloudflare's `CF-Connecting-IP` header (absent on internal Docker-network calls, so frontend traffic is unaffected). No-op when `FARAGOPEDIA_API_KEY` is unset. `FARAGOPEDIA_API_KEY` wired into `.env.example` and `docker-compose.yml`. ADR 0003 written. 6 new tests passing (`test_external_api_key_middleware.py`); 256 pre-existing tests unaffected (11 pre-existing failures confirmed unrelated — Python 3.14 env issues in `test_api.py`/`test_setup_routes.py`/`test_wiki_import.py`, present on `main` before this branch). This is the defense-in-depth layer; the primary gate (Cloudflare Access + Service Token on a new tunnel route) is dashboard-only and still needed configuring by the user — see ADR 0003 and the handoff doc in `FaragoProjects-Rocketreach-leads-research/docs/`. Superseded by the entry above — the tunnel hostname changed during setup. |
| 2026-07-01 | Claude | **External API exposure & auth — fully verified end-to-end.** Cloudflare Access + Service Token configured on hostname `faragopedia-api.ai-wise.uk` (not the originally planned `api.faragopedia.ai-wise.uk` — that second-level subdomain wasn't covered by Cloudflare's default Universal SSL wildcard, `*.ai-wise.uk`, which only covers one level of nesting; HTTPS reset at the TLS handshake while plain HTTP served the backend fully unauthenticated — caught and fixed by renaming to a single-level subdomain before anyone else found it). ADR 0003 updated to reflect the real hostname. Live curl verification: no headers → `403` (Cloudflare Access); CF-Access creds only, no `X-API-Key` → `401` (backend middleware live); CF-Access creds + correct `X-API-Key` → `200` full response. Both auth layers confirmed working together. `FARAGOPEDIA_API_URL`, `FARAGOPEDIA_CF_CLIENT_ID`, `FARAGOPEDIA_CF_CLIENT_SECRET`, `FARAGOPEDIA_API_KEY` handed off to the `FaragoProjects-Rocketreach-leads-research` project for its Trigger.dev automation. |
| 2026-05-19 | Claude | **Per-operation AI model routing + structured output migration.** Added `LINT_AI_PROVIDER/MODEL` and `FIX_AI_PROVIDER/MODEL` env var overrides to `_init_llm()` — any operation can now use a different model/provider without code changes. Fixed docker-compose to pass the new vars into the container. Migrated all three LLM operations (ingest, lint, fix) from `PydanticOutputParser` to `with_structured_output()` — resolves Gemini output truncation and markdown-fence parse failures, and makes structured output model-agnostic. Lint and fix currently routed to `anthropic/claude-haiku-4.5` via OpenRouter (~$0.10/lint vs ~$0.50 for Sonnet). ADR 0002 written. |
| 2026-05-19 | Claude | **Web Search Sources — Phase 2 smoke test passed. Feature fully verified end-to-end.** Search renders ~10 Brave results; checkbox selection and count label work; "Ingest N Selected Sources" fires the crawl toast and closes the modal; sources land in Sources view; Ingest creates wiki pages. Known limitation: JS-rendered/auth-gated pages (LinkedIn, paywalled sites) return empty crawled content and fail at Wisecrawler's analyze step — this is pre-existing crawler behaviour, not a web-search bug. Feature is production-ready. |
| 2026-05-15 | Claude | **Web Search Sources — merged to `main` and deployed for first inspection.** Branch `feature/web-search-sources` (6 commits) merged via `--no-ff` (`674435f`); pushed to GitHub. Portainer redeploy of Faragopedia confirmed the new `🔍 Search` tab renders; clicking Search surfaced 503 "WISECRAWLER_BASE_URL is not configured" — wiring on the Faragopedia side is correct, the env vars just aren't set on the deployed stack yet. **Next actions (user, when ready):** (1) Add `WISECRAWLER_BASE_URL` + `WISECRAWLER_API_KEY` to Faragopedia's Portainer stack env; (2) deploy Wisecrawler with the `POST /v1/search` route from the brief at `docs/superpowers/specs/2026-05-15-wisecrawler-search-endpoint-brief.md`; (3) sign up for Brave Search API and add `BRAVE_API_KEY` to Wisecrawler stack env; (4) run Phase 2 of the smoke runbook in `docs/superpowers/plans/2026-05-15-web-search-sources-faragopedia.md`. |
| 2026-05-15 | Claude | **Web Search Sources — Faragopedia side complete** (branch: `feature/web-search-sources`). Tasks 1–3 implemented and reviewed: `agent.wisecrawler.search()` client function with 3 unit tests, `POST /api/search` proxy route with 6 route tests, new `🔍 Search` tab in `AddSourcesModal.tsx` (query → Brave-backed results → checkbox-select → ingest via existing `/scrape-urls` pipeline). Backend tests: `test_wisecrawler.py` 7/7, `test_sources.py` 15/15 passing. Frontend `npm run build` clean. Wisecrawler-side `POST /v1/search` is a separate repo — portable brief at `docs/superpowers/specs/2026-05-15-wisecrawler-search-endpoint-brief.md`. Live end-to-end smoke test pending Brave API key. |
| 2026-04-24 | Claude | **Entity Type Templates — designed and planned**. Design spec saved to `docs/superpowers/specs/2026-04-24-entity-templates-design.md`. Full 5-task TDD implementation plan saved to `docs/superpowers/plans/2026-04-24-entity-templates.md`. Feature: during setup wizard completion, generate a `_template.md` per entity type co-located with `_type.yaml`; filter `_`-prefixed files from `list_pages()`; pre-populate new pages from the template. Pure backend — no frontend changes. No code changes yet. |
| 2026-04-22 | Claude | **Settings Section — designed and planned** (branch: `setup-wizard`). Design spec saved to `docs/superpowers/specs/2026-04-22-settings-design.md`. Full 13-task TDD implementation plan saved to `docs/superpowers/plans/2026-04-22-settings-implementation.md`. Feature covers: slide-out SettingsDrawer (theme toggle, reconfigure, export zip), Tailwind dark mode (`dark:` class strategy), backend export/import API (3 endpoints), SetupWizard step-0 import-from-backup flow. Backend tasks (1–5) → Claude. Frontend tasks (6–13) → Gemini. No code changes yet. |
| 2026-04-21 | Claude | **Setup Wizard — All 10 tasks complete** (branch: `setup-wizard`). Tasks 3–9 implemented: `setup_wizard.py` Pydantic models + core functions + `complete_setup()`; `setup_routes.py` 5 endpoints + `suggest_schema_llm()`; `main.py` startup migration + WikiManager init; `Sidebar.tsx` wikiName prop + Reconfigure button; `App.tsx` setup state gating + reconfigure flow; `SetupWizard.tsx` full 3-step wizard (identity → schema review → confirm/launch). `wiki_config.json` generated on setup completion. |
| 2026-04-21 | Claude | **Setup Wizard — Tasks 1–2 complete** (branch: `setup-wizard`). Task 1: `WikiManager._load_system_prompt()` now returns a stub string instead of raising `FileNotFoundError` when schema files are absent. Task 2: Replaced module-level `WikiManager` singleton in `routes.py` with FastAPI DI (`get_wiki_manager`, `set_wiki_manager`, `WM = Annotated[WikiManager, Depends(...)]`); `safe_wiki_filename` now takes explicit `wm` param; all 139 tests updated and passing. Tasks 3–10 remain. |
| 2026-04-20 | Claude | **Desktop UI/UX Polish**: Standardized list and search item padding, adjusted chat bubble spacing, constrained Wiki width for readability, and fixed search results layout bugs (nested scrollbars, overlap). Changed New Page icon. |
| 2026-04-20 | Claude | **Branch Merges**: Merged all feature branches (`big-refactor`, `dynamic-folders`, `search-and-tags`, `bulk-actions`, `linting-system`) into `main` and pruned local/remote branches. |
| 2026-04-20 | Claude | **Actionable Lint — Tasks 4–7 complete** (branch: `bulk-actions` / `linting-system`). API endpoints for lint fix & snapshot management added. Frontend: implemented `LintView.tsx` with bulk apply and `SnapshotsPanel.tsx` for rollbacks. Wired up successfully. |
| 2026-04-20 | Claude | **Actionable Lint — Tasks 1–3 complete**. Backend fully implemented: `LintFinding` updated with `fix_confidence` and `fix_description`; new models `LintFixPlan`, `FixReport`, `Snapshot`; `FIX_HUMAN_TEMPLATE` added; snapshot methods added to `WikiManager`; `fix_lint_findings` + `_run_fix_llm` added; `snapshots_data` Docker volume added. |
| 2026-04-19 | Claude | **Bulk Move & Bulk Download — fully implemented** (branch: `bulk-actions`). All 7 tasks complete. Backend: `POST /pages/bulk-move` (renames pages between entity subdirs, rewrites all `[[wikilinks]]` across the wiki via `rewrite_wikilinks`), `POST /pages/bulk-download` (ZIP stream of selected pages), `POST /sources/bulk-download` (ZIP stream of selected sources). Frontend: new `MoveDialog.tsx` component (radio-button destination picker), bulk Move + Download buttons added to `WikiView` and `SourcesView` desktop toolbars and mobile floating action menus. 12 backend tests passing, 3 smoke test sections added. Branch pushed to GitHub. |
| 2026-04-19 | Claude | **Search & Tags — fully implemented** (branch: `search-and-tags`). All 8 tasks complete. Backend: `_parse_frontmatter`, `_render_frontmatter`, `_strip_markdown`, `_rebuild_search_index` added to `WikiManager`; index rebuilt on every write; `update_page_tags`, `update_source_tags` added; `_suggest_tags` via LLM; 5 new API endpoints (`GET /search/index`, `GET /tags`, `PATCH /pages/{path}/tags`, `PATCH /sources/{filename}/tags`, `POST /search/rebuild`). Frontend: `WikiView.tsx` — full-width search bar, client-side results panel with tag filter row, tag chips below page title with add/remove/AI-suggestion UI; `SourcesView.tsx` — same search + tag chips pattern. 111 backend tests passing. |
| 2026-04-18 | Claude | **Search & Tags — designed and planned** (branch: `search-and-tags`, off `dynamic-folders`). Per-view keyword search (client-side JSON index), shared free-form tag system (pages + sources), AI tag suggestion. Design spec saved to `docs/superpowers/specs/2026-04-18-search-and-tags-design.md`. Full 8-task TDD implementation plan saved to `docs/superpowers/plans/2026-04-18-search-and-tags.md`. No code changes yet. |
| 2026-04-18 | Claude | **Dynamic Folders — all 7 tasks complete** (branch: `dynamic-folders`). Seeded `_type.yaml` for 5 entity folders; built `schema_builder.py` (TDD, 6 tests); added folder CRUD + page move + wikilink rewriting to `WikiManager` (TDD, 10 tests); added 5 new API endpoints (TDD, 17 API tests); updated `WikiView.tsx` with dynamic sidebar, New Folder dialog, Move Page dialog; regenerated `SCHEMA.md`; e2e integration test. 87 tests passing. |
| 2026-04-17 | Claude | **Dynamic Folders feature designed and planned** (branch: `dynamic-folders`, off `big-refactor`). Designed collaborative wiki architecture: `_type.yaml` per folder, `SCHEMA_TEMPLATE.md` + auto-generated `SCHEMA.md`, folder CRUD, page move, wikilink rewriting. Full 7-task implementation plan saved to `docs/superpowers/plans/2026-04-17-dynamic-folders.md`. No code changes yet — plan only. |
| 2026-04-16 | Gemini | **Wiki-Concept Integration — Tasks 1–12 complete** (branch: `big-refactor`). All frontend and backend tasks finished, verified with tests. |
| 2026-04-16 | Claude | **Wiki-Concept Integration — Tasks 1–9 complete** (branch: `big-refactor`). See details below. Tasks 10–12 remain. |
| 2026-04-15 | Claude | **Wiki-Concept Integration Plan**: Authored design spec (`docs/superpowers/specs/2026-04-15-wiki-integration-design.md`) and full implementation plan (`docs/superpowers/plans/2026-04-15-wiki-integration-claude.md`). Plan covers 12 tasks: schema files, new Pydantic models, recursive traversal, path security, ingest redesign, query update, lint operation, create_new_page, API routes, WikiView tree, LintView/Sidebar/App, and final integration test. |
| 2026-04-14 | Gemini | **Documentation Audit**: Synchronized `AGENTS.md`, updated `docs/flaws-and-bugs-report.md` with resolved features, and authored [ADR 0001](decisions/0001-file-management-and-ingestion.md). |
| 2026-04-14 | Gemini | **Improved Ingestion**: Added manual ingestion control. Users can now upload sources without immediate ingestion, track status via a new metadata system, and trigger ingestion manually from the Sources view. |
| 2026-04-14 | Gemini | **Sources Navigation**: Implemented back/forward history navigation in the Sources view, mirroring the Wiki view behavior. |
| 2026-04-14 | Gemini | **File Management**: Added Archive, Restore, Delete (Trash Bin), and Download capabilities for both Wiki pages and Sources. Implemented a new 'Archive' storage location and UI view. Added 'New Page' feature (Untitled.md default). |
| 2026-04-14 | Gemini | **Sources View**: Added a new view to browse and read raw source files (including PDF text extraction). Implemented backend endpoints `GET /api/sources` and `GET /api/sources/{filename}`. |
| 2026-04-14 | Gemini | **Deployment Fixes**: Resolved "empty container" issue by removing source code volume mounts in `docker-compose.yml`. Updated `backend/main.py` CORS and frontend `App.tsx`/`WikiView.tsx` to use dynamic backend URLs based on `window.location.hostname`. |
| 2026-04-14 | Claude       | **Ingestion Race Condition Fix**: Added `asyncio.Lock` to `WikiManager`. `ingest_source` split into two phases — LLM inference runs concurrently, file writes serialized. 33/33 tests passing. Merged to main. |
| 2026-04-14 | Claude       | **Interactive WikiLinks Fix**: Fixed filename mismatch between `_get_page_path` and `secure_filename`. Added `safe_wiki_filename` to routes for path-traversal-safe page lookups. Fixed `processWikiLinks` in `WikiView.tsx` to mirror backend sanitization rules. 18/18 tests passing. Merged to main. |
| 2026-04-14 | Gemini       | **Interactive WikiLinks & Port Refactoring**: Changed backend port to 8300 to resolve allocation conflicts. Updated all API calls and documentation. Implemented interactive `[[WikiLinks]]` in the frontend for associative navigation. |
| 2026-04-14 | Gemini       | **Local Development Workflow**: Verified local execution of FastAPI and Vite without Docker. Successfully tested ingestion and chat with OpenRouter/Claude Sonnet. |
| 2026-04-13 | Gemini       | **Implemented Multi-Provider LLM Support**: Added dynamic switching between OpenAI, Anthropic, Gemini, and OpenRouter via factory pattern in `WikiManager`. Updated tests and API to handle multiple providers. |
| 2026-04-13 | Gemini       | **Finalized MVP Features**: Implemented `WikiView`, `Upload`, and `Chat` frontend views with `react-markdown` and `lucide-react`. Added Wiki Health Check logic to `WikiManager`. |
| 2026-04-13 | Gemini       | **Completed Scaffolding**: Built FastAPI backend with upload/chat routes and React/Vite/Tailwind frontend layout. |
| 2026-04-13 | Gemini       | **Architectural Design**: Authored design docs and implementation plans for the LLM Wiki webapp. |
| 2026-04-13 | Claude       | Initialized project scaffold, shared AI context, Docker skeleton. |

---

## What Exists Now

- [x] Project scaffold with shared AI-agent context (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`)
- [x] Git configuration (`.gitignore`, `.editorconfig`)
- [x] Docker setup and project structure (`backend/`, `frontend/`, `sources/`, `wiki/`)
- [x] Dockerfiles and docker-compose.yml with named volumes
- [x] Initial FastAPI (backend/main.py) and React (frontend/) placeholders
- [x] Backend routes for upload and chat (with security and Docker fixes)
- [x] Frontend layout with Sidebar and view switching (React + Tailwind)
- [x] WikiManager with LangChain ingestion and health check logic
- [x] Functional Wiki, Upload, Chat, and Health Check UI views
- [x] Multi-Provider LLM Integration (OpenAI, Anthropic, Gemini, OpenRouter)
- [x] Documentation structure (`docs/status.md`, `docs/decisions/`)
- [x] Port conflict resolved (Backend moved to 8300)
- [x] Local development verification (FastAPI + Vite)
- [x] Interactive [[WikiLinks]] ✅ Fixed (2026-04-14)
- [x] Ingestion Race Conditions ✅ Fixed (2026-04-14)
- [x] Backlinks/Linked Mentions ✅ Fixed (2026-04-14)
- [x] Navigation History (back/forward) ✅ Fixed (2026-04-14)
- [x] Edit Page capability ✅ Fixed (2026-04-14)
- [x] Sources View (Browse/Read raw data) ✅ Fixed (2026-04-14)
- [x] File Management (New, Archive, Restore, Delete, Download) ✅ (2026-04-14)
- [x] Improved Source Ingestion (Manual control, Status tracking) ✅ (2026-04-14)
- [x] Sources Navigation (Back/Forward) ✅ (2026-04-14)
- [x] Dynamic Folders (user-managed wiki folders, page move, wikilink rewriting, auto-generated SCHEMA.md) ✅ (2026-04-18) — branch: `dynamic-folders`
- [x] Search & Tags (per-view keyword search, shared tag vocabulary, AI tag suggestion) ✅ (2026-04-19) — branch: `search-and-tags`
- [x] Bulk Move (wiki pages between entity types, automatic wikilink rewriting) ✅ (2026-04-19) — branch: `bulk-actions`
- [x] Bulk Download (pages + sources as ZIP archive) ✅ (2026-04-19) — branch: `bulk-actions`
- [x] Actionable Lint (checkbox findings, Apply Selected, snapshot rollback) ✅ (2026-04-20) — branch: `bulk-actions`
- [x] Setup Wizard (first-run identity + LLM schema generation, company-agnostic config) ✅ (2026-04-21) — branch: `setup-wizard`
- [ ] Settings Section (slide-out drawer, dark mode, export/import infrastructure files) 🟡 Planned — branch: `setup-wizard`
- [ ] Entity Type Templates (`_template.md` per entity type, pre-populated new pages) 🟡 Planned — `main`
- [x] Source-document link resolver (`GET /api/job/{key}` → closed lookup table → 302, host-allowlisted) ✅ (2026-09-09) — branch: `feature/job-page-import`, ADR 0006
- [x] VPS production deployment (OVHcloud, separate from the NUC's dev/test role) ✅ (2026-09-09) — branch: `vps-prod-deploy`, ADR 0007

---

## Actionable Lint Progress (branch: `bulk-actions`)

| Task | Status | Description |
| ---- | ------ | ----------- |
| 1 | ✅ Done | Updated `LintFinding` (`fix_confidence`, `fix_description`); added `LintFixPlan`, `FixReport`, `Snapshot` models; updated `LINT_HUMAN_TEMPLATE`; added `FIX_HUMAN_TEMPLATE` |
| 2 | ✅ Done | Snapshot methods (`create_snapshot`, `list_snapshots`, `restore_snapshot`, `delete_snapshot`) + `snapshots_data` Docker volume |
| 3 | ✅ Done | `fix_lint_findings` + `_run_fix_llm` on WikiManager |
| 4 | ✅ Done | API endpoints: `POST /lint/fix`, `GET /snapshots`, `POST /snapshots/{id}/restore`, `DELETE /snapshots/{id}` |
| 5 | ✅ Done | `LintView.tsx` — checkboxes, fix-confidence badges, Select All, Apply Selected button, inline FixReport panel |
| 6 | ✅ Done | `SnapshotsPanel.tsx` — collapsible snapshot list with Restore (+ confirmation) and Delete |
| 7 | ✅ Done | Wire `SNAPSHOTS_DIR` into `WikiManager` instantiation in `routes.py` |

**Current test state:** All tests passing.

---

## Bulk Actions Progress (branch: `bulk-actions`)

| Task | Status | Description |
| ---- | ------ | ----------- |
| 1 | ✅ Done | `POST /pages/bulk-move` — moves pages between entity subdirs, rewrites all wikilinks via `rewrite_wikilinks` helper |
| 2 | ✅ Done | `POST /pages/bulk-download` — streams selected wiki pages as `pages-export.zip` |
| 3 | ✅ Done | `POST /sources/bulk-download` — streams selected source files as `sources-export.zip` |
| 4 | ✅ Done | `MoveDialog.tsx` — radio-button destination picker modal |
| 5 | ✅ Done | `WikiView.tsx` — bulk Move + Download buttons (desktop toolbar + mobile floating menu) |
| 6 | ✅ Done | `SourcesView.tsx` — bulk Download button (desktop toolbar + mobile floating menu) |
| 7 | ✅ Done | Smoke tests — sections 9–11 for move dialog, wiki download, sources download |

**Current test state:** 12 backend tests passing, 0 failed.

---

## Search & Tags Progress (branch: `search-and-tags`)

| Task | Status | Description |
| ---- | ------ | ----------- |
| 1 | ✅ Done | WikiManager parsing helpers + `_rebuild_search_index` + startup init |
| 2 | ✅ Done | Hook `_rebuild_search_index` into all write operations |
| 3 | ✅ Done | WikiManager tag management (`update_page_tags`, `update_source_tags`) |
| 4 | ✅ Done | `_suggest_tags` + hook into `save_page_content` and `ingest_source` |
| 5 | ✅ Done | API endpoints (`/search/index`, `/tags`, PATCH tags, `/search/rebuild`) |
| 6 | ✅ Done | Frontend WikiView — search bar + results panel |
| 7 | ✅ Done | Frontend WikiView — tag chips, add/remove, filter row, AI suggestion UI |
| 8 | ✅ Done | Frontend SourcesView — search bar + tag chips |

**Current test state:** 111 passed, 0 failed.

---

## Dynamic Folders Progress (branch: `dynamic-folders`)

| Task | Status | Description |
| ---- | ------ | ----------- |
| 1 | ✅ Done | Seed `_type.yaml` metadata files for 5 entity folders |
| 2 | ✅ Done | `schema_builder.py` — type discovery + SCHEMA.md assembly (TDD, 6 tests) |
| 3 | ✅ Done | `WikiManager` folder CRUD + page move + wikilink rewriting (TDD, 10 tests) |
| 4 | ✅ Done | 5 new API endpoints: entity-types, folder create/rename/delete, page move (TDD, 17 tests) |
| 5 | ✅ Done | `WikiView.tsx` — dynamic sidebar, New Folder dialog, Move Page dialog |
| 6 | ✅ Done | Regenerate `SCHEMA.md` from template + `_type.yaml` seed files |
| 7 | ✅ Done | End-to-end integration test |

**Current test state:** 87 passed, 0 failed.

---

## Wiki-Concept Integration Progress (branch: `big-refactor`)

| Task | Status | Description |
| ---- | ------ | ----------- |
| 1 | ✅ Done | Data migration: schema files copied to `backend/schema/`, wiki subdirs created, old pages deleted, Dockerfile updated |
| 2 | ✅ Done | New Pydantic models: `WikiPage`, `FaragoIngestionResult`, `LintFinding`, `LintReport`; `schema_dir` param + `_load_system_prompt()` added to WikiManager |
| 3 | ✅ Done | Recursive traversal: `list_pages()`, `update_index()`, `get_backlinks()` updated for subdirectory structure; `test_km_features.py` replaced |
| 4 | ✅ Done | Path security: `safe_wiki_filename` now requires `subdir/page.md` form with known entity subdirectory |
| 5 | ✅ Done | Ingest redesign: schema-aware `ingest_source()` using `FaragoIngestionResult` with retry logic; old `Entity`/`IngestionResult` models removed |
| 6 | ✅ Done | Query update: `query()` now uses system prompt + `ChatPromptTemplate`; `_run_query_llm()` extracted for testability |
| 7 | ✅ Done | Lint operation: `lint()` + `_run_lint_llm()` added; `health_check()` removed; `test_wiki_manager_health.py` deleted |
| 8 | ✅ Done | `create_new_page(entity_type)` — accepts entity_type param, writes to correct subdir with YAML frontmatter |
| 9 | ✅ Done | API routes — `GET /pages` grouped by entity type, `POST /lint` added, `GET /health` removed, all page routes use `{path:path}`, `POST /pages` accepts `entity_type`, `test_api.py` rewritten |
| 10 | ✅ Done | Frontend WikiView tree — collapsible entity sections, entity-type new-page menu, path-aware wikilinks |
| 11 | ✅ Done | Frontend Sidebar/LintView/App — replace Health Check with Lint nav, create LintView.tsx |
| 12 | ✅ Done | Final integration test |

**Current test state:** 52 passed, 0 failed (all backend tests clean).

## Setup Wizard Progress (branch: `setup-wizard`)

| Task | Status | Description |
| ---- | ------ | ----------- |
| 1 | ✅ Done | `WikiManager._load_system_prompt()` returns stub when schema files absent (no crash) |
| 2 | ✅ Done | FastAPI DI refactor: `get_wiki_manager`/`set_wiki_manager`/`WM` type alias; `safe_wiki_filename` takes explicit `wm`; 139 tests passing |
| 3 | ✅ Done | `setup_wizard.py` — Pydantic models + core functions (`is_setup_complete`, `get_wiki_config`, `migrate_existing`, `clear_setup`) + `BASE_SCHEMA_TEMPLATE` |
| 4 | ✅ Done | `setup_wizard.py` — `complete_setup()` orchestrator |
| 5 | ✅ Done | `setup_routes.py` — 5 setup API endpoints + `suggest_schema_llm()` |
| 6 | ✅ Done | `main.py` — startup migration + `WikiManager` init; register `setup_router` |
| 7 | ✅ Done | `Sidebar.tsx` — `wikiName` prop + Reconfigure button |
| 8 | ✅ Done | `App.tsx` — setup state gating + reconfigure flow |
| 9 | ✅ Done | `SetupWizard.tsx` — full 3-step wizard (identity → schema review → confirm/launch) |
| 10 | ✅ Done | End-to-end verification |

---

## Settings Section Progress (branch: `setup-wizard`)

**Plan:** `docs/superpowers/plans/2026-04-22-settings-implementation.md`
**Spec:** `docs/superpowers/specs/2026-04-22-settings-design.md`

### Backend (Claude implements)

| Task | Status | Description |
| ---- | ------ | ----------- |
| 1 | ⬜ Todo | `setup_wizard.py` — add `finalize_import()` function |
| 2 | ⬜ Todo | `export_routes.py` — `GET /api/export/bundle` (zip of 5 infrastructure files) |
| 3 | ⬜ Todo | `export_routes.py` — `POST /api/export/import` (stage zip, write SCHEMA.md + company_profile.md, return config) |
| 4 | ⬜ Todo | `export_routes.py` — `POST /api/export/import/finalize` (create entity folders, write wiki_config.json) |
| 5 | ⬜ Todo | `main.py` — register `export_router` under `/api/export` |

### Frontend (Gemini implements)

| Task | Status | Description |
| ---- | ------ | ----------- |
| 6 | ⬜ Todo | `tailwind.config.js` — add `darkMode: 'class'` |
| 7 | ⬜ Todo | `App.tsx` — theme state + `settingsOpen` + `useEffect` + render `SettingsDrawer` |
| 8 | ⬜ Todo | `Sidebar.tsx` — remove Reconfigure button, add gear icon + `onOpenSettings` prop |
| 9 | ⬜ Todo | `SettingsDrawer.tsx` — new slide-out component (theme segmented control, reconfigure button, export download) |
| 10 | ⬜ Todo | `SetupWizard.tsx` — add step-0 getting-started screen + import-from-backup flow |
| 11 | ⬜ Todo | Dark mode color mapping reference (no code — methodology task) |
| 12 | ⬜ Todo | Dark mode — `App.tsx` layout + inline chat UI |
| 13 | ⬜ Todo | Dark mode — `WikiView.tsx`, `SourcesView.tsx`, `ArchiveView.tsx`, `LintView.tsx` |

---

## Immediate Next Steps

1. **Execute Settings backend (Tasks 1–5)** — Claude implements `finalize_import` + `export_routes.py` + `main.py` registration on `setup-wizard` branch.
2. **Execute Settings frontend (Tasks 6–13)** — Gemini implements per `docs/superpowers/plans/2026-04-22-settings-implementation.md`.
3. Merge `setup-wizard` to `main` once Settings is complete and verified.
4. **Execute Entity Type Templates plan (Tasks 1–5)** — pure backend, `main` branch, per `docs/superpowers/plans/2026-04-24-entity-templates.md`.
5. Add Graph View (post-settings).
6. Monitor snapshot storage usage and add auto-pruning if needed.
7. ~~Switch ingest to a cheaper/faster model than Sonnet.~~ Done 2026-07-03 — `INGEST_AI_MODEL` set to `anthropic/claude-haiku-4.5` in the Portainer deploy variables (local `.env` synced to match). **Still open:** nobody's confirmed Haiku 4.5 holds up on entity-resolution/extraction quality against a real Sonnet-produced baseline — watch the next few real ingests for wrong create-vs-update decisions, malformed wikilinks, or missed entities before trusting it unattended.
8. **Decide when to promote the VPS to the real `faragopedia.ai-wise.uk` / `faragopedia-api.ai-wise.uk` hostnames** and retire (or keep as a dashboard-only fallback) the NUC's Cloudflare Access apps on those names. Until then the VPS lives on the temporary `-vps`-suffixed hostnames — see ADR 0007.
9. **After every future merge to `main`: merge `main` into `vps-prod-deploy` and redeploy the VPS Portainer stack.** This is a manual step with no automation behind it (confirmed the hard way on 2026-09-09 — see that day's entry above). Forgetting it means the VPS silently serves an older frontend/backend than what's on `main`.
10. **Migrate the remaining NUC data** (anything created on the NUC after the 2026-09-09 export/import) **to the VPS** once the VPS is confirmed stable, so the two instances don't diverge indefinitely.

---

## Entity Type Templates Progress (branch: `main`)

**Plan:** `docs/superpowers/plans/2026-04-24-entity-templates.md`
**Spec:** `docs/superpowers/specs/2026-04-24-entity-templates-design.md`

| Task | Status | Description |
| ---- | ------ | ----------- |
| 1 | ⬜ Todo | `schema_builder.py` — `generate_entity_template(folder_name, singular, fields, sections) -> str` |
| 2 | ⬜ Todo | `schema_builder.py` — `write_entity_templates(wiki_dir, entity_type_dicts)` |
| 3 | ⬜ Todo | `setup_wizard.py` `complete_setup()` — call `write_entity_templates()` after `_type.yaml` loop |
| 4 | ⬜ Todo | `wiki_manager.py` `list_pages()` — filter `_`-prefixed `.md` files from page list |
| 5 | ⬜ Todo | `wiki_manager.py` `create_new_page()` — read `_template.md` if present, fallback to stub |
| 6 | ⬜ Todo | `wiki_manager.py` `_slugify()` + `auto_rename_if_untitled()`; `routes.py` returns `new_filename`; `WikiView.tsx` navigates to new path on save |
| 7 | ⬜ Todo | Manual rename: `wiki_manager.py` `rename_page()`; `POST /pages/{path}/rename`; desktop sidebar pencil icon + inline input; mobile action menu Rename pill + input |

---

## Known Issues / Blockers

*   **Portainer's `POST /api/stacks/{id}/git/redeploy` requires the FULL existing env var list on every call, or it wipes the stack's env.** Confirmed 2026-09-10: calling it with `"env":[]` (intending "leave unchanged") actually overwrote the stack's persisted env vars with nothing, dropping `DATA_DIR` and causing the backend to bind-mount a relative fallback path instead of the real data volume. **Before any future redeploy via this endpoint:** `GET /api/stacks/{id}` first, and pass its `Env` array back verbatim (or merged with any intended change) in the redeploy call's `env` field. Never pass an empty array unless you actually intend to clear all env vars.
*   No CI existed until 2026-09-10 (see Recent Activity) — `.github/workflows/ci.yml` now runs pytest + `npm run build` on push/PR to `main`.
