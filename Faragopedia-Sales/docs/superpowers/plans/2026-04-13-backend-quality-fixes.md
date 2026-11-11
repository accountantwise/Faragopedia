# Backend Quality Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix security, Docker compatibility, and package structure issues in the backend.

**Architecture:** 
- Sanitize filenames to prevent path traversal.
- Adjust imports for Docker compatibility.
- Standardize Python package structure with `__init__.py` files.
- Update test dependencies.

**Tech Stack:** FastAPI, Pytest, HTTPX

---

### Task 1: Package Structure and Requirements

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/api/__init__.py`
- Create: `backend/tests/__init__.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Create `__init__.py` files**

Create empty files at:
- `backend/__init__.py`
- `backend/api/__init__.py`
- `backend/tests/__init__.py`

- [ ] **Step 2: Update `backend/requirements.txt`**

Add `pytest` and `httpx` to `backend/requirements.txt`.

- [ ] **Step 3: Commit**

```bash
git add backend/__init__.py backend/api/__init__.py backend/tests/__init__.py backend/requirements.txt
git commit -m "chore(backend): add missing __init__.py files and update requirements"
```

### Task 2: Docker Compatibility - Fix Imports

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Fix import in `backend/main.py`**

Change `from backend.api.routes import router as api_router` to `from api.routes import router as api_router`.

- [ ] **Step 2: Commit**

```bash
git add backend/main.py
git commit -m "fix(backend): adjust imports for Docker compatibility"
```

### Task 3: Security - Filename Sanitization

**Files:**
- Modify: `backend/api/routes.py`

- [ ] **Step 1: Implement filename sanitization**

Update `backend/api/routes.py` to sanitize `file.filename`.

```python
import re

def secure_filename(filename: str) -> str:
    filename = os.path.basename(filename)
    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    return filename
```

Use this function in `upload_file`.

- [ ] **Step 2: Commit**

```bash
git add backend/api/routes.py
git commit -m "fix(backend): sanitize filenames to prevent path traversal"
```

### Task 4: Verification

**Files:**
- Run: `backend/tests/test_api.py`

- [ ] **Step 1: Run tests**

Run: `pytest tests/test_api.py` from the `backend/` directory.

- [ ] **Step 2: Verify all tests pass**

- [ ] **Step 3: Final Commit (if any changes were needed during verification)**

---
