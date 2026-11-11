# Wiki-Concept Integration & Autonomous Agent Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Faragopedia-Sales into an IDE-like autonomous agent engine driven by the `Wiki-Concept` business rules.

**Architecture:** We will replace the current extraction logic with a LangChain ReAct agent. The backend will serve as an orchestrator that provides the LLM with a "Toolbelt" for local filesystem access, strictly governed by the rules in `SCHEMA.md`.

**Tech Stack:** Python/FastAPI, LangChain, OpenRouter (Claude 3.5 Sonnet), React.

---

### Task 1: Data Consolidation & Storage Refactor

**Files:**
- Modify: `backend/agent/wiki_manager.py`
- Modify: `backend/api/routes.py`
- Run: Shell commands for migration

- [ ] **Step 1: Migrate Wiki-Concept files to the app's wiki directory**

Run:
```powershell
# Create the target directory structure
mkdir -p Faragopedia-Sales/wiki/clients
mkdir -p Faragopedia-Sales/wiki/contacts
mkdir -p Faragopedia-Sales/wiki/photographers
mkdir -p Faragopedia-Sales/wiki/productions
mkdir -p Faragopedia-Sales/wiki/prospects
mkdir -p Faragopedia-Sales/wiki/sources/assets

# Copy the content from Wiki-Concept
cp Wiki-Concept/*.md Faragopedia-Sales/wiki/
cp -r Wiki-Concept/clients/* Faragopedia-Sales/wiki/clients/
cp -r Wiki-Concept/contacts/* Faragopedia-Sales/wiki/contacts/
cp -r Wiki-Concept/photographers/* Faragopedia-Sales/wiki/photographers/
cp -r Wiki-Concept/productions/* Faragopedia-Sales/wiki/productions/
cp -r Wiki-Concept/prospects/* Faragopedia-Sales/wiki/prospects/
cp -r Wiki-Concept/sources/assets/* Faragopedia-Sales/wiki/sources/assets/
```

- [ ] **Step 2: Update WikiManager initialization to support recursive listing**

Modify `Faragopedia-Sales/backend/agent/wiki_manager.py`:
Update `list_pages` to search recursively so it finds files in `clients/`, `contacts/`, etc.

```python
    def list_pages(self) -> List[str]:
        """List all markdown files recursively in the wiki directory."""
        pages = []
        for root, _, files in os.walk(self.wiki_dir):
            for f in files:
                if f.endswith(".md") and f not in ["log.md", "index.md", "SCHEMA.md"]:
                    # Get path relative to wiki_dir
                    rel_path = os.path.relpath(os.path.join(root, f), self.wiki_dir)
                    pages.append(rel_path.replace("\\", "/"))
        return sorted(pages)
```

- [ ] **Step 3: Update `get_page_content` to handle sub-paths**

Modify `Faragopedia-Sales/backend/agent/wiki_manager.py`:
```python
    def get_page_content(self, filename: str) -> str:
        """Read content of a wiki page, allowing sub-directories."""
        path = os.path.join(self.wiki_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Page not found: {filename}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
```

- [ ] **Step 4: Commit migration**

```bash
git add Faragopedia-Sales/wiki/
git add Faragopedia-Sales/backend/agent/wiki_manager.py
git commit -m "feat: migrate Wiki-Concept data and support recursive directory structure"
```

---

### Task 2: Implement the Agent Toolbelt

**Files:**
- Create: `backend/agent/tools.py`
- Modify: `backend/agent/wiki_manager.py`

- [ ] **Step 1: Create the Python tools for the LLM**

