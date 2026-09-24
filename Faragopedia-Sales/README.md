# Faragopedia-Sales (LLM Wiki)

A self-maintaining personal knowledge base that uses AI to organize, link, and synthesize information in a persistent Markdown wiki.

> 🟡 **Status: Prototype Complete** — A functional MVP with a React frontend and FastAPI backend is ready for evaluation.

## Overview

Faragopedia-Sales implements the **LLM Wiki** methodology. Unlike traditional RAG systems that re-discover knowledge on every query, this app builds and maintains a structured collection of Markdown files (`index.md`, `log.md`, and entity pages) that compound in value over time.

### Key Features
- **AI-Driven Ingestion**: Upload documents and the AI automatically creates/updates entity pages and maintains cross-references.
- **Persistent Wiki**: Your knowledge is stored as standard Markdown files, making it completely portable.
- **Multi-Provider Support**: Switch between OpenAI, Anthropic, Gemini, and OpenRouter via environment configuration.
- **Interactive Chat**: Ask questions directly to your wiki and receive synthesized answers with citations.
- **Link View**: See the whole wiki's crosslink structure at once — pages grouped by entity type, hover to trace connections, click to read any page in a side panel, and search by page content.
- **Health Check**: Automatically identify orphan pages and broken links to keep your vault clean.

## Getting Started

Detailed setup and deployment instructions can be found in the [Deployment Guide](docs/deployment.md).

### Prerequisites
- [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/)
- An API Key for one of the supported providers (OpenAI, Anthropic, Google, or OpenRouter)

### Setup & Run

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/accountantwise/Faragopedia-Sales.git
    cd Faragopedia-Sales
    ```

2.  **Configure Environment**:
    Rename `.env.example` to `.env` and add your API keys and preferred model:
    ```bash
    cp .env.example .env
    # Edit .env to set AI_PROVIDER, AI_MODEL, and your API keys
    ```

3.  **Start the Application**:
    ```bash
    docker-compose up --build
    ```

4.  **Access the Prototype**:
    - **Web UI**: [http://localhost:5173](http://localhost:5173)
    - **API Docs**: [http://localhost:8300/docs](http://localhost:8300/docs)

## Project Structure
- `backend/`: FastAPI application containing the `WikiManager` agent.
- `frontend/`: React application (Vite + Tailwind CSS).
- `sources/`: Directory for your raw source documents.
- `wiki/`: Your persistent Markdown knowledge base.

## AI Collaboration
This project is designed for AI-assisted development using a shared-context model.
- See [`AGENTS.md`](AGENTS.md) for the single source of truth for all agents.
- See [`docs/status.md`](docs/status.md) for the detailed living project status.

## License
TBD
