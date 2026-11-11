# LLM Wiki Webapp - Architecture Design

## 1. Background & Motivation
The objective is to build a web application that implements the "LLM Wiki" methodology described in `methodology.md`. The application acts as a self-maintaining personal knowledge base. Instead of generating answers from scratch using retrieval-augmented generation (RAG) at query time, an LLM agent incrementally builds and maintains a persistent, interlinked wiki in markdown format.

## 2. Architecture & Components
We are adopting a decoupled client-server architecture to provide full UI control while maintaining robust AI capabilities.

### Backend (Python + FastAPI)
*   **API Layer:** Serves endpoints for file uploads, chat queries, and task triggers.
*   **Agent Engine:** Powered by LangChain or LangGraph to process logic, query models (OpenAI, Anthropic, or local models), and manage multi-step reasoning.
*   **File System Manager:** Interacts with the local file system (volumes in Docker) maintaining the separation of `sources/` sources and `wiki/` markdown files.

### Frontend (React + Vite)
*   **Wiki Viewer/Editor:** A markdown rendering engine with bidirectional link support (similar to Obsidian).
*   **Interaction Sidebar:** A hybrid interface offering both free-form chat for conversational queries and action buttons (Ingest, Health Check/Lint).

## 3. Data Flow & Agent Logic
*   **Upload & Ingest:**
    *   User uploads a source file (PDF, TXT, MD, etc.) via the UI into the `sources/` directory.
    *   A background task is triggered. The AI reads the source, updates `index.md`, extracts entities, updates/creates relevant `.md` files in `wiki/`, and appends the action to `log.md`.
*   **Query:**
    *   User asks a question via the chat UI.
    *   The agent reads `index.md`, retrieves relevant wiki pages, synthesizes an answer, and optionally creates a new synthesis markdown page to persist the insight.
*   **Lint (Health Check):**
    *   Triggered via a button. The agent scans the wiki for orphans, contradictions, or missing links, presenting suggestions in the UI.

## 4. The Master Schema Configuration
*   **Configurator UI:** A dedicated screen where a user provides a short prompt describing their specific goals. The application combines this prompt with the core rules from `methodology.md` to generate the `schema.md` (e.g., `AGENTS.md`).
*   **Schema Governance:** The generated `schema.md` dictates the focus and rules the LLM agent follows when maintaining the wiki.

## 5. Deployment
*   The application will run as a simple web-facing Docker container (e.g., via Docker Compose and Portainer).
*   Storage relies on persistent volumes bound to the local host, ensuring all markdown data remains portable and under user control.