Create `Faragopedia-Sales/backend/agent/tools.py`:
```python
import os
import re
from typing import List
from langchain.tools import tool

class WikiTools:
    def __init__(self, wiki_dir: str):
        self.wiki_dir = wiki_dir

    @tool
    def list_wiki_files(self) -> str:
        """List all existing entities and files in the wiki recursively."""
        files = []
        for root, _, filenames in os.walk(self.wiki_dir):
            for f in filenames:
                if f.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, f), self.wiki_dir)
                    files.append(rel.replace("\\", "/"))
        return "\n".join(files)

    @tool
    def read_wiki_file(self, rel_path: str) -> str:
        """Read the content of a specific wiki page. Path must be relative to wiki root."""
        full_path = os.path.join(self.wiki_dir, rel_path)
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    @tool
    def write_wiki_file(self, rel_path: str, content: str) -> str:
        """Create or update a wiki page. Agent must provide correct subdirectory path."""
        full_path = os.path.join(self.wiki_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {rel_path}"

    @tool
    def grep_wiki(self, query: str) -> str:
        """Search all wiki files for a specific string (case-insensitive)."""
        results = []
        for root, _, filenames in os.walk(self.wiki_dir):
            for f in filenames:
                if f.endswith(".md"):
                    path = os.path.join(root, f)
                    with open(path, "r", encoding="utf-8") as file:
                        if query.lower() in file.read().lower():
                            rel = os.path.relpath(path, self.wiki_dir)
                            results.append(rel)
        return "\n".join(results) if results else "No matches found."
```

- [ ] **Step 2: Commit tools**

```bash
git add Faragopedia-Sales/backend/agent/tools.py
git commit -m "feat: implement FileSystem toolbelt for the Agent"
```

---

### Task 3: Refactor WikiManager to Autonomous Agent

**Files:**
- Modify: `backend/agent/wiki_manager.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add LangChain Agent dependencies**

Update `Faragopedia-Sales/backend/requirements.txt`:
Add `langchain-hub` and `langgraph`.

- [ ] **Step 2: Update WikiManager to initialize the Agent Loop**

Modify `Faragopedia-Sales/backend/agent/wiki_manager.py`:
```python
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain import hub
from .tools import WikiTools

# Inside WikiManager class
    def _init_agent(self):
        tools = WikiTools(self.wiki_dir)
        self.tool_list = [
            tools.list_wiki_files,
            tools.read_wiki_file,
            tools.write_wiki_file,
            tools.grep_wiki
        ]
        prompt = hub.pull("hwchase17/openai-functions-agent")
        agent = create_openai_functions_agent(self.llm, self.tool_list, prompt)
        return AgentExecutor(agent=agent, tools=self.tool_list, verbose=True)
```

- [ ] **Step 3: Implement Ingest via Agent Loop**

Modify `ingest_source` in `Faragopedia-Sales/backend/agent/wiki_manager.py`:
```python
    async def ingest_source(self, file_name: str):
        # ... Phase 1: Read source ...
        
        # Load System Protocol Context
        schema = self.get_page_content("SCHEMA.md")
        profile = self.get_page_content("company_profile.md")
        
        mission_prompt = f"""
        MISSION: Ingest the following source according to the SCHEMA.md rules.
        
        RULES:
        {schema}
        
        CONTEXT:
        {profile}
        
        SOURCE CONTENT:
        {content}
        
        STEP 1: Use list_wiki_files to see what exists.
        STEP 2: Use grep_wiki to find related entities.
        STEP 3: Read, merge, and write files following the directory structure.
        """
        
        agent_executor = self._init_agent()
        result = await agent_executor.ainvoke({"input": mission_prompt})
        return result
```

- [ ] **Step 4: Commit Agent Refactor**

```bash
git add Faragopedia-Sales/backend/agent/wiki_manager.py
git commit -m "feat: refactor WikiManager to use ReAct Agent loop"
```

---

### Task 4: Frontend "Reasoning Log" (Real-time Feedback)

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `backend/api/routes.py`

- [ ] **Step 1: Implement Server-Sent Events (SSE) for Agent steps**

Modify `Faragopedia-Sales/backend/api/routes.py`:
Update the `/ingest` route to return a `StreamingResponse` that yields the agent's verbose output.

- [ ] **Step 2: Update App.tsx to display streaming logs**

Modify `Faragopedia-Sales/frontend/src/App.tsx`:
Add a `logs` state and a component to display the real-time activity of the agent.

- [ ] **Step 3: Commit UI updates**

```bash
git add Faragopedia-Sales/frontend/src/App.tsx
git commit -m "feat: add real-time reasoning log to the UI"
```
