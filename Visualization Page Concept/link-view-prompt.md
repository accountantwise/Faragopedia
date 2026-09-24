# Link View — Prompt for Claude Fable 5

I'm building Faragopedia, a self-hosted wiki app: Python/FastAPI backend, React + TypeScript + Vite frontend
(Tailwind for styling, no router — views switch via `currentView` state in `App.tsx`). Wiki pages are markdown
files with YAML frontmatter under `backend/wiki/<entity-folder>/<page>.md`, and they reference each other with
`[[subdir/page-name]]` wikilinks in the markdown body/frontmatter. This is backlog item 27 in `AGENTS.md`:
"Implement Graph View."

Right now the only way to see how pages relate is to open one page and scroll to its backlinks. I want a new
page — call it Link View — that shows the whole crosslink structure at once, the way Obsidian's graph view
does, but NOT as a physics-based force-directed graph. I've mocked up the exact visual style and interactions
I want in three screenshots at the repo root: `Visualization Page Concept/link-view-concept-1-overview.png`,
`-2-hover-highlight.png`, `-3-node-focus.png`. Look at all three before building anything. They show:

- Pages grouped into labeled sections (colored bullet + title + one-line subtitle), with pages as rounded
  pill/chip nodes wrapped in a grid inside each section — not scattered in open space.
- At rest, everything is visible at roughly equal visual weight.
- On hover over a node, unrelated nodes and section chrome dim, and curved lines draw from the hovered node
  to every node it links to, crossing section boundaries when relevant.
- On click, a node "focuses": everything else dims further, its connections draw in as thicker/brighter
  curves, and Escape or clicking the background resets to the rest state.
- A footer stats bar reports summary counts (e.g. "77 nodes · 298 connections") plus the Esc/reset hint.

For Faragopedia, sections should map to something meaningful in our actual data — the entity-folder/category
a page lives under, or its tags. Use your judgment on which grouping reads best given what's actually in
`backend/wiki/`. Connections are wikilinks between pages.

Data: the backend already has `GET /pages` (`wiki_manager.list_pages()`) and `GET /pages/{path}/backlinks`
(`wiki_manager.get_backlinks()` in `backend/agent/wiki_manager.py`, ~line 1467), both in `backend/api/routes.py`.
Calling backlinks per page to assemble a full graph is an N+1 pattern on top of a function that already scans
every page per call. Decide whether that's fine at our current page count or whether a single aggregate
endpoint (e.g. `GET /pages/graph`, returning all nodes + edges in one pass) is worth adding — your call.

No graph/visualization library is installed (`frontend/package.json` has none of d3, cytoscape, vis-network,
react-force-graph). The mockups are a grouped grid, not a force simulation, so a hand-rolled SVG/CSS layout is
probably enough — reach for a lightweight library only if hand-rolled positioning or curve-drawing genuinely
doesn't hold up.

Wire it up like the other views: add `LinkView.tsx` (or similar) to `frontend/src/components/`, following
the conventions in `WikiView.tsx`/`LintView.tsx` (TypeScript, Tailwind `dark:` variants, no CSS modules), add
a case to the `renderContent()` switch in `App.tsx`, and add a nav entry to the `navItems`-style array in
`Sidebar.tsx` (a `lucide-react` icon like `Network` or `Share2` fits the existing set).

Do this work on a new branch named exactly `link-view`, branched from the current branch — note if that
breaks from this repo's usual `feature/<desc>` naming, but use `link-view` as asked. Scope this to the
link-view feature only; don't refactor the other views or touch unrelated code. Proceed through reversible
implementation choices without checking in; ask only if something needs a decision only I can make.

Once it's built, run the frontend dev server and actually look at the page in a browser to confirm hover,
click-to-focus, and Escape/background reset all work, with a real (or realistic sample) set of wiki pages,
in both light and dark mode. Only tell me it's done once you've verified that yourself against real tool
output — if something doesn't render or is stubbed, say so plainly rather than reporting success.
