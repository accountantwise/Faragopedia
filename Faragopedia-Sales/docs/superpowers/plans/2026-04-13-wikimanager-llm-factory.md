# Task 2: Implement LLM Factory in WikiManager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor 'WikiManager' to dynamically initialize the LLM provider based on environment variables.

**Architecture:** Implement a private `_init_llm` method that reads `AI_PROVIDER` and `AI_MODEL` from environment variables and returns the appropriate LangChain chat model instance.

**Tech Stack:** Python, FastAPI, LangChain (OpenAI, Anthropic, Google Generative AI).

---

### Task 1: Create tests for LLM Factory

**Files:**
- Create: `backend/tests/test_wiki_manager_factory.py`

- [ ] **Step 1: Write tests to verify LLM initialization based on environment variables**

```python
import os
import pytest
from unittest.mock import patch
from backend.agent.wiki_manager import WikiManager
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

def test_init_llm_openai():
    with patch.dict(os.environ, {"AI_PROVIDER": "openai", "AI_MODEL": "gpt-4o-mini"}):
        wm = WikiManager()
        assert isinstance(wm.llm, ChatOpenAI)
        assert wm.llm.model_name == "gpt-4o-mini"

def test_init_llm_anthropic():
    with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "AI_MODEL": "claude-3-5-sonnet-20240620"}):
        wm = WikiManager()
        assert isinstance(wm.llm, ChatAnthropic)
        assert wm.llm.model == "claude-3-5-sonnet-20240620"

def test_init_llm_google():
    with patch.dict(os.environ, {"AI_PROVIDER": "google", "AI_MODEL": "gemini-1.5-pro"}):
        wm = WikiManager()
        assert isinstance(wm.llm, ChatGoogleGenerativeAI)
        assert wm.llm.model == "gemini-1.5-pro"

def test_init_llm_openrouter():
    with patch.dict(os.environ, {"AI_PROVIDER": "openrouter", "AI_MODEL": "meta-llama/llama-3-70b-instruct", "OPENROUTER_API_KEY": "test_key"}):
        wm = WikiManager()
        assert isinstance(wm.llm, ChatOpenAI)
        assert wm.llm.openai_api_base == "https://openrouter.ai/api/v1"
        assert wm.llm.model_name == "meta-llama/llama-3-70b-instruct"

def test_init_llm_invalid():
    with patch.dict(os.environ, {"AI_PROVIDER": "invalid"}):
        with pytest.raises(ValueError, match="Unsupported AI provider: invalid"):
            WikiManager()

def test_init_llm_default():
    with patch.dict(os.environ, {}, clear=True):
        # We need to ensure at least some env vars are NOT there if they are set in the environment
        if "AI_PROVIDER" in os.environ: del os.environ["AI_PROVIDER"]
        if "AI_MODEL" in os.environ: del os.environ["AI_MODEL"]
        wm = WikiManager()
        assert isinstance(wm.llm, ChatOpenAI)
        assert wm.llm.model_name == "gpt-4o-mini"
```

- [ ] **Step 2: Run tests and verify they fail (because imports are missing and logic is not yet implemented)**

Run: `pytest backend/tests/test_wiki_manager_factory.py`
Expected: FAIL (ImportError or AttributeError)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_wiki_manager_factory.py
git commit -m "test(agent): add tests for dynamic LLM provider switching"
```

---

### Task 2: Implement LLM Factory in WikiManager

**Files:**
- Modify: `backend/agent/wiki_manager.py`

- [ ] **Step 1: Update imports and implement `_init_llm`**

```python
import os
# ... existing imports ...
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
# ... existing imports ...

class WikiManager:
    def __init__(self, sources_dir="sources", wiki_dir="wiki"):
        self.sources_dir = sources_dir
        self.wiki_dir = wiki_dir
        # Initialize LLM based on environment variables
        self.llm = self._init_llm()
        
        # ... existing directory setup ...

    def _init_llm(self):
        provider = os.getenv("AI_PROVIDER", "openai").lower()
        model = os.getenv("AI_MODEL", "gpt-4o-mini")
        
        if provider == "openai":
            return ChatOpenAI(model=model)
        elif provider == "anthropic":
            return ChatAnthropic(model=model)
        elif provider == "google":
            return ChatGoogleGenerativeAI(model=model)
        elif provider == "openrouter":
            return ChatOpenAI(
                model=model,
                openai_api_base="https://openrouter.ai/api/v1",
                openai_api_key=os.getenv("OPENROUTER_API_KEY")
            )
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")

    # ... rest of the class ...
```

- [ ] **Step 2: Run tests to verify implementation**

Run: `pytest backend/tests/test_wiki_manager_factory.py`
Expected: PASS

- [ ] **Step 3: Run existing tests to ensure no regressions**

Run: `pytest backend/tests/test_wiki_manager.py`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/agent/wiki_manager.py
git commit -m "feat(agent): implement dynamic LLM provider switching"
```

---

### Task 3: Final Verification and Documentation

- [ ] **Step 1: Final test run**

Run: `pytest backend/tests/`
Expected: All tests pass.

- [ ] **Step 2: Update `docs/status.md`**

Add entry for Task 2 completion.

- [ ] **Step 3: Commit**

```bash
git add docs/status.md
git commit -m "docs: update status for Task 2"
```
