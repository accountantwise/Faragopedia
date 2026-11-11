# Actionable Lint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Extend the lint feature so the LLM not only identifies wiki issues but applies selected fixes, with snapshot-based rollback stored on a persistent Docker volume.

**Architecture:** The existing `/api/lint` endpoint and `LintFinding` model gain two new fields (`fix_confidence`, `fix_description`). A new `/api/lint/fix` endpoint accepts selected findings, creates a pre-fix snapshot, runs a second LLM pass that generates `WikiPage` objects, writes them to disk, and returns a `FixReport`. Four snapshot-management endpoints allow listing, restoring, and deleting snapshots. The frontend gains checkboxes, an "Apply Selected" button, an inline result panel, and a `SnapshotsPanel` component.

**Tech Stack:** Python/FastAPI, LangChain + PydanticOutputParser, React/TypeScript, Tailwind CSS, `zipfile` (stdlib), Docker named volumes.

---

## File Map

| File | Change |
|------|--------|
| `backend/agent/wiki_manager.py` | Update `LintFinding`; add `LintFixPlan`, `FixReport`, `Snapshot` models; add `FIX_HUMAN_TEMPLATE`; update `LINT_HUMAN_TEMPLATE`; add `snapshots_dir` to `__init__`; add snapshot methods + `fix_lint_findings` + `_run_fix_llm` |
| `backend/api/routes.py` | Add `LintFixRequest` request model; import new models; add 4 new endpoints |
| `backend/tests/test_wiki_manager.py` | Update `LintFinding` model tests; add snapshot method tests; add `fix_lint_findings` test |
| `backend/tests/test_api.py` | Add tests for the 4 new endpoints |
| `frontend/src/components/LintView.tsx` | Update TS interfaces; add checkboxes, select-all, fix-confidence badge, apply button, inline `FixReport` panel |
| `frontend/src/components/SnapshotsPanel.tsx` | **Create** — collapsible snapshot list with restore/delete and confirmation dialog |
| `docker-compose.yml` | Add `snapshots_data` named volume mounted at `/app/snapshots` |

---

## Task 1: Update Pydantic models and prompt templates

**Files:**
- Modify: `backend/agent/wiki_manager.py:58-124`
- Modify: `backend/tests/test_wiki_manager.py:218-239`

- [x] **Step 1: Write failing tests for updated `LintFinding` and new models**

Add at the bottom of `backend/tests/test_wiki_manager.py`, after the existing `test_lint_report_model` test:

```python
def test_lint_finding_has_fix_fields():
    finding = LintFinding(
        severity="warning",
        page="clients/louis-vuitton.md",
        description="Missing 'last_contact' field.",
        fix_confidence="full",
        fix_description="Add a last_contact field to the frontmatter.",
    )
    assert finding.fix_confidence == "full"
    assert finding.fix_description == "Add a last_contact field to the frontmatter."


def test_lint_finding_fix_fields_default():
    finding = LintFinding(
        severity="warning",
        page="clients/acme.md",
        description="Some issue.",
    )
    assert finding.fix_confidence == "full"
    assert finding.fix_description == ""


def test_lint_fix_plan_model():
    from agent.wiki_manager import LintFixPlan
    plan = LintFixPlan(
        pages=[WikiPage(path="concepts/e-sign.md", content="# E-Sign\n\nStub.", action="create")],
        skipped=["needs_source: Whitmore bottleneck pages"],
        summary="Fixed 1 finding: created 1 stub.",
    )
    assert len(plan.pages) == 1
    assert plan.pages[0].path == "concepts/e-sign.md"
    assert len(plan.skipped) == 1


def test_fix_report_model():
    from agent.wiki_manager import FixReport
    report = FixReport(
        files_changed=["concepts/e-sign.md"],
        skipped=["needs_source: Whitmore bottleneck pages"],
        summary="Fixed 1 finding: created 1 stub.",
        snapshot_id="20260420-143201",
    )
    assert report.snapshot_id == "20260420-143201"
    assert "concepts/e-sign.md" in report.files_changed


def test_snapshot_model():
    from agent.wiki_manager import Snapshot
    snap = Snapshot(
        id="20260420-143201",
        label="pre-lint 2026-04-20 14:32",
        created_at="2026-04-20T14:32:01",
        file_count=12,
    )
    assert snap.id == "20260420-143201"
    assert snap.file_count == 12
```

Also update the `test_wiki_manager.py` imports line to include new models:
```python
from agent.wiki_manager import (
    WikiManager, WikiPage, FaragoIngestionResult, LintFinding, LintReport,
    LintFixPlan, FixReport, Snapshot
)
```

