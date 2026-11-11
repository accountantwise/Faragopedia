# WikiManager Design Specification

**Goal:** Implement a centralized `WikiManager` to handle source ingestion, wiki maintenance, and knowledge retrieval using LangChain.

**Architecture:**
The `WikiManager` acts as the "brain" of the application, bridging the gap between raw source documents and a structured, interlinked markdown wiki.

**Components:**
1.  **Ingestion Service:**
    - Loads raw documents from the `sources/` directory.
    - Uses LangChain's `ChatOpenAI` to generate summaries and extract key entities/concepts.
    - Updates or creates individual markdown pages in the `wiki/` directory.
    - Automatically adds cross-references using the `[[Page Name]]` syntax.
2.  **Maintenance Service:**
    - Ensures `wiki/index.md` stays up-to-date with all current pages and their summaries.
    - Maintains a chronological `wiki/log.md` of all actions.
3.  **Query Service:**
    - Performs an initial "navigational" search by reading `wiki/index.md`.
    - Retrieves relevant pages to synthesize a detailed answer with citations.

**Data Flow:**
- **Ingestion:** Upload -> Save to `sources/` -> `WikiManager.ingest()` -> Extract Info -> Write to `wiki/` -> Update Index/Log.
- **Query:** User Question -> `WikiManager.query()` -> Read Index -> Identify Pages -> Synthesize Answer -> Return to User.

**Tech Stack:**
- LangChain for LLM orchestration.
- OpenAI GPT models.
- Standard Python file I/O for markdown management.

**File Conventions:**
- `wiki/index.md`: Content-oriented catalog of all pages.
- `wiki/log.md`: Chronological append-only record.
- Individual wiki pages: `[[Entity Name]].md` or `[[Concept Name]].md`.

**Testing Strategy:**
- Unit tests for `WikiManager` using a mock LLM.
- Integration tests to verify API endpoints `POST /upload` and `POST /chat` use `WikiManager` correctly.
