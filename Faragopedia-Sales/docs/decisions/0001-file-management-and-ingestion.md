# ADR 0001: File Management & Manual Ingestion Control

**Date:** 2026-04-14
**Status:** Accepted

## Context
The initial prototype ingested all uploads immediately and lacked a way to manage (delete/archive) wiki pages or raw source files. As the wiki grew, users needed:
1. Control over when ingestion occurs (to avoid costs/token usage on every upload).
2. Status tracking for ingested files.
3. A "safety net" (Archive/Trash) to prevent accidental data loss.

## Decision
We implemented a comprehensive file management and metadata system:
1. **Archive Storage:** Created a top-level `archive/` directory to store "soft-deleted" files.
2. **Metadata Persistence:** Sources now have an associated metadata system to track ingestion status (`pending`, `ingested`, `error`).
3. **Manual Trigger:** Split the upload and ingestion processes. Ingestion can now be triggered manually via a dedicated endpoint.
4. **Permanent Deletion:** Added a two-step deletion process (Archive -> Permanent Delete).

## Consequences
*   **Safety:** Users can safely archive and restore both wiki pages and source files.
*   **Efficiency:** Prevents unnecessary LLM calls by allowing batch uploads with selective ingestion.
*   **Complexity:** The backend now manages more state (metadata and archive paths), but the UI is significantly more robust.
