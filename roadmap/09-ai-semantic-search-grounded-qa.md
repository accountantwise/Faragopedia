# 09 — AI Upgrade: Semantic Search, Grounded Q&A & Autolinking

| Field | Value |
| --- | --- |
| Priority | P1 — Faragopedia's core differentiator; keyword search is now dated |
| Effort | M–L (2–4 sessions) |
| Dependencies | 05 (cost tracking makes embedding/query spend visible); benefits from 03 |
| Repo | `Faragopedia-Sales` |
| Branches touched | new `feature/semantic-search` |
| Review status | **UPGRADED & APPROVED** 2026-07-07 — the "chat stuffs the whole wiki into the prompt" claim corrected against code (chat is a 2-pass catalog-relevance flow; **lint** is the whole-wiki path); sqlite-vec verified actively maintained and kept, behind a thin store interface with a numpy fallback; embedding made async off the save path; local-model tradeoff stated honestly. See `00-review-log.md`. |

## Problem

Search today is a **client-side keyword index** (verified: `GET /search/index` at routes.py:919-928 ships title/path/tags/frontmatter/500-char preview — built at wiki_manager.py:306-313 — and WikiView filters it synchronously in the browser). Chat (`WikiManager.query`) is better than the original draft claimed — **verified 2-pass flow**: an LLM relevance call over the full page *catalog* picks 3-5 pages (wiki_manager.py:813-817), then `_run_query_llm` answers from those pages' full content (:847). But it still scales with wiki size (the catalog and whole pages go through the LLM), grounding is page-coarse with **no citations**, and a paraphrased search query misses. **Lint is the true whole-wiki-in-prompt path** (`_run_lint_llm(wiki_content)` takes the entire wiki). In 2025-2026 every competitor ships semantic search + grounded AI answers (Notion AI, Docmost, Slite "Ask"). Keyword-only search is a competitive liability.

## Design

### Embeddings + vector store

- On every page write/ingest, chunk the page (by heading/paragraph, ~500–1000 tokens with overlap) and embed each chunk. Store vectors + metadata (workspace, page_path, chunk text, heading) locally.
- **Store: a thin interface (`VectorStore` protocol: upsert/delete/query) with `sqlite-vec` as the default backend** — verified actively maintained (Mozilla Builders) and it keeps the single-file, no-extra-service ethos already chosen in 03. Because the interface is thin, ship a **numpy brute-force fallback backend** (vectors in a plain SQLite blob table, cosine in-process) in the same PR — it's ~50 lines, removes the native-extension dependency as a deploy risk, and at this corpus size (thousands of chunks, not millions) is indistinguishable in latency. LanceDB is the named escape hatch if the corpus ever outgrows both; note all three in the ADR.
- **Embedding model:** provider-agnostic to match the existing multi-provider factory (`_init_llm` per-operation env pattern, verified wiki_manager.py:217-236). Default: a hosted embedding API (e.g. OpenAI `text-embedding-3-small` — cheap, strong) via `EMBED_PROVIDER`/`EMBED_MODEL`. A local `sentence-transformers` model is the zero-marginal-cost option **but be honest about the tradeoff**: it adds ~1-2 GB to the image and meaningful RAM — offer it as a config option, not the default.
- **Don't block saves on embedding:** page save currently returns after an LLM tag-suggestion call already; adding synchronous embedding compounds latency and couples save success to an external API. Enqueue (asyncio task + in-process queue) with a "stale index" marker; the existing `asyncio.Lock` (verified :188) serializes the writes themselves; embedding retries on failure and `reindex` (below) is the recovery path.

### Retrieval + semantic search endpoint

