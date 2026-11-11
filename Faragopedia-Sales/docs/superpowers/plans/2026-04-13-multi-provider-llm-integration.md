# Multi-Provider LLM Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement environment-based switching for multiple AI providers (Anthropic, Gemini, OpenAI, OpenRouter) in the `WikiManager`.

**Architecture:** Refactor `WikiManager` initialization into a factory pattern that instantiates the correct LangChain chat model based on `AI_PROVIDER` and `AI_MODEL` environment variables.

**Tech Stack:** Python, FastAPI, LangChain (ChatOpenAI, ChatAnthropic, ChatGoogleGenerativeAI).

---

### Task 1: Environment & Dependency Setup

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add provider-specific LangChain packages to requirements**
```text
langchain-openai
langchain-anthropic
langchain-google-genai
```

- [ ] **Step 2: Update .env.example with provider variables**
```text
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
```

- [ ] **Step 3: Commit setup**
```bash
git add backend/requirements.txt .env.example
git commit -m "chore: add multi-provider dependencies and env template"
```

### Task 2: Implement LLM Factory in WikiManager

**Files:**
- Modify: `backend/agent/wiki_manager.py`

- [ ] **Step 1: Add new imports to wiki_manager.py**
```python
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
```

- [ ] **Step 2: Implement private `_init_llm` method**
```python
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
```

- [ ] **Step 3: Update `__init__` to use the new factory**
```python
def __init__(self, sources_dir="sources", wiki_dir="wiki"):
    self.sources_dir = sources_dir
    self.wiki_dir = wiki_dir
    self.llm = self._init_llm()
    # ... rest of init
```

### Task 3: Verification & Test Updates

**Files:**
- Modify: `backend/tests/test_wiki_manager.py`

- [ ] **Step 1: Update tests to verify factory initialization logic**
- [ ] **Step 2: Ensure existing mocks in API tests still work**
- [ ] **Step 3: Commit implementation**
```bash
git add backend/agent/wiki_manager.py backend/tests/test_wiki_manager.py
git commit -m "feat(agent): implement dynamic LLM provider switching"
```
