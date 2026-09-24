# Roadmap Critical Review Log — 2026-07-07

Independent critical review of the 10-point roadmap and its implementation docs, performed before handing them to Sonnet-based build sessions. Method: every code anchor was re-verified against `Faragopedia-Sales` by four parallel codebase fact-check agents; every library/technique recommendation was checked for mid-2026 maintenance status and best-practice standing by two research agents; design decisions were then re-judged and each doc rewritten in place. Each doc carries a `Review status` row summarizing its changes.

## Verdict summary

| Doc | Verdict | Materiality of changes |
|---|---|---|
| 01 Production hardening | **UPGRADED** | High — architecture improved (same-origin nginx `/api` proxy), a live bug in the CORS snippet fixed, EOL Node base bumped, deploy-breaking gotchas added |
| 02 Security remediation | **UPGRADED** | High — two findings re-graded on evidence (zip-slip not exploitable; secrets largely mitigated); the two real criticals confirmed with exact anchors; a new HIGH added (destructive restore) |
| 03 Auth & user management | **UPGRADED** | High — dead library (passlib) replaced; test-migration strategy replaced (saves rewriting ~282 tests); CSRF/session/migration decisions made explicit |
| 04 Roles & sharing | **UPGRADED** | High — discovered the server-global active-workspace state; added step 0 (per-request workspace context) as a prerequisite; share tokens hashed |
| 05 Admin dashboard | **UPGRADED** | Medium — `with_structured_output(include_raw=True)` usage-capture gotcha added; missing chat relevance-pass call site added; price table made config-driven |
| 06 Routing & frontend | **UPGRADED** | Medium — metrics corrected (77 fetches not 174); `/chat` route added; v7 import guidance, URL-encoding rule, one-line dark-mode fix, react-markdown v10 pin note |
| 07 Version history | **UPGRADED** | Medium — revision capture extended to lint-fix/ingest/delete; concurrency switched to content-hash; no-op saves excluded |
| 08 Collaboration | **UPGRADED** | Low–Medium — SSE promoted (verified fine through cloudflared); toast-context reuse corrected; notification debounce + rename-path sync added |
| 09 Semantic search & RAG | **UPGRADED** | Medium — core motivating claim corrected (chat is 2-pass, lint is whole-wiki); vector store put behind an interface with numpy fallback; embedding made async |
| 10 UX polish | **UPGRADED** | Medium — five problem claims corrected against code so sessions fix real gaps; modal strategy moved to native `<dialog>`/Radix |

All 10 are **APPROVED for build** in their upgraded form. No doc was rejected; none survived entirely unchanged — the designs were fundamentally sound, but every doc contained at least one factual or currency error that would have cost a build session time.

## Corrections that changed substance (what the original docs got wrong)

1. **Zip-slip (doc 02 "C2/C3") is not exploitable.** CPython's `zipfile.extract/extractall` strips `..` components, leading slashes and drive letters (backend runs `python:3.11-slim`). The audit conflated `zipfile` with `tarfile`. Re-scoped to zip-bomb caps + defense-in-depth. The genuinely dangerous part found instead: `restore_snapshot()` **deletes the wiki before extracting** (wiki_manager.py:920-940) — now HIGH "H2" with a staged-swap fix.
2. **Secrets (doc 02 "C1") were mostly already handled.** `backend/.dockerignore` exists and excludes `.env`; `.env` was never in git history. Residual: pre-`.dockerignore` image layers and the missing `frontend/.dockerignore` entry. Downgraded to verify-and-rotate.
3. **The two real criticals stand, with exact anchors:** import-rename path traversal (`wiki_manager.py:1407/1411`, zero sanitization despite `secure_filename`/`safe_wiki_filename` existing at routes.py:102-165) and unvalidated `snapshot_id` (routes.py:527/538).
4. **The backend's "active workspace" is server-global module state** (`workspace_manager.py` `_active_workspace_id`/`_active_dirs`). Two users would flip each other's context. No original doc mentioned it; doc 04 now has it as step 0 and the overview sequencing flags it.
5. **"Chat stuffs the whole wiki into the prompt" was false** — chat is a 2-pass catalog-relevance flow (wiki_manager.py:813-817, :847); **lint** is the whole-wiki path. Doc 09's RAG case is restated on the true baseline (and is still compelling: per-question relevance-pass spend, no citations).
6. **Frontend metrics were overcounted:** 77 raw fetches across 12 files (claimed ~174/18); App.tsx has 17 useState (claimed ~28); manual history stacks live in WikiView, not App. WikiView's 1959 lines confirmed.
7. **Doc 10's problem list overstated five claims:** 8 aria-labels exist (claimed 1); spinners/skeletons exist in 20+ places (claimed none); Wiki search already shows a result count (WikiView.tsx:1025); the sidebar already highlights the active view (missing only `aria-current`); the mojibake placeholder doesn't exist in code (verify-or-drop). Confirmed real: zero modal focus management across all 9 dialogs, no favorites/recents, no command palette.
8. **Doc 01's CORS snippet had a real bug:** `"".split(",")` → `[""]` is truthy, so the localhost fallback was dead code and an empty env produced origin `""`. Fixed with filtered parsing.
9. **Cross-reference errors** in doc 01's out-of-scope (auth is 03 not 02; security remediation is 02 not 10) and a stale reference to a non-existent `10-security-fixes.md` — fixed.
10. **Chat is a view** (`currentView` case) that doc 06's route table omitted — `/chat` added.