- [x] **Step 2: Run tests to verify they fail**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wiki_manager.py::test_lint_finding_has_fix_fields tests/test_wiki_manager.py::test_lint_fix_plan_model tests/test_wiki_manager.py::test_fix_report_model tests/test_wiki_manager.py::test_snapshot_model -v
```

Expected: `ImportError` or `ValidationError` — the new models and fields don't exist yet.

- [x] **Step 3: Update `LintFinding` and add new models in `wiki_manager.py`**

Replace lines 58–66 (the existing `LintFinding` and `LintReport` classes):

```python
class LintFinding(BaseModel):
    severity: str = Field(description="'error', 'warning', or 'suggestion'")
    page: str = Field(description="Affected page path (e.g. 'clients/louis-vuitton.md') or 'global'")
    description: str = Field(description="Description of the issue or suggestion")
    fix_confidence: str = Field(default="full", description="'full' (LLM can resolve from existing context), 'stub' (LLM creates a starting-point), or 'needs_source' (requires ingesting new source material first)")
    fix_description: str = Field(default="", description="Plain-English sentence describing what applying the fix will do")

class LintReport(BaseModel):
    findings: List[LintFinding] = Field(description="All findings from the lint operation")
    summary: str = Field(description="One-line summary of findings count by severity")

class LintFixPlan(BaseModel):
    pages: List[WikiPage] = Field(description="Pages to create or update to resolve the selected findings")
    skipped: List[str] = Field(description="Descriptions of findings that could not be actioned")
    summary: str = Field(description="One-line summary, e.g. 'Fixed 3 findings: updated 2 pages, created 1 stub'")

class FixReport(BaseModel):
    files_changed: List[str] = Field(description="Relative paths of wiki pages that were created or modified")
    skipped: List[str] = Field(description="Descriptions of findings that could not be actioned")
    summary: str = Field(description="One-line summary of what was changed")
    snapshot_id: str = Field(description="ID of the pre-fix snapshot created before any edits")

class Snapshot(BaseModel):
    id: str = Field(description="Timestamp-based ID, e.g. '20260420-143201'")
    label: str = Field(description="Human-readable label, e.g. 'pre-lint 2026-04-20 14:32'")
    created_at: str = Field(description="ISO timestamp of when snapshot was created")
    file_count: int = Field(description="Number of wiki files captured in the snapshot")
```

- [x] **Step 4: Update `LINT_HUMAN_TEMPLATE` and add `FIX_HUMAN_TEMPLATE`**

Replace lines 110–124 (the existing `LINT_HUMAN_TEMPLATE`):

```python
LINT_HUMAN_TEMPLATE = """Perform a lint operation on the Farago Projects wiki.

All current wiki pages:
{wiki_content}

Instructions (per SCHEMA.md lint operation):
1. Find orphan pages — pages with no inbound wikilinks from other pages.
2. Flag contradictions between pages (conflicting dates, roles, statuses).
3. Identify entities mentioned in page text that lack their own page.
4. Suggest data gaps that could be filled with a new source or web search.

Return findings grouped by severity: 'error' (structural problems), 'warning' (data quality), 'suggestion' (gaps to fill).
Use page='global' for findings that are not specific to one page.

For each finding also set:
- fix_confidence: 'full' if the fix can be applied entirely from existing wiki context; 'stub' if a useful starting-point page or edit can be created but the user will need to complete it; 'needs_source' if fixing requires ingesting new external source material first.
- fix_description: A short plain-English sentence describing what will happen when the fix is applied (e.g. "Replace all raw/ paths with source/ across 14 files", "Create a stub concepts/e-sign.md page", "Add [[wikilink]] references from index.md to photographers/jane-doe.md").

{format_instructions}"""

FIX_HUMAN_TEMPLATE = """You are applying selected lint fixes to the Farago Projects wiki.

All current wiki pages:
{wiki_content}

Selected findings to fix:
{findings_text}

Instructions:
1. For each finding, produce the full updated or new page content that resolves the issue.
2. Use existing wiki context to produce accurate, realistic content.
3. For 'full' confidence findings: fully resolve the issue.
4. For 'stub' confidence findings: create a well-structured page with clearly marked placeholder sections (e.g. "<!-- TODO: add content -->").
5. For 'needs_source' findings: skip them and add a brief explanation to the skipped list.
6. Always use [[subdir/page-name]] wikilink syntax for cross-references.
7. Use action='create' for new pages, action='update' for modified existing pages.
8. Only include pages that genuinely need to change — do not regenerate unchanged pages.
9. Write a one-line summary (e.g. "Fixed 3 findings: updated 2 pages, created 1 stub").

{format_instructions}"""
```

- [x] **Step 5: Run tests to verify they pass**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wiki_manager.py::test_lint_finding_has_fix_fields tests/test_wiki_manager.py::test_lint_finding_fix_fields_default tests/test_wiki_manager.py::test_lint_fix_plan_model tests/test_wiki_manager.py::test_fix_report_model tests/test_wiki_manager.py::test_snapshot_model -v
```

Expected: all 5 PASS.

