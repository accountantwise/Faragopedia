# Finalize API Test Mocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update backend dependencies and implement robust mocks for `WikiManager` in API tests to ensure project stability.

**Architecture:** Use `unittest.mock.patch` to isolate API routes from the actual `WikiManager` implementation, which relies on external LLM services.

**Tech Stack:** Python, FastAPI, Pytest, unittest.mock, LangChain.

---

### Task 1: Update Dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add missing LangChain dependencies**

Add `langchain-core` and `langchain-community` to `backend/requirements.txt`.

```text
fastapi
uvicorn
python-multipart
langchain
langchain-core
langchain-community
langchain-openai
python-dotenv
pytest
httpx
```

- [ ] **Step 2: Verify requirements.txt**

Run: `cat backend/requirements.txt`
Expected: All dependencies are present.

### Task 2: Mock WikiManager in API Tests

**Files:**
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Update test_upload_file to mock ingest_source**

Update `test_upload_file` to use `unittest.mock.patch` on `backend.api.routes.wiki_manager.ingest_source`. Ensure it verifies the call and matches the actual response from `routes.py`.

```python
from unittest.mock import patch, MagicMock, AsyncMock

@patch("backend.api.routes.wiki_manager.ingest_source", new_callable=AsyncMock)
def test_upload_file(mock_ingest):
    # In this test environment, sources is at ./sources from project root
    sources_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sources"))
    if not os.path.exists(sources_dir):
        os.makedirs(sources_dir)
    
    filename = "test_upload.txt"
    content = b"hello world"
    files = {"file": (filename, content, "text/plain")}
    
    response = client.post("/api/upload", files=files)
    
    assert response.status_code == 200
    assert response.json() == {"filename": filename, "message": "File uploaded and ingestion started"}
    
    # Verify ingest_source was called
    mock_ingest.assert_called_once_with(filename)
    
    file_path = os.path.join(sources_dir, filename)
    assert os.path.exists(file_path)
    
    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)
```

- [ ] **Step 2: Update test_chat_query to mock query**

Update `test_chat_query` to use `unittest.mock.patch` on `backend.api.routes.wiki_manager.query`. Ensure it returns a mock response and verifies the call.

```python
@patch("backend.api.routes.wiki_manager.query", new_callable=AsyncMock)
def test_chat_query(mock_query):
    mock_query.return_value = "Mocked LLM Response"
    query = "What is Faragopedia?"
    response = client.post(f"/api/chat?query={query}")
    
    assert response.status_code == 200
    assert response.json() == {"response": "Mocked LLM Response"}
    mock_query.assert_called_once_with(query)
```

- [ ] **Step 3: Update other tests for consistency**

Ensure all tests in `test_api.py` are consistent with the `routes.py` implementation.

### Task 3: Verification and Commitment

- [ ] **Step 1: Run API tests**

Run: `python -m pytest backend/tests/test_api.py`
Expected: All tests pass.

- [ ] **Step 2: Run WikiManager tests**

Run: `python -m pytest backend/tests/test_wiki_manager.py`
Expected: All tests pass.

- [ ] **Step 3: Commit changes**

Run: `git add backend/requirements.txt backend/tests/test_api.py`
Run: `git commit -m "test(backend): finalize API test mocks for WikiManager integration"`
