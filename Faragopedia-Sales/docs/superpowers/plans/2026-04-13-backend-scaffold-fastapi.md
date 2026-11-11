# Backend Scaffold (FastAPI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up the core FastAPI application with routes for file upload and AI chat, following TDD.

**Architecture:** A standard FastAPI structure with modular routing. `api/routes.py` will handle requests, interacting with the filesystem (`sources/`) for file persistence.

**Tech Stack:** FastAPI, Pydantic, pytest, httpx (for testing), python-multipart (for file uploads).

---

### Task 1: API Test Setup

**Files:**
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: Write initial failing tests for upload and chat**

```python
from fastapi.testclient import TestClient
from backend.main import app
import os
import shutil

client = TestClient(app)

def test_upload_file():
    # Ensure sources directory exists for test (normally handled by app)
    if not os.path.exists("../sources"):
        os.makedirs("../sources")
    
    filename = "test.txt"
    content = b"hello world"
    files = {"file": (filename, content, "text/plain")}
    
    response = client.post("/api/upload", files=files)
    
    assert response.status_code == 200
    assert response.json() == {"filename": filename, "message": "File uploaded successfully"}
    assert os.path.exists(f"../sources/{filename}")
    
    # Cleanup
    if os.path.exists(f"../sources/{filename}"):
        os.remove(f"../sources/{filename}")

def test_chat_query():
    query = "What is Faragopedia?"
    response = client.post(f"/api/chat?query={query}")
    
    assert response.status_code == 200
    assert "response" in response.json()
    assert response.json()["response"] == f"Echo: {query}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_api.py -v` (Note: Need to install `pytest` and `httpx` if not present)
Expected: FAIL with 404 Not Found for both endpoints.

- [ ] **Step 3: Commit initial test**

```bash
git add backend/tests/test_api.py
git commit -m "test(backend): add initial tests for upload and chat endpoints"
```

### Task 2: Implement API Routes

**Files:**
- Create: `backend/api/routes.py`
- Create: `backend/api/__init__.py`

- [ ] **Step 1: Create `backend/api/routes.py` with basic implementation**

```python
from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import shutil

router = APIRouter()

# In container, sources is at ../sources. If local dev, it might be ./sources.
# We'll use a configurable path or check relative to this file.
SOURCES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sources"))

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not os.path.exists(SOURCES_DIR):
        # Basic error handling: if sources/ is missing, try to create it
        try:
            os.makedirs(SOURCES_DIR)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not create sources directory: {str(e)}")
    
    file_path = os.path.join(SOURCES_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return {"filename": file.filename, "message": "File uploaded successfully"}

@router.post("/chat")
async def chat(query: str):
    return {"response": f"Echo: {query}"}
```

- [ ] **Step 2: Commit API routes**

```bash
git add backend/api/routes.py backend/api/__init__.py
git commit -m "feat(backend): implement upload and chat routes"
```

### Task 3: Integrate Router and CORS

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Update `backend/main.py` to include the router and CORS**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router as api_router

app = FastAPI()

# CORS configuration
origins = [
    "http://localhost:5173",  # React frontend
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Hello World from FastAPI"}
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest backend/tests/test_api.py -v`
Expected: PASS

- [ ] **Step 3: Commit integration**

```bash
git add backend/main.py
git commit -m "feat(backend): add upload and chat routes with basic CORS"
```

### Task 4: Final Verification and Self-Review

- [ ] **Step 1: Run all tests in the backend**

Run: `pytest backend/tests`
Expected: All tests pass.

- [ ] **Step 2: Self-review and update status**

- Ensure all requirements from Task 2 are met.
- Update `docs/status.md`.