- [x] **Step 6: Run existing lint model tests to confirm no regressions**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wiki_manager.py::test_lint_finding_model tests/test_wiki_manager.py::test_lint_report_model tests/test_wiki_manager.py::test_lint_returns_report -v
```

Expected: all 3 PASS (old tests use fields that now have defaults, so they still work).

- [x] **Step 7: Commit**

```bash
git add Faragopedia-Sales/backend/agent/wiki_manager.py Faragopedia-Sales/backend/tests/test_wiki_manager.py
git commit -m "feat(lint): add fix_confidence/fix_description to LintFinding, add LintFixPlan/FixReport/Snapshot models"
```

---

## Task 2: Add snapshot methods to WikiManager + Docker volume

**Files:**
- Modify: `backend/agent/wiki_manager.py` (WikiManager `__init__` and new methods)
- Modify: `backend/tests/test_wiki_manager.py`
- Modify: `docker-compose.yml`

- [x] **Step 1: Write failing snapshot tests**

Add to `backend/tests/test_wiki_manager.py` after existing tests:

```python
def test_create_snapshot(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "acme.md").write_text("# Acme\n")
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    snap = manager.create_snapshot()
    assert snap.file_count >= 1
    assert (snapshots / f"{snap.id}.zip").exists()
    assert (snapshots / f"{snap.id}.meta.json").exists()


