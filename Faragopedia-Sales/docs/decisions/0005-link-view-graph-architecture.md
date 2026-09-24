# ADR 0005: Link View Graph Architecture

**Date:** 2026-07-04
**Status:** Accepted

## Context

Backlog item 27 called for a graph view showing the whole wiki's crosslink
structure at once. The design (mockups in `Visualization Page Concept/` at the
repo root) is a grouped grid — pages as pill chips inside labeled sections per
entity type, with connection curves drawn on hover/focus — explicitly **not** a
physics-based force-directed graph.

Two data-access questions had to be settled:

1. The backend already exposed `GET /pages` and `GET /pages/{path}/backlinks`,
   but assembling a full graph client-side means one backlinks call per page,
   and `get_backlinks()` itself re-scans every wiki file per call — N pages
   would cost N full wiki scans (about 190,000 file reads at the production
   count of ~440 pages).
2. No graph/visualization library was installed, and the grouped-grid design
   doesn't need force simulation.

## Decision

1. **Single aggregate endpoint.** `GET /api/pages/graph`
   (`WikiManager.get_link_graph()`) builds the entire graph in **one pass**
   over the wiki: all nodes (id, title from frontmatter `name` with a
   de-slugged filename fallback, group = entity folder), deduplicated edges
   (`[[folder/page]]` wikilinks resolved from body **and** frontmatter; broken
   links, self-links, and duplicates dropped), and groups (entity types from
   `_type.yaml` — `name`/`description` become section title/subtitle). The
   route is registered **before** `GET /pages/{path:path}` so `graph` is not
   parsed as a page path.

2. **Hand-rolled SVG/CSS, no graph library.** Chips are normal DOM in a
   flex-wrap grid; connection curves are cubic béziers in an absolutely
   positioned SVG overlay, measured from chip `getBoundingClientRect()` and
   remeasured via a `ResizeObserver` on the map wrapper. Hover takes display
   priority over click-focus so hovering always responds.

3. **Content search reuses the existing client-side index.** The search bar
   filters the map using `GET /search/index` (title + path + tags +
   frontmatter values + 500-char content preview) — no new backend search
   endpoint. Edges, hover/focus, and the stats bar operate on the filtered
   subgraph.

4. **Cache-critical styling is inline.** The reading panel's open/close
   geometry (width, visibility, transition) lives in inline styles rather than
   Tailwind classes, because production serves CSS through Cloudflare's cache
   and a stale stylesheet missing a new-to-codebase class once left the closed
   panel covering the entire map (see `docs/deployment.md`, "Frontend Asset
   Caching Behind Cloudflare").

## Consequences

- Graph assembly is O(one wiki scan) per request and needs no cache layer at
  current scale (~440 pages, verified fast in production). If the wiki grows
  enough that per-request scanning hurts, add mtime-based caching inside
  `get_link_graph()` rather than reintroducing per-page calls.
- Node titles come from the same frontmatter `name` convention the search
  index uses, so the two stay consistent.
- Content search matches only the first 500 characters of each page body
  (the index's `content_preview` limit, shared with WikiView search). Widening
  it is a one-line change in `_rebuild_search_index()` if deep-page matching
  is ever needed.
- No new frontend dependencies; the view is one self-contained component
  (`frontend/src/components/LinkView.tsx`).
