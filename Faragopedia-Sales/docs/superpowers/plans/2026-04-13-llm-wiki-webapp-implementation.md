# LLM Wiki Webapp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a functional prototype of the LLM Wiki webapp with a React frontend and a Python FastAPI backend, capable of ingesting documents and managing a persistent markdown wiki.

**Architecture:** A decoupled client-server architecture. The FastAPI backend handles the LLM agent logic and file system operations on the `sources/` and `wiki/` directories. The React frontend provides a user-friendly interface for browsing the wiki and interacting with the AI.

**Tech Stack:** React (Vite), TypeScript, Tailwind CSS, Python, FastAPI, LangChain/LangGraph, Docker.

---

### Task 1: Project Structure & Docker Setup

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/requirements.txt`
- Create: `frontend/Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create Backend requirements.txt**
```text
fastapi
uvicorn
python-multipart
langchain
langchain-openai
python-dotenv
```

- [ ] **Step 2: Create Docker Compose for development**
```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    volumes:
      - ./backend:/app
      - ./sources:/app/sources
      - ./wiki:/app/wiki
    ports:
      - "8000:8000"
    env_file: .env
  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
```

- [ ] **Step 3: Commit setup**
```bash
git add backend/requirements.txt docker-compose.yml
git commit -m "chore: initial docker setup and requirements"
```

### Task 2: Backend Scaffold (FastAPI)

**Files:**
- Create: `backend/main.py`
- Create: `backend/api/routes.py`

- [ ] **Step 1: Create basic FastAPI app**
```python
from fastapi import FastAPI
from backend.api.routes import router

app = FastAPI(title="LLM Wiki API")
app.include_router(router)

@app.get("/")
def read_root():
    return {"message": "LLM Wiki API is running"}
```

- [ ] **Step 2: Define basic routes for File Upload and Chat**
```python
from fastapi import APIRouter, UploadFile, File

router = APIRouter()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Save file to sources/
    return {"filename": file.filename}

@router.post("/chat")
async def chat(query: str):
    # LLM logic here
    return {"response": "I am your wiki agent."}
```

### Task 3: Frontend Scaffold (React + Vite)

**Files:**
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Set up basic Layout with Sidebar and Content Area**
```tsx
import React from 'react';
import Sidebar from './components/Sidebar';

function App() {
  return (
    <div className="flex h-screen bg-gray-100">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8">
        <h1 className="text-3xl font-bold">Your Wiki</h1>
        {/* Content Area */}
      </main>
    </div>
  );
}

export default App;
```

### Task 4: Agent Core - Ingest & Maintenance

**Files:**
- Create: `backend/agent/wiki_manager.py`

- [ ] **Step 1: Implement basic WikiManager with LangChain**
```python
class WikiManager:
    def __init__(self, wiki_dir: str):
        self.wiki_dir = wiki_dir
    
    def ingest_source(self, source_path: str):
        # Read source -> Summarize -> Update Wiki
        pass
```

- [ ] **Step 2: Write tests for WikiManager**
- [ ] **Step 3: Integrate WikiManager into /upload and /chat routes**

### Task 5: Final Polish & Persistent Storage

- [ ] **Step 1: Ensure `sources/` and `wiki/` volumes are correctly mounted and persistent.**
- [ ] **Step 2: Add 'Health Check' (Linting) logic to WikiManager.**
- [ ] **Step 3: Basic UI styling for markdown rendering in the frontend.**
