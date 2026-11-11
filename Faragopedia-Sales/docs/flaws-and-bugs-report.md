# Faragopedia: Flaws and Bugs Report
**Date:** 2026-04-14
**Status:** MVP Features Implemented; Advanced Optimization Next

This report outlines the technical and functional status of Faragopedia-Sales based on the [LLM Wiki Methodology](../.assets/foundational_ideas/methodology.md) and industry standards (Obsidian, Logseq).

---

## 1. Resolved Issues (2026-04-14)

### 1.1 Non-Interactive `[[WikiLinks]]`
*   **Status:** ✅ FIXED.
*   **Implementation:** Custom renderer for `react-markdown` parses `[[...]]` and triggers `fetchPageContent`. Sanitization rules match the backend's `safe_wiki_filename`.

### 1.2 Ingestion Race Conditions
*   **Status:** ✅ FIXED.
*   **Implementation:** Added `asyncio.Lock` to `WikiManager`. `ingest_source` is split into two phases: LLM inference (concurrent) and file writing (serialized).

### 1.3 Missing Bidirectional Links (Backlinks)
*   **Status:** ✅ FIXED.
*   **Implementation:** Added `/api/pages/{filename}/backlinks` endpoint. Frontend displays inbound links at the bottom of `WikiView`.

### 1.4 Lack of Navigation History
*   **Status:** ✅ FIXED.
*   **Implementation:** Implemented a navigation stack for both Wiki and Sources views.

### 1.5 Read-Only UI
*   **Status:** ✅ FIXED.
*   **Implementation:** Added "Edit Page" capability with backend support for saving Markdown content.

### 1.6 File Management Gaps
*   **Status:** ✅ FIXED.
*   **Implementation:** Added New Page, Archive, Restore, Delete (permanent), and Download features for both Wiki pages and Sources.

### 1.7 Ingestion Control
*   **Status:** ✅ FIXED.
*   **Implementation:** Added manual ingestion control, status tracking, and metadata persistence for sources.

---

## 2. High Priority: Knowledge Management Gaps

### 2.1 Basic "Health Check" Optimization
*   **The Issue:** The current linting is purely structural (orphans/dead links).
*   **Impact:** Does not fulfill the methodology's goal of finding "contradictions" or "stale claims" across documents.
*   **Required Fix:** Implement a "Semantic Lint" feature that uses the LLM to verify content consistency.

### 2.2 Absence of Graph View
*   **The Issue:** No visual map of the knowledge base.
*   **Impact:** Harder to identify structural clusters or "island" concepts that need better integration.
*   **Required Fix:** Integrate a force-directed graph library (e.g., `react-force-graph`).

---

## 3. Low Priority: Architectural & Polish Flaws

### 3.1 Advanced AI Maintenance
*   **The Issue:** Scaling of background ingestion.
*   **Impact:** Large batches of files might slow down the system if not managed by a dedicated worker.
*   **Required Fix:** Consider moving from `asyncio.create_task` to a proper task queue (e.g., Celery/RQ) if the volume increases.

---

## Summary of Alignment
The current prototype successfully handles the **Ingest**, **Query**, and **Experience** layers. The wiki is now browsable, editable, and stable. Next steps focus on **Insight** (Graph View) and **Integrity** (Semantic Linting).