def test_list_snapshots(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    manager.create_snapshot(label="snap-1")
    manager.create_snapshot(label="snap-2")
    snaps = manager.list_snapshots()
    assert len(snaps) == 2
    labels = {s.label for s in snaps}
    assert "snap-1" in labels
    assert "snap-2" in labels


def test_restore_snapshot(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    original_file = wiki / "clients" / "acme.md"
    original_file.write_text("# Original\n")
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    snap = manager.create_snapshot()
    # Modify the file after snapshot
    original_file.write_text("# Modified\n")
    assert original_file.read_text() == "# Modified\n"

    manager.restore_snapshot(snap.id)
    assert original_file.read_text() == "# Original\n"


def test_restore_snapshot_not_found(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(tmp_path / "wiki"),
            snapshots_dir=str(tmp_path / "snapshots"),
            schema_dir=str(schema_dir),
        )

    with pytest.raises(FileNotFoundError):
        manager.restore_snapshot("nonexistent-id")


def test_delete_snapshot(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    snap = manager.create_snapshot()
    assert (snapshots / f"{snap.id}.zip").exists()
    manager.delete_snapshot(snap.id)
    assert not (snapshots / f"{snap.id}.zip").exists()
    assert not (snapshots / f"{snap.id}.meta.json").exists()
```

- [x] **Step 2: Run to confirm tests fail**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wiki_manager.py::test_create_snapshot tests/test_wiki_manager.py::test_list_snapshots tests/test_wiki_manager.py::test_restore_snapshot tests/test_wiki_manager.py::test_restore_snapshot_not_found tests/test_wiki_manager.py::test_delete_snapshot -v
```

Expected: `TypeError` — `WikiManager.__init__` doesn't accept `snapshots_dir` yet.

- [x] **Step 3: Add `snapshots_dir` to `WikiManager.__init__` and add `import zipfile` at top**

At the top of `wiki_manager.py`, after the existing imports (line 8), add:
```python
import zipfile
```

(Note: `shutil` and `json` are already imported at lines 6–7.)

Replace the `WikiManager.__init__` signature at line 128:
```python
def __init__(self, sources_dir="sources", wiki_dir="wiki", archive_dir="archive", snapshots_dir="snapshots", llm=None, schema_dir=None):
```

In `__init__`, after `self.archive_sources_dir = ...` (line 132), add:
```python
        self.snapshots_dir = snapshots_dir
```

In the directory creation loop at line 142, add `self.snapshots_dir`:
```python
        for d in [self.sources_dir, self.wiki_dir, self.archive_dir,
                  self.archive_wiki_dir, self.archive_sources_dir, self.snapshots_dir]:
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
```

- [x] **Step 4: Add snapshot methods to `WikiManager`**

Add these four methods to `WikiManager`, after the `lint()` method (after line 639):

```python
    def create_snapshot(self, label: str = None) -> Snapshot:
        snapshot_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        created_at = datetime.datetime.now().isoformat()
        if label is None:
            label = f"pre-lint {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"

        zip_path = os.path.join(self.snapshots_dir, f"{snapshot_id}.zip")
        file_count = 0
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(self.wiki_dir):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    arcname = os.path.relpath(filepath, self.wiki_dir)
                    zf.write(filepath, arcname)
                    file_count += 1

        snapshot = Snapshot(
            id=snapshot_id,
            label=label,
            created_at=created_at,
            file_count=file_count,
        )
        meta_path = os.path.join(self.snapshots_dir, f"{snapshot_id}.meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(snapshot.model_dump_json())

        return snapshot

    def list_snapshots(self) -> List[Snapshot]:
        snapshots = []
        for filename in os.listdir(self.snapshots_dir):
            if filename.endswith(".meta.json"):
                meta_path = os.path.join(self.snapshots_dir, filename)
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                snapshots.append(Snapshot(**data))
        return sorted(snapshots, key=lambda s: s.created_at, reverse=True)

    def restore_snapshot(self, snapshot_id: str):
        zip_path = os.path.join(self.snapshots_dir, f"{snapshot_id}.zip")
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Snapshot {snapshot_id} not found")

        for item in os.listdir(self.wiki_dir):
            item_path = os.path.join(self.wiki_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(self.wiki_dir)

        self.update_index()
        self._rebuild_search_index()

    def delete_snapshot(self, snapshot_id: str):
        zip_path = os.path.join(self.snapshots_dir, f"{snapshot_id}.zip")
        meta_path = os.path.join(self.snapshots_dir, f"{snapshot_id}.meta.json")
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Snapshot {snapshot_id} not found")
        os.remove(zip_path)
        if os.path.exists(meta_path):
            os.remove(meta_path)
```

- [x] **Step 5: Run snapshot tests to verify they pass**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wiki_manager.py::test_create_snapshot tests/test_wiki_manager.py::test_list_snapshots tests/test_wiki_manager.py::test_restore_snapshot tests/test_wiki_manager.py::test_restore_snapshot_not_found tests/test_wiki_manager.py::test_delete_snapshot -v
```

Expected: all 5 PASS.

- [x] **Step 6: Add `snapshots_data` volume to `docker-compose.yml`**

In `docker-compose.yml`, add `snapshots_data` to the top-level `volumes` block:
```yaml
volumes:
  node_modules:
  wiki_data:
  sources_data:
  snapshots_data:
```

And add the mount to the `backend` service `volumes` list:
```yaml
    volumes:
      - wiki_data:/app/wiki
      - sources_data:/app/sources
      - snapshots_data:/app/snapshots
```

- [x] **Step 7: Commit**

```bash
git add Faragopedia-Sales/backend/agent/wiki_manager.py Faragopedia-Sales/backend/tests/test_wiki_manager.py Faragopedia-Sales/docker-compose.yml
git commit -m "feat(lint): add snapshot methods (create/list/restore/delete) with Docker volume"
```

---

## Task 3: Add `fix_lint_findings` and `_run_fix_llm` to WikiManager

**Files:**
- Modify: `backend/agent/wiki_manager.py`
- Modify: `backend/tests/test_wiki_manager.py`

- [x] **Step 1: Write failing test for `fix_lint_findings`**

Add to `backend/tests/test_wiki_manager.py`:

```python
@pytest.mark.asyncio
async def test_fix_lint_findings(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "clients").mkdir()
    (wiki / "clients" / "acme.md").write_text("---\ntype: client\nname: Acme\n---\n# Acme\n")
    snapshots = tmp_path / "snapshots"

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        manager = WikiManager(
            sources_dir=str(tmp_path / "sources"),
            wiki_dir=str(wiki),
            snapshots_dir=str(snapshots),
            schema_dir=str(schema_dir),
        )

    mock_fix_plan = LintFixPlan(
        pages=[WikiPage(
            path="concepts/e-sign.md",
            content="---\ntype: concept\nname: E-Sign\n---\n# E-Sign\n\nStub page.\n",
            action="create",
        )],
        skipped=[],
        summary="Fixed 1 finding: created 1 stub.",
    )

    findings = [
        LintFinding(
            severity="suggestion",
            page="global",
            description="E-sign concept page is missing.",
            fix_confidence="stub",
            fix_description="Create a stub concepts/e-sign.md page.",
        )
    ]

    with patch.object(manager, '_run_fix_llm', new_callable=AsyncMock) as mock_fix_llm:
        mock_fix_llm.return_value = mock_fix_plan
        report = await manager.fix_lint_findings(findings)

    assert isinstance(report, FixReport)
    assert "concepts/e-sign.md" in report.files_changed
    assert report.snapshot_id != ""
    assert (snapshots / f"{report.snapshot_id}.zip").exists()
    assert (wiki / "concepts" / "e-sign.md").exists()
    log_content = (wiki / "log.md").read_text()
    assert "lint-fix" in log_content
```

- [x] **Step 2: Run to confirm test fails**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wiki_manager.py::test_fix_lint_findings -v
```

Expected: `AttributeError` — `fix_lint_findings` doesn't exist yet.

- [x] **Step 3: Add `_run_fix_llm` and `fix_lint_findings` to `WikiManager`**

Add after the `delete_snapshot` method (after the last snapshot method added in Task 2):

```python
    async def _run_fix_llm(self, findings: List[LintFinding], wiki_content: str) -> LintFixPlan:
        findings_text = "\n".join([
            f"{i+1}. [{f.fix_confidence.upper()}] {f.description} (page: {f.page})\n   Fix: {f.fix_description}"
            for i, f in enumerate(findings)
        ])
        parser = PydanticOutputParser(pydantic_object=LintFixPlan)
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template("{system_prompt}"),
            HumanMessagePromptTemplate.from_template(FIX_HUMAN_TEMPLATE),
        ])
        chain = prompt | self.llm | parser
        return await chain.ainvoke({
            "system_prompt": self.system_prompt,
            "wiki_content": wiki_content,
            "findings_text": findings_text,
            "format_instructions": parser.get_format_instructions(),
        })

    async def fix_lint_findings(self, findings: List[LintFinding]) -> FixReport:
        wiki_content = ""
        for rel_path in self.list_pages():
            full_path = os.path.join(self.wiki_dir, rel_path.replace("/", os.sep))
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    wiki_content += f"\n=== {rel_path} ===\n{f.read()}\n"

        snapshot = self.create_snapshot()
        fix_plan = await self._run_fix_llm(findings, wiki_content)

        async with self._write_lock:
            files_changed = []
            for page in fix_plan.pages:
                page_full_path = os.path.join(self.wiki_dir, page.path.replace("/", os.sep))
                os.makedirs(os.path.dirname(page_full_path), exist_ok=True)
                with open(page_full_path, "w", encoding="utf-8") as f:
                    f.write(page.content)
                files_changed.append(page.path)

            self.update_index()
            self._append_to_log("lint-fix", fix_plan.summary)

        self._rebuild_search_index()

        return FixReport(
            files_changed=files_changed,
            skipped=fix_plan.skipped,
            summary=fix_plan.summary,
            snapshot_id=snapshot.id,
        )
```

- [x] **Step 4: Run test to verify it passes**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wiki_manager.py::test_fix_lint_findings -v
```

Expected: PASS.

- [x] **Step 5: Run full wiki_manager test suite to confirm no regressions**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_wiki_manager.py -v
```

Expected: all tests PASS.

- [x] **Step 6: Commit**

```bash
git add Faragopedia-Sales/backend/agent/wiki_manager.py Faragopedia-Sales/backend/tests/test_wiki_manager.py
git commit -m "feat(lint): add fix_lint_findings and _run_fix_llm to WikiManager"
```

---

## Task 4: Add new API endpoints

**Files:**
- Modify: `backend/api/routes.py`
- Modify: `backend/tests/test_api.py`

- [x] **Step 1: Write failing API tests**

Add to `backend/tests/test_api.py`, within the fixture-scoped tests (use the existing `client` fixture):

First, update the `client` fixture in `test_api.py` to mock the new methods. Find the `with patch('api.routes.WikiManager') as MockWM:` block and add these mock assignments alongside the existing ones:

```python
        from agent.wiki_manager import FixReport, Snapshot
        mock_wm.fix_lint_findings = AsyncMock(return_value=FixReport(
            files_changed=["concepts/e-sign.md"],
            skipped=[],
            summary="Fixed 1 finding.",
            snapshot_id="20260420-143201",
        ))
        mock_wm.list_snapshots.return_value = [
            Snapshot(id="20260420-143201", label="pre-lint 2026-04-20 14:32", created_at="2026-04-20T14:32:01", file_count=5)
        ]
        mock_wm.restore_snapshot = MagicMock()
        mock_wm.delete_snapshot = MagicMock()
```

Then add the test functions:

```python
def test_lint_fix_endpoint(client):
    payload = {
        "findings": [
            {
                "severity": "suggestion",
                "page": "global",
                "description": "E-sign concept page is missing.",
                "fix_confidence": "stub",
                "fix_description": "Create a stub concepts/e-sign.md page.",
            }
        ]
    }
    response = client.post("/api/lint/fix", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "files_changed" in data
    assert "snapshot_id" in data
    assert data["snapshot_id"] == "20260420-143201"


def test_lint_fix_empty_findings(client):
    response = client.post("/api/lint/fix", json={"findings": []})
    assert response.status_code == 422


def test_list_snapshots_endpoint(client):
    response = client.get("/api/snapshots")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["id"] == "20260420-143201"


def test_restore_snapshot_endpoint(client):
    response = client.post("/api/snapshots/20260420-143201/restore")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_delete_snapshot_endpoint(client):
    response = client.delete("/api/snapshots/20260420-143201")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
```

- [x] **Step 2: Run to confirm tests fail**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_api.py::test_lint_fix_endpoint tests/test_api.py::test_list_snapshots_endpoint tests/test_api.py::test_restore_snapshot_endpoint tests/test_api.py::test_delete_snapshot_endpoint -v
```

Expected: `404` responses — the endpoints don't exist yet.

- [x] **Step 3: Add the `LintFixRequest` model and update imports in `routes.py`**

Update the import at line 13:
```python
from agent.wiki_manager import WikiManager, LintFinding, FixReport, Snapshot
```

After the `BulkMove` class (around line 28), add:
```python
class LintFixRequest(BaseModel):
    findings: List[LintFinding]

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    def validate_findings_not_empty(self):
        if not self.findings:
            raise ValueError("findings must not be empty")
```

Actually, use a `validator` approach to enforce non-empty findings. Replace the above with:

```python
from pydantic import BaseModel, validator

class LintFixRequest(BaseModel):
    findings: List[LintFinding]

    @validator('findings')
    def findings_not_empty(cls, v):
        if not v:
            raise ValueError('findings must not be empty')
        return v
```

Note: `pydantic` is already available; just add `validator` to the existing `from pydantic import BaseModel` import at line 4:
```python
from pydantic import BaseModel, validator
```

- [x] **Step 4: Add the four new endpoints in `routes.py`**

After the existing `/lint` endpoint (after line 400), add:

```python
@router.post("/lint/fix")
async def fix_lint_findings(request: LintFixRequest):
    try:
        report = await wiki_manager.fix_lint_findings(request.findings)
        return report.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying lint fixes: {str(e)}")


@router.get("/snapshots")
async def list_snapshots():
    try:
        snapshots = wiki_manager.list_snapshots()
        return [s.model_dump() for s in snapshots]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing snapshots: {str(e)}")


@router.post("/snapshots/{snapshot_id}/restore")
async def restore_snapshot(snapshot_id: str):
    try:
        wiki_manager.restore_snapshot(snapshot_id)
        return {"success": True, "message": f"Snapshot {snapshot_id} restored successfully"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error restoring snapshot: {str(e)}")


@router.delete("/snapshots/{snapshot_id}")
async def delete_snapshot(snapshot_id: str):
    try:
        wiki_manager.delete_snapshot(snapshot_id)
        return {"success": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting snapshot: {str(e)}")
```

- [x] **Step 5: Run API tests to verify they pass**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_api.py::test_lint_fix_endpoint tests/test_api.py::test_lint_fix_empty_findings tests/test_api.py::test_list_snapshots_endpoint tests/test_api.py::test_restore_snapshot_endpoint tests/test_api.py::test_delete_snapshot_endpoint -v
```

Expected: all PASS.

- [x] **Step 6: Run full API test suite to confirm no regressions**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/test_api.py -v
```

Expected: all tests PASS.

- [x] **Step 7: Commit**

```bash
git add Faragopedia-Sales/backend/api/routes.py Faragopedia-Sales/backend/tests/test_api.py
git commit -m "feat(lint): add /lint/fix, /snapshots CRUD endpoints"
```

---

## Task 5: Update `LintView.tsx` with checkboxes, fix badges, and Apply Selected

**Files:**
- Modify: `frontend/src/components/LintView.tsx`

- [x] **Step 1: Replace the full contents of `LintView.tsx`**

```tsx
import React, { useState } from 'react';
import { Activity, Loader2, AlertCircle, AlertTriangle, Lightbulb, CheckSquare, Square, Wrench } from 'lucide-react';
import { API_BASE } from '../config';
import SnapshotsPanel from './SnapshotsPanel';

interface LintFinding {
  severity: 'error' | 'warning' | 'suggestion';
  page: string;
  description: string;
  fix_confidence: 'full' | 'stub' | 'needs_source';
  fix_description: string;
}

interface LintReport {
  findings: LintFinding[];
  summary: string;
}

interface FixReport {
  files_changed: string[];
  skipped: string[];
  summary: string;
  snapshot_id: string;
}

const SEVERITY_CONFIG = {
  error: {
    label: 'Errors',
    icon: <AlertCircle className="w-4 h-4 text-red-500" />,
    cardClass: 'bg-red-50 border-red-200',
    badgeClass: 'bg-red-100 text-red-700',
  },
  warning: {
    label: 'Warnings',
    icon: <AlertTriangle className="w-4 h-4 text-amber-500" />,
    cardClass: 'bg-amber-50 border-amber-200',
    badgeClass: 'bg-amber-100 text-amber-700',
  },
  suggestion: {
    label: 'Suggestions',
    icon: <Lightbulb className="w-4 h-4 text-blue-500" />,
    cardClass: 'bg-blue-50 border-blue-200',
    badgeClass: 'bg-blue-100 text-blue-700',
  },
};

const FIX_CONFIDENCE_CONFIG = {
  full: { label: 'Full fix', className: 'bg-green-100 text-green-700' },
  stub: { label: 'Stub', className: 'bg-amber-100 text-amber-700' },
  needs_source: { label: 'Needs source', className: 'bg-gray-100 text-gray-500' },
};

const LintView: React.FC = () => {
  const [report, setReport] = useState<LintReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [applying, setApplying] = useState(false);
  const [fixReport, setFixReport] = useState<FixReport | null>(null);
  const [snapshotsKey, setSnapshotsKey] = useState(0);

  const runLint = async () => {
    setLoading(true);
    setError(null);
    setReport(null);
    setSelected(new Set());
    setFixReport(null);
    try {
      const response = await fetch(`${API_BASE}/lint`, { method: 'POST' });
      if (!response.ok) throw new Error('Lint request failed');
      const data: LintReport = await response.json();
      setReport(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelected = (index: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(index) ? next.delete(index) : next.add(index);
      return next;
    });
  };

  const selectAll = () => {
    if (!report) return;
    setSelected(new Set(report.findings.map((_, i) => i)));
  };

  const deselectAll = () => setSelected(new Set());

  const applySelected = async () => {
    if (!report || selected.size === 0) return;
    setApplying(true);
    setFixReport(null);
    try {
      const selectedFindings = Array.from(selected).map(i => report.findings[i]);
      const response = await fetch(`${API_BASE}/lint/fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ findings: selectedFindings }),
      });
      if (!response.ok) throw new Error('Fix request failed');
      const data: FixReport = await response.json();
      setFixReport(data);
      setSelected(new Set());
      setSnapshotsKey(k => k + 1);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setApplying(false);
    }
  };

  const allSelected = report ? selected.size === report.findings.length : false;

  return (
    <div className="h-full w-full overflow-y-auto">
      <div className="p-8 md:p-12 max-w-4xl mx-auto pb-24">
        <h1 className="text-4xl font-extrabold text-gray-900 mb-6 tracking-tight">Wiki Lint</h1>
        <p className="text-xl text-gray-500 mb-8 leading-relaxed">
          Deep AI analysis — orphan pages, contradictions, missing entities, and data gaps.
        </p>

        <button
          onClick={runLint}
          disabled={loading}
          className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition-colors disabled:opacity-50 mb-8 shadow-sm"
        >
          {loading
            ? <Loader2 className="w-5 h-5 animate-spin mr-2" />
            : <Activity className="w-5 h-5 mr-2" />
          }
          Lint
        </button>

        {loading && (
          <div className="space-y-4 max-w-xl animate-pulse mt-8">
            <div className="flex items-center space-x-3 mb-6">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
              <span className="text-blue-500 font-medium tracking-wide">Deep AI Analysis in Progress...</span>
            </div>
            <div className="h-4 bg-gray-200 rounded-full w-3/4"></div>
            <div className="h-4 bg-gray-200 rounded-full w-full"></div>
            <div className="h-4 bg-gray-200 rounded-full w-5/6"></div>
          </div>
        )}

        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm mb-4">
            {error}
          </div>
        )}

        {fixReport && (
          <div className="p-4 bg-green-50 border border-green-200 rounded-xl mb-6">
            <p className="text-green-800 font-semibold mb-2">{fixReport.summary}</p>
            {fixReport.files_changed.length > 0 && (
              <ul className="text-sm text-green-700 space-y-1">
                {fixReport.files_changed.map(f => (
                  <li key={f} className="font-mono">{f}</li>
                ))}
              </ul>
            )}
            {fixReport.skipped.length > 0 && (
              <div className="mt-3">
                <p className="text-sm font-medium text-amber-700">Skipped:</p>
                <ul className="text-sm text-amber-600 space-y-1 mt-1">
                  {fixReport.skipped.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}

        {report && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <p className="text-gray-600 font-medium">{report.summary}</p>
              {report.findings.length > 0 && (
                <button
                  onClick={allSelected ? deselectAll : selectAll}
                  className="text-sm text-blue-600 hover:underline"
                >
                  {allSelected ? 'Deselect all' : 'Select all'}
                </button>
              )}
            </div>

            {(['error', 'warning', 'suggestion'] as const).map(severity => {
              const findings = report.findings
                .map((f, i) => ({ finding: f, index: i }))
                .filter(({ finding }) => finding.severity === severity);
              if (findings.length === 0) return null;
              const config = SEVERITY_CONFIG[severity];
              return (
                <div key={severity}>
                  <h3 className="flex items-center space-x-2 text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
                    {config.icon}
                    <span>{config.label} ({findings.length})</span>
                  </h3>
                  <ul className="space-y-2">
                    {findings.map(({ finding, index }) => {
                      const isChecked = selected.has(index);
                      const confidenceConfig = FIX_CONFIDENCE_CONFIG[finding.fix_confidence];
                      return (
                        <li
                          key={index}
                          className={`p-4 rounded-xl border ${config.cardClass} cursor-pointer`}
                          onClick={() => toggleSelected(index)}
                        >
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5 flex-shrink-0">
                              {isChecked
                                ? <CheckSquare className="w-5 h-5 text-blue-600" />
                                : <Square className="w-5 h-5 text-gray-400" />
                              }
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2 mb-1">
                                <span className={`inline-block text-xs font-mono px-2 py-0.5 rounded-md ${config.badgeClass}`}>
                                  {finding.page}
                                </span>
                                <span className={`inline-block text-xs px-2 py-0.5 rounded-md font-medium ${confidenceConfig.className}`}>
                                  {confidenceConfig.label}
                                </span>
                              </div>
                              <p className="text-sm text-gray-700">{finding.description}</p>
                              {finding.fix_description && (
                                <p className="text-xs text-gray-500 mt-1 italic">{finding.fix_description}</p>
                              )}
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}

            {report.findings.length === 0 && (
              <p className="text-green-600 font-medium">Wiki is clean — no issues found.</p>
            )}

            {selected.size > 0 && (
              <div className="sticky bottom-4">
                <button
                  onClick={applySelected}
                  disabled={applying}
                  className="flex items-center px-6 py-3 bg-green-600 text-white rounded-xl font-semibold hover:bg-green-700 transition-colors disabled:opacity-50 shadow-lg"
                >
                  {applying
                    ? <Loader2 className="w-5 h-5 animate-spin mr-2" />
                    : <Wrench className="w-5 h-5 mr-2" />
                  }
                  Apply {selected.size} selected
                </button>
              </div>
            )}
          </div>
        )}

        <SnapshotsPanel key={snapshotsKey} />
      </div>
    </div>
  );
};

export default LintView;
```

- [x] **Step 2: Verify the TypeScript compiles**

```bash
cd Faragopedia-Sales/frontend
npm run build 2>&1 | head -40
```

Expected: build succeeds with no TypeScript errors. If `Wrench` is not available in the installed version of `lucide-react`, replace it with `Hammer` or `Settings`.

- [x] **Step 3: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/LintView.tsx
git commit -m "feat(lint): add checkboxes, fix-confidence badges, and Apply Selected button to LintView"
```

---

## Task 6: Create `SnapshotsPanel.tsx` and integrate

**Files:**
- Create: `frontend/src/components/SnapshotsPanel.tsx`

- [x] **Step 1: Create `SnapshotsPanel.tsx`**

```tsx
import React, { useState, useEffect, useCallback } from 'react';
import { ChevronDown, ChevronRight, RotateCcw, Trash2, Loader2 } from 'lucide-react';
import { API_BASE } from '../config';

interface Snapshot {
  id: string;
  label: string;
  created_at: string;
  file_count: number;
}

const SnapshotsPanel: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmRestore, setConfirmRestore] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const fetchSnapshots = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/snapshots`);
      if (!res.ok) throw new Error('Failed to load snapshots');
      setSnapshots(await res.json());
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) fetchSnapshots();
  }, [open, fetchSnapshots]);

  const restoreSnapshot = async (id: string) => {
    setActionInProgress(id);
    setConfirmRestore(null);
    try {
      const res = await fetch(`${API_BASE}/snapshots/${id}/restore`, { method: 'POST' });
      if (!res.ok) throw new Error('Restore failed');
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionInProgress(null);
    }
  };

  const deleteSnapshot = async (id: string) => {
    setActionInProgress(id);
    try {
      const res = await fetch(`${API_BASE}/snapshots/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      setSnapshots(prev => prev.filter(s => s.id !== id));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionInProgress(null);
    }
  };

  return (
    <div className="mt-12 border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 bg-gray-50 hover:bg-gray-100 transition-colors text-sm font-semibold text-gray-700"
      >
        <span>Snapshots</span>
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>

      {open && (
        <div className="p-5">
          {loading && (
            <div className="flex items-center gap-2 text-gray-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading snapshots...
            </div>
          )}

          {error && (
            <p className="text-red-600 text-sm">{error}</p>
          )}

          {!loading && snapshots.length === 0 && (
            <p className="text-gray-400 text-sm">No snapshots yet. Snapshots are created automatically before applying lint fixes.</p>
          )}

          {snapshots.length > 0 && (
            <ul className="space-y-2">
              {snapshots.map(snap => (
                <li key={snap.id} className="flex items-center justify-between p-3 bg-white border border-gray-100 rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-gray-800">{snap.label}</p>
                    <p className="text-xs text-gray-400">{new Date(snap.created_at).toLocaleString()} · {snap.file_count} files</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {confirmRestore === snap.id ? (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-amber-700 font-medium">Overwrite current wiki?</span>
                        <button
                          onClick={() => restoreSnapshot(snap.id)}
                          className="px-3 py-1 bg-amber-600 text-white rounded-lg hover:bg-amber-700 text-xs font-semibold"
                        >
                          Yes, restore
                        </button>
                        <button
                          onClick={() => setConfirmRestore(null)}
                          className="px-3 py-1 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 text-xs font-semibold"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          onClick={() => setConfirmRestore(snap.id)}
                          disabled={actionInProgress === snap.id}
                          className="flex items-center gap-1 px-3 py-1 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg disabled:opacity-50"
                        >
                          {actionInProgress === snap.id
                            ? <Loader2 className="w-3 h-3 animate-spin" />
                            : <RotateCcw className="w-3 h-3" />
                          }
                          Restore
                        </button>
                        <button
                          onClick={() => deleteSnapshot(snap.id)}
                          disabled={actionInProgress === snap.id}
                          className="flex items-center gap-1 px-3 py-1 text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 rounded-lg disabled:opacity-50"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default SnapshotsPanel;
```

- [x] **Step 2: Verify the build**

```bash
cd Faragopedia-Sales/frontend
npm run build 2>&1 | head -40
```

Expected: no TypeScript errors.

- [x] **Step 3: Run full backend test suite one final time**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/ -v
```

Expected: all tests PASS.

- [x] **Step 4: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/SnapshotsPanel.tsx
git commit -m "feat(lint): add SnapshotsPanel component with restore/delete and confirmation dialog"
```

---

## Task 7: Wire `snapshots_dir` in the backend entrypoint

**Files:**
- Modify: `backend/api/routes.py` (or wherever `WikiManager` is instantiated with its paths)

- [x] **Step 1: Add `SNAPSHOTS_DIR` constant and pass it to `WikiManager` in `routes.py`**

In `backend/api/routes.py`, after line 40 (`ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")`), add:

```python
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "snapshots")
```

Then update the `WikiManager` instantiation at line 43 to include it:

```python
wiki_manager = WikiManager(
    sources_dir=SOURCES_DIR,
    wiki_dir=WIKI_DIR,
    archive_dir=ARCHIVE_DIR,
    snapshots_dir=SNAPSHOTS_DIR,
)
```

- [x] **Step 3: Verify backend starts without errors**

```bash
cd Faragopedia-Sales/backend
python -m pytest tests/ -v
```

Expected: all tests PASS.

- [x] **Step 4: Final commit**

```bash
git add Faragopedia-Sales/backend/api/routes.py
git commit -m "feat(lint): wire snapshots_dir=/app/snapshots in WikiManager instantiation"
```
