# Actionable Lint Design

**Date:** 2026-04-20
**Status:** Approved

## Overview

Extend the existing lint operation so the LLM not only identifies wiki issues but also resolves them. The user selects findings via checkboxes and clicks "Apply Selected." The backend snapshots the wiki, sends selected findings to the LLM for fixing, applies the changes using existing `create_page`/`update_page` operations, and returns a report of what changed. Snapshots persist on the Docker volume and can be restored at any time.

---

## Approach

**Second LLM pass (Approach A):** After lint surfaces findings, selected findings are sent back to the LLM with a "fix these" instruction. The LLM uses existing WikiManager file operations to apply changes. One snapshot is created per "Apply Selected" click, before any edits are made.

Rationale: wiki fixes (missing concept pages, broken wikilinks, data gaps) require LLM reasoning, not mechanical string replacement. The existing `create_page`/`update_page` ops are reused without new file-editing logic.

---

## Data Models

### Updated `LintFinding`

```python
class LintFinding(BaseModel):
    severity: str          # 'error' | 'warning' | 'suggestion'
    page: str              # affected page path or 'global'
    description: str       # issue description
    fix_confidence: str    # 'full' | 'stub' | 'needs_source'
    fix_description: str   # plain-English description of what applying will do
```

**`fix_confidence` values:**
- `full` — LLM can fully resolve the issue from existing wiki context
- `stub` — LLM creates a starting-point page/edit; user should complete it afterward
- `needs_source` — resolution requires ingesting new source material via Sources first; the finding serves as a prompt to the user

### New `FixReport`

```python
class FixReport(BaseModel):
    files_changed: List[str]   # paths of modified or created files
    summary: str               # e.g. "Fixed 3 findings: updated 2 pages, created 1 stub"
    skipped: List[str]         # descriptions of findings the LLM could not action
```

### New `Snapshot`

```python
class Snapshot(BaseModel):
    id: str           # timestamp-based, e.g. "20260420-143201"
    label: str        # "pre-lint 2026-04-20 14:32"
    created_at: str
    file_count: int
```

---

## Backend Changes

### New `WikiManager` methods

| Method | Description |
|--------|-------------|
| `fix_lint_findings(findings: List[LintFinding]) -> FixReport` | Entry point: fetches wiki content internally, creates snapshot, calls `_run_fix_llm()`, returns `FixReport` |
| `_run_fix_llm(findings, wiki_content) -> FixReport` | LLM pass instructed to fix selected findings using existing page ops |
| `create_snapshot() -> Snapshot` | Zips the wiki source directory (same path used by `list_pages()`) to `/snapshots/<id>.zip` with metadata JSON |
| `list_snapshots() -> List[Snapshot]` | Reads `/snapshots/` and returns metadata for all snapshots |
| `restore_snapshot(snapshot_id: str)` | Unzips snapshot over current wiki directory |

**Snapshot storage:** `/snapshots/` directory on the same Docker volume as wiki files. Each snapshot is a `.zip` of the wiki directory plus a `<id>.meta.json` file with label, timestamp, and file count.

**Snapshot creation:** One snapshot per "Apply Selected" click, created before any fixes are applied. Never one per individual finding.

### LLM prompt strategy for `_run_fix_llm`

The prompt receives:
- Full current wiki content (same as lint pass)
- The list of selected `LintFinding` objects with their `fix_description` fields
- Instruction to apply each fix using available operations, skip findings it cannot confidently resolve, and return a `FixReport`

---

## API Endpoints

All new. No changes to existing `POST /api/lint`.

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `POST` | `/api/lint/fix` | `{ findings: [LintFinding, ...] }` | `FixReport` |
| `GET` | `/api/snapshots` | — | `List[Snapshot]` |
| `POST` | `/api/snapshots/{snapshot_id}/restore` | — | `{ success: bool, message: str }` |
| `DELETE` | `/api/snapshots/{snapshot_id}` | — | `{ success: bool }` |

---

## Frontend Changes

### `LintView.tsx`

- **Checkbox** on each finding row
- **Fix confidence badge** alongside the severity badge: `Full fix` (green) / `Stub` (amber) / `Needs source` (grey)
- **`fix_description`** shown as a subtitle under the finding description
- **"Select All / Deselect All"** toggle
- **"Apply Selected" button** — disabled until ≥1 finding checked; label shows count: *Apply 3 selected*
- **Result panel** shown inline after apply: files changed list, summary text, any skipped findings

### New `SnapshotsPanel.tsx`

Collapsible section at the bottom of `LintView`:
- List of snapshots with label and creation date
- "Restore" button per snapshot, gated by a confirmation dialog: *"This will overwrite all current wiki files. Are you sure?"*
- "Delete" button per snapshot for cleanup

---

## Error Handling

- If `fix_lint_findings` fails mid-way, the snapshot already exists and the user can restore from it
- If the LLM cannot action a finding, it is added to `FixReport.skipped` — not a hard error
- Restore does not delete the snapshot — it remains available for re-restore
- Restore endpoint returns a clear error message if the snapshot zip is missing or corrupt
- `needs_source` findings are selectable (user can try), but the LLM will likely skip them and they'll appear in `skipped`

---

## What Does Not Change

- `POST /api/lint` — existing endpoint untouched
- `LintReport` model — `findings` field type changes to `List[LintFinding]` with new fields added, which is backwards-compatible with existing display logic
- Sidebar navigation — Lint remains a single sidebar item; Snapshots live inside LintView