- `POST /api/search/semantic` — embed the query, top-k vector search (filtered by workspace — per-page permission filtering only matters once 04's phase-2 page ACLs exist; workspace scoping is the real boundary in v1), return ranked chunks with page links and snippets.
- **Hybrid search:** combine semantic (vector) with the existing keyword index via reciprocal-rank fusion. Hybrid beats pure-vector for exact terms/names — important for an entity wiki full of proper nouns. (The keyword side can stay the existing server-built index, matched server-side in this endpoint.)
- Frontend search (WikiView + LinkView) becomes hybrid by default with ranked results + snippets. (Note: WikiView search already shows a result count — verified WikiView.tsx:1025 — the original draft claimed it didn't; LinkView shows "N of M" too.)

### Grounded Q&A (RAG) — upgrade chat

- Replace the LLM relevance pass with **retrieve-then-answer**: embed the question → retrieve top-k chunks (workspace-scoped) → answer citing them. Return **inline citations** (which pages/chunks the answer used) so users can verify — the trust feature competitors emphasize.
- Why this wins over the current 2-pass design: the relevance pass costs tokens proportional to the catalog on *every* question and returns whole pages; retrieval costs one cheap embedding call and returns focused chunks. Log both embedding and answer usage to 05's `llm_usage`.
- Keep the existing Anthropic prompt-caching (verified `_supports_cache_control` + `cache_control` blocks, wiki_manager.py:619-656) where it still applies (system prompt).
- **Lint gets the same treatment later** (retrieve relevant pages per finding category instead of whole-wiki) — flag as a follow-on inside this doc, not v1.

### Autolinking (differentiator, phase 2 in this doc)

- On save/ingest, suggest `[[wikilinks]]` by finding existing entity pages whose titles/aliases appear in the new text (string match + embedding similarity for fuzzy matches). Present as **suggestions the user accepts**, not auto-applied — matching the verified actionable-lint pattern (lint findings → user selects → `POST /lint/fix`).

### Backend

- `backend/agent/embeddings.py`: chunker, embed function (provider factory), `VectorStore` interface + sqlite-vec and numpy backends.
- Hook embedding upsert (queued) into `save_page_content`, ingest writes, `move_page`, `rename_page` (metadata update), lint-fix writes; delete vectors on page delete/archive. These are the same write paths 07 hooks for revisions — coordinate so both hooks live in one place.
- Routes: `POST /api/search/semantic`, upgrade `POST /api/chat` to RAG (return `citations`), `POST /api/pages/{path}/suggest-links` (phase 2).
- `POST /api/admin/reindex` (admin, 05) to backfill embeddings for an existing wiki and after model changes; also the recovery path for queue failures.

### Frontend

- Hybrid search results panel with snippets + ranking.
- Chat answers render inline citations (clickable → deep-link via 06).
- Link suggestions surfaced in the editor/lint flow (phase 2).

## Implementation plan (TDD)

1. **Embeddings module** — chunker + provider-agnostic embed + `VectorStore` with both backends. Tests: chunking boundaries; upsert/query returns nearest chunk for a known query (deterministic fake embedder); both backends pass the same suite.
2. **Index lifecycle hooks** — queued upsert on write/ingest/move/rename/lint-fix, delete on remove; stale-marker + retry. Tests: after save, chunk becomes queryable; after delete, gone; save succeeds even when the embedder is down.
3. **Semantic + hybrid search route** with workspace filtering (RRF fusion). Tests: semantic finds a paraphrase keyword misses; hybrid ranks exact-name hits high; other-workspace results excluded.
4. **RAG chat** — retrieve-then-answer with citations; usage logged to 05 (embedding + answer rows). Tests: answer cites the seeded relevant page; irrelevant pages not cited (fake LLM).
5. **Admin reindex** endpoint + progress. Test: reindex populates vectors for all pages.
6. **Frontend** hybrid results + citations UI. Verify with webapp-testing: paraphrased query surfaces the right page; chat answer cites sources that deep-link.
7. **(Phase 2)** autolink suggestions in editor/lint; lint retrieval refactor.

## Acceptance criteria

- A query phrased differently from the page's wording still finds it (semantic win over the keyword index).
- Saving a page never fails or slows because the embedding provider is down.
- Chat answers cite the specific pages used, and citations deep-link to them; chat token spend drops vs the catalog-relevance baseline for a comparable wiki (verify in 05's usage tab).
- Results never include pages from another workspace.
- Reindex rebuilds the vector store for an existing wiki, on either backend.

## Out of scope

- Cross-tool "enterprise search" over Slack/Jira/etc. — wiki-scoped only.
- Fine-tuning; retrieval quality tuning beyond hybrid + sensible chunking.
- Per-page-ACL filtering of results (needs 04 phase 2; workspace scoping covers v1).