## Library/currency verdicts applied

| Recommendation | Verdict | Action taken |
|---|---|---|
| `passlib` for hashing | **Dead** (last release 2020; breaks with bcrypt ≥4.1) | Replaced with `argon2-cffi` direct (OWASP argon2id baseline m=19456 KiB, t=2, p=1); `pwdlib` noted as alternative |
| `slowapi` | Aging but functional; suggested replacement `fastapi-limiter` **requires Redis** | Kept slowapi (in-memory, no extra service); hand-rolled token-bucket noted as acceptable alternative |
| `authlib` (OIDC) | Actively maintained; still standard | Confirmed; state/nonce/PKCE notes added |
| `fastapi-users` | Maintenance mode; no generic OIDC | Explicitly rejected in doc 03 (was previously unaddressed) |
| SQLModel + SQLite | Maintained, Pydantic-v2-native | Confirmed; migration story made concrete (`create_all` + `PRAGMA user_version` runner; Alembic as upgrade path) |
| `sqlite-vec` | Actively maintained (Mozilla Builders) — the "stalled" concern did not hold | Kept as default, but behind a thin `VectorStore` interface with a numpy brute-force fallback backend; LanceDB as scale escape hatch |
| `node:20-alpine` | **Past EOL 2026-04-30** | Bumped to `node:22-alpine` (24 also acceptable) |
| react-router | v7 current (data mode, `createBrowserRouter`); v8 splits packages | Specified `react-router` import path + data mode; TanStack Router considered/rejected |
| `@tanstack/react-query` v5 | Confirmed default choice; object-syntax only | Adopted with the v5 syntax note |
| `cmdk` | Maintained, React 18/19 OK, built-in scoring sufficient | Confirmed; dropped the need for a separate fuzzy lib |
| `focus-trap-react` | Superseded by native `<dialog>` / Radix Dialog | Doc 10 now prefers native `<dialog>` or Radix; focus-trap-react demoted to shim |
| `react-diff-viewer-continued` | Viable; `react-diff-view` lighter | Doc 07 prefers hand-rolled from structured hunks; both libs listed |
| `react-markdown` | Repo pins `^9.0.1`; v10 removed `className` | Pin/upgrade-deliberately note added to doc 06 |
| SSE behind cloudflared | Works transparently; no workarounds needed | Doc 08 promotes SSE to recommended with polling fallback |
| zip upload caps | Still needed regardless of zip-slip re-grade | `safe_extract` kept (with `commonpath` instead of `startswith`) |

## Improvements introduced by the review (not in the original roadmap)

- **Same-origin nginx `/api` proxy** (doc 01) — mirrors the existing Vite dev proxy; kills build-time env baking and most CORS surface; plus the `nginx-unprivileged`/`user:` compose gotcha and the 300s proxy timeout for slow LLM calls.
- **`dependency_overrides` test strategy** (doc 03) — the original plan implied retrofitting auth into 22 test files / ~282 tests; a root conftest override reduces that to near zero.
- **Session/share/invitation tokens stored hashed** (docs 03/04); explicit CSRF stance; login rate-limit + anti-enumeration.
- **`with_structured_output(..., include_raw=True)`** (doc 05) — without it the usage-tracking plan silently gets no token counts from 3 of the 6 call sites; the chat relevance-pass call site was also missing from the instrumentation list.
- **Content-hash optimistic concurrency** (doc 07) — revision-id-based checks fail for never-edited pages.
- **Embedding decoupled from the save path** (doc 09) — saves must not fail or slow when the embedding provider is down; `reindex` doubles as recovery.
- **`can()` action map with a `CHAT_MIN_ROLE` flag** (doc 04) — chat reads content but spends money; that tension is now an explicit operator choice.
- **Share-token endpoint allowlist tested exhaustively** (doc 04) — iterate all 72 routes and assert only the allowlist answers.

## Verified environment facts build sessions can rely on

- Backend: FastAPI on `python:3.11-slim`; **72 routes** (54 `routes.py`, 7 setup, 3 export, 8 workspace); requirements.txt is **unpinned** (pin new deps at least). Test suite: 22 files, ~282 tests, per-file fixtures, **no root conftest**.
- LLM: `_init_llm(operation)` factory (openai/anthropic/google/openrouter) with `{PREFIX}AI_PROVIDER/MODEL` env pattern; five call-site methods named exactly as the docs state; Anthropic `cache_control` already used for ingest; **no token-usage tracking exists**.
- Writes: `asyncio.Lock` per manager (wiki_manager.py:188) around save/move/rename/ingest/lint-fix.
- Storage: `workspaces/{slug}/{wiki,sources,archive,snapshots,schema}/`; registry at `workspaces/registry.json`; pages `entity/slug.md`; `search-index.json` rebuilt on writes.
- Frontend: React 18 + Vite + Tailwind; no router, no tests, no state library; 20 components; `@uiw/react-md-editor` + `react-markdown@^9`; `config.ts` is one line; Vite dev server proxies `/api → backend:8300`.
- Conventions: ADRs `docs/decisions/0001–0005` exist (**next: 0006**); `AGENTS.md` is the agent-protocol source of truth; update `docs/status.md` as work lands.
