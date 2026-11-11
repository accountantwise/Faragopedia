# Final Polish & Persistent Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finalize the LLM Wiki webapp by ensuring persistent storage, adding health check logic, and polishing the frontend UI with markdown rendering and navigation.

**Architecture:** Extend WikiManager with health check logic, add API endpoints for health and page management, and update React frontend to render markdown and navigate wiki pages.

**Tech Stack:** FastAPI, Pydantic, React (Vite), TailwindCSS, react-markdown.

---

### Task 1: WikiManager - Health Check & Page Listing

**Files:**
- Modify: `backend/agent/wiki_manager.py`
- Test: `backend/tests/test_wiki_manager_health.py`

- [ ] **Step 1: Write the failing test for health_check and list_pages**

```python
import pytest
import os
from agent.wiki_manager import WikiManager

@pytest.fixture
def wiki_manager(tmp_path):
    sources = tmp_path / "sources"
    wiki = tmp_path / "wiki"
    sources.mkdir()
    wiki.mkdir()
    return WikiManager(sources_dir=str(sources), wiki_dir=str(wiki))

def test_health_check_empty(wiki_manager):
    report = wiki_manager.health_check()
    assert report["orphan_pages"] == []
    assert report["missing_pages"] == []

def test_health_check_with_issues(wiki_manager):
    # Create orphan page
    with open(os.path.join(wiki_manager.wiki_dir, "orphan.md"), "w") as f:
        f.write("# Orphan\nNo links here.")
    
    # Create index with missing page
    with open(os.path.join(wiki_manager.wiki_dir, "index.md"), "w") as f:
        f.write("# Index\n- [[missing]]: Missing page")
        
    report = wiki_manager.health_check()
    assert "orphan.md" in report["orphan_pages"]
    assert "missing" in report["missing_pages"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_wiki_manager_health.py`
Expected: FAIL (methods not found)

- [ ] **Step 3: Implement health_check and helper methods**

Modify `backend/agent/wiki_manager.py`:
- Add `health_check()`
- Add `list_pages()`
- Add `get_page_content(filename)`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_wiki_manager_health.py`

- [ ] **Step 5: Commit**

```bash
git add backend/agent/wiki_manager.py
git commit -m "feat: implement wiki health check and page listing in WikiManager"
```

---

### Task 2: Backend API - Health Check & Page Routes

**Files:**
- Modify: `backend/api/routes.py`
- Test: `backend/tests/test_api_health.py`

- [ ] **Step 1: Write failing tests for new routes**

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement GET /api/health, GET /api/pages, GET /api/pages/{filename}**

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes.py
git commit -m "feat: add health check and page routes to API"
```

---

### Task 3: Frontend - Install dependencies & Basic Navigation

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/WikiView.tsx`

- [ ] **Step 1: Install frontend dependencies**

Run: `npm install react-markdown lucide-react` (in frontend dir)

- [ ] **Step 2: Create WikiView component**

- [ ] **Step 3: Update App.tsx to use WikiView and handle navigation**

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: add WikiView with markdown rendering and basic navigation"
```

---

### Task 4: Frontend - Health Check UI

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add Health Check button to Sidebar**

- [ ] **Step 2: Implement Health Check modal/alert in App.tsx**

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat: add health check UI to frontend"
```

---

### Task 5: Final Verification & Persistent Storage Check

- [ ] **Step 1: Verify docker-compose.yml volumes** (already checked, looks good)
- [ ] **Step 2: Verify .gitkeep files** (already checked, looks good)
- [ ] **Step 3: Final manual-style verification of integration**
- [ ] **Step 4: Final Commit**

```bash
git commit --allow-empty -m "feat: add wiki health check and markdown rendering UI"
```
