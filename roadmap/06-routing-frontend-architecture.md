# 06 — URL Routing & Frontend Architecture Refactor

| Field | Value |
| --- | --- |
| Priority | P1 — unblocks deep-linking/sharing (04) and makes the codebase maintainable |
| Effort | L (3–5 sessions; can be phased) |
| Dependencies | Pairs with 01 (SPA fallback in nginx); enables 04 share links |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/frontend-architecture` |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — metrics corrected against code (77 fetches/12 files, not 174/18; App.tsx 520 lines/17 useState; the manual history stack lives in WikiView, not App); `/chat` route added; react-router v7 specifics + page-path URL-encoding rule + the one-line editor dark-mode fix written in. See `00-review-log.md`. |

## Problem

The frontend has no URL router — navigation is a `switch(currentView)` in `App.tsx` (verified, lines 296-415, cases `Wiki | Sources | Chat | Archive | Lint | Links`). Verified consequences:

- **No deep-linking / no shareable URLs** — refreshing resets to Wiki; you can't link someone to a page. This directly blocks share links (04).
- **Browser back/forward don't work**; `WikiView` fakes page history with its own `historyStack`/`forwardStack` arrays (App.tsx itself has none).
- **`App.tsx` (520 lines, 17 useState)** is a state hub prop-drilling into children.
- **`WikiView.tsx` (1959 lines, 52 component-level useState)** is a god component: page tree, editor, frontmatter UI, backlinks, chat panel toggle, mobile menus, tags, bulk actions, search, folder CRUD, resizable sidebar — all in one (verified inventory).
- **77 raw `fetch()` across 12 files** (verified: WikiView 21, App 15, SourcesView 12, ArchiveView 6, SetupWizard 5, AddSourcesModal 5, others ≤3), duplicated fetch logic, inconsistent error handling — 4 silent `.catch(() => {})` and 29 `catch (err: any)`.
- No shared API types; minimal memoization; no code-splitting; **no frontend tests, no test tooling at all** (verified: no vitest/jest/RTL in package.json).

(The original draft's "174 fetches across 18 files" and "~28 useState in App" were overcounts — corrected above so refactor progress is measured against real numbers.)

## Design

### A. Routing (highest value, do first)

Add **react-router v7 in library ("data") mode**: `createBrowserRouter` + `RouterProvider`. Install `react-router` (v7 merged the packages; import from `react-router` / `react-router/dom` so a future v8 bump is a no-op — `react-router-dom` is now a compat re-export). v7 requires React 18+ (repo is on `react ^18.2.0`, fine). TanStack Router was considered — better type-safety, but react-router's docs/familiarity win for mixed-session maintenance; note in ADR.

Routes:
```
/                      → redirect to /wiki
/wiki                  → WikiView (no page selected)
/wiki/:entity/:slug    → WikiView with page loaded from URL
/sources               → SourcesView
/sources/:filename     → SourcesView with source open
/chat                  → Chat view (exists today as a currentView case — the original draft missed it)
/links                 → LinkView
/lint                  → LintView
/archive               → ArchiveView
/admin                 → AdminDashboard (05, admin-only)
/share/:token          → public read-only viewer (04)
/login                 → LoginPage (03)
```
- **Page-path encoding rule (write it once, use everywhere):** wiki paths are `entity/slug.md` (verified layout); the URL carries `entity` and `slug` **without** `.md`, each segment `encodeURIComponent`-encoded. Helpers `pagePathToUrl(path)` / `urlToPagePath(entity, slug)` live next to the router. Current slugs are kebab-case ASCII so this is mostly future-proofing — but don't skip it; imported pages may carry unicode.
- `currentView` state and WikiView's manual `historyStack`/`forwardStack` are deleted; the router owns navigation. Back/forward, refresh, and bookmarks work for free.
- Page selection reads from `useParams()`; wikilink clicks (currently `processWikiLinks()` → custom `a` renderer → `fetchPageContent(path)`, verified WikiView.tsx:677/726) become `navigate(pagePathToUrl(path))`.
- nginx (from 01) already has the SPA fallback (`try_files $uri /index.html`) this requires.

### B. Centralized, typed API client

- `src/api/client.ts`: a typed `fetch` wrapper that sets `credentials: 'include'` (needed by 03), the `X-Workspace-Id` header (needed by 04 step 0), JSON handling, and **consistent error surfacing** (throws typed errors routed to toasts — kills the silent catches).
- `src/api/types.ts`: shared response types (`WikiPage`, `SearchEntry`, `SourceEntry`, `LinkGraph`, `User`, …) mirroring the backend Pydantic models. Replaces per-component inline duplicates and `any`.
- Adopt **`@tanstack/react-query` v5** (verified current major; object-syntax API only — `useQuery({ queryKey, queryFn })`) for data fetching/caching/invalidation and in-flight dedup. Wraps the client; gives loading/error states uniformly (feeds the UX work in 10).

### C. Decompose the god components

`WikiView.tsx` → `components/wiki/`:
- `PageTreeSidebar.tsx` (entity tree, folder CRUD, drag/move)
- `PageEditor.tsx` (markdown editor + save/edit state)
- `PageContent.tsx` (frontmatter chips + rendered markdown + backlinks)
- `FrontmatterEditor.tsx`
- `BulkActionsBar.tsx`
- `MobileWikiControls.tsx`
- `WikiView.tsx` becomes a thin composition (<300 lines) driven by route + react-query hooks.

`App.tsx` → thin shell: `<RouterProvider>` + context providers (`AuthContext` 03, `PermissionsContext` 04, `WorkspaceContext`, `OperationToastProvider` existing). `ChatPanel.tsx` is already extracted (verified — 20 components exist under `src/components/`). Target <200 lines.

### D. Hygiene / quick wins (bundle with the above)

- Replace `catch (err: any)` (29 sites) with a typed error helper; route the 4 silent catches through toasts.
- Extract duplicated frontmatter parsing to `src/utils/frontmatter.ts`.
- **Editor dark mode — the fix is one line** (verified): WikiView.tsx:1492 hard-codes `data-color-mode="light"` on the `@uiw/react-md-editor` wrapper and fakes dark with `dark:invert dark:hue-rotate-180`. MDEditor supports dark natively — set `data-color-mode={theme}` from the existing theme state and delete the invert classes.
- **Dependency pin note:** `react-markdown` is at `^9.0.1`; v10 removed the `className` prop. Either stay on v9 or handle the wrapper-div change deliberately during this refactor — don't let an incidental `npm update` do it.
- Route-level code-splitting with `React.lazy` + `Suspense`.
- Add **Vitest + React Testing Library** (`environment: 'jsdom'`); establish the first tests (utils, one modal, the page-load flow).
- Memoize long lists (page tree, search results); consider virtualization if a workspace exceeds a few hundred pages.

## Implementation plan (phased, each independently shippable)

1. **Router (Phase A).** Add react-router v7 (data mode); map views to routes incl. `/chat`; wire `useParams` page loading + the path-encoding helpers; delete `currentView` + WikiView's manual history. Verify back/forward/refresh/deep-link with webapp-testing. *Ship this alone first — it's the unblocker.*
2. **API client + types + react-query (Phase B).** Introduce `client.ts`/`types.ts`; migrate WikiView + SourcesView fetches first (33 of the 77); add `credentials: 'include'` + workspace header. Tests for the client (mocked fetch).
3. **Decompose WikiView (Phase C1).** Extract subcomponents behind the new hooks; no behavior change. RTL tests per extracted piece.
4. **Thin App.tsx + contexts (Phase C2).** Move state into contexts; remove prop drilling.
5. **Decompose SourcesView + hygiene (Phase D).** Typed errors, frontmatter util, editor dark mode (the one-liner), code-splitting, memoization.
6. **Testing baseline.** Vitest config + first suite; wire into CI expectations.

## Acceptance criteria

- `faragopedia.ai-wise.uk/wiki/clients/acme` deep-links straight to that page after refresh.
- Browser back/forward navigate view+page history correctly (WikiView's own history stacks are gone).
- A network failure surfaces a toast instead of silently doing nothing (0 remaining `.catch(() => {})`).
- Raw `fetch(` count in `src/` is 0 outside `src/api/client.ts` (was 77).
- `WikiView.tsx` and `App.tsx` are each well under 400 lines; no component over ~500.
- The markdown editor renders natively dark in dark mode (no `invert` classes).
- `npm run build` clean; route chunks split; `vitest` runs green.

## Notes for sequencing

- **Phase A (routing) should ship before 04's share links** (they need `/share/:token`).
- Phase B's `credentials: 'include'` should land with or right after 03 (auth); its `X-Workspace-Id` header is a prerequisite for 04 step 0.
- Everything here is behavior-preserving refactor except routing — low product risk, high leverage.
