# Backend Scaffold (FastAPI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up the core FastAPI application with routes for file upload and AI chat.

**Architecture:** Use `APIRouter` for modularity. Files will be saved to a `sources/` directory.

**Tech Stack:** Python, FastAPI, python-multipart.

---

### Task 1: Implement API Routes

**Files:**
- Create: `backend/api/routes.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create backend/api/routes.py**

```python
from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import shutil

router = APIRouter()

# The 'sources/' directory is at '../sources' from 'backend/' if running inside the container,
# or './sources' from the root.
# Let's use a path relative to the current file to be safe.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCES_DIR = os.path.join(BASE_DIR, "sources")

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not os.path.exists(SOURCES_DIR):
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

- [ ] **Step 2: Update backend/main.py to include router and CORS**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router as api_router

app = FastAPI()

# Set up CORS
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

- [ ] **Step 3: Run tests to verify implementation**

Run: `python -m pytest backend/tests/test_api.py`
Expected: PASS

- [ ] **Step 4: Commit changes**

```bash
git add backend/api/routes.py backend/main.py
git commit -m "feat(backend): add upload and chat routes with basic CORS"
```

### Task 2: Final Verification

- [ ] **Step 1: Check sources directory**
Verify that a test file was created in `sources/` during the test and was cleaned up (or just check the directory exists).

- [ ] **Step 2: Self-review**
Ensure error handling is adequate and paths are correct.
