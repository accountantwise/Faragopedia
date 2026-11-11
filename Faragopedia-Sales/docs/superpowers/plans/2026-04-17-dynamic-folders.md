# Dynamic Folders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users create/delete/rename wiki folders and move pages between them, with all structural changes automatically reflected in SCHEMA.md so the AI agent operates correctly on future ingest/lint/query calls.

**Architecture:** Each wiki folder gets a `_type.yaml` metadata file defining its name, description, and frontmatter fields. SCHEMA.md is split into a fixed template (operations, rules) and a dynamic section auto-generated from `_type.yaml` files. The backend discovers valid entity types from the filesystem at runtime instead of a hardcoded list. The frontend sidebar gains folder management UI (create, rename, delete) and a move-page dialog.

**Tech Stack:** Python/FastAPI backend, React/TypeScript frontend, YAML for folder metadata, existing LangChain LLM integration.

---

## File Structure

### New files
- `Faragopedia-Sales/backend/agent/schema_builder.py` — Reads `_type.yaml` files, assembles dynamic SCHEMA.md, provides `get_entity_types()` helper
- `Faragopedia-Sales/backend/tests/test_schema_builder.py` — Tests for schema assembly and type discovery
- `Faragopedia-Sales/backend/tests/test_folder_ops.py` — Tests for folder CRUD and page move operations
- `Wiki-Concept/clients/_type.yaml` — Type metadata for clients folder
- `Wiki-Concept/prospects/_type.yaml` — Type metadata for prospects folder
- `Wiki-Concept/contacts/_type.yaml` — Type metadata for contacts folder
- `Wiki-Concept/photographers/_type.yaml` — Type metadata for photographers folder
- `Wiki-Concept/productions/_type.yaml` — Type metadata for productions folder
- `Wiki-Concept/SCHEMA_TEMPLATE.md` — Fixed portion of SCHEMA.md (operations, rules, identity)

### Modified files
- `Faragopedia-Sales/backend/agent/wiki_manager.py` — Replace hardcoded `ENTITY_SUBDIRS` with dynamic discovery; add `move_page()`, `create_folder()`, `delete_folder()`, `rename_folder()`, `rebuild_schema()`; load system prompt dynamically
- `Faragopedia-Sales/backend/api/routes.py` — Replace `VALID_ENTITY_SUBDIRS` set with dynamic lookup; add folder CRUD endpoints and page move endpoint
- `Faragopedia-Sales/frontend/src/components/WikiView.tsx` — Replace hardcoded `ENTITY_TYPES` array with data from API; add folder management UI (create/rename/delete); add move-page dialog
- `Wiki-Concept/SCHEMA.md` — Now auto-generated (fixed template + dynamic entity types from `_type.yaml` files)

---

## Task 1: Create `_type.yaml` seed files for existing folders

Seed the five existing entity folders with `_type.yaml` metadata so the system has something to read from day one. No code changes yet — just the data files.

**Files:**
- Create: `Wiki-Concept/clients/_type.yaml`
- Create: `Wiki-Concept/prospects/_type.yaml`
- Create: `Wiki-Concept/contacts/_type.yaml`
- Create: `Wiki-Concept/photographers/_type.yaml`
- Create: `Wiki-Concept/productions/_type.yaml`

- [ ] **Step 1: Create clients/_type.yaml**

```yaml
name: Clients
description: Active client brands and fashion houses
singular: client
fields:
  - name: type
    type: string
    default: client
  - name: name
    type: string
    required: true
  - name: industry
    type: string
  - name: tier
    type: enum
    values: [A, B, C]
    description: "A = active/high value, B = occasional, C = cold"
  - name: status
    type: enum
    values: [active, inactive]
  - name: hq
    type: string
  - name: relationship_since
    type: string
  - name: last_contact
    type: date
  - name: source_count
    type: integer
sections:
  - Overview
  - Key Contacts
  - Production History
  - Relationship Notes
  - Open Opportunities
  - Sources
```

- [ ] **Step 2: Create prospects/_type.yaml**

```yaml
name: Prospects
description: Pipeline and potential clients or publications being actively pursued
singular: prospect
fields:
  - name: type
    type: string
    default: prospect
  - name: name
    type: string
    required: true
  - name: industry
    type: string
  - name: tier
    type: enum
    values: [A, B, C]
    description: "A = high priority, B = medium, C = low/watch"
  - name: status
    type: enum
    values: [prospect, target]
  - name: hq
    type: string
  - name: last_contact
    type: date
  - name: source_count
    type: integer
sections:
  - Overview
  - Key Contacts
  - Why Farago
  - Outreach History
  - Open Opportunities
  - Sources
```

- [ ] **Step 3: Create contacts/_type.yaml**

```yaml
name: Contacts
description: Individual people across all organisations
singular: contact
fields:
  - name: type
    type: string
    default: contact
  - name: name
    type: string
    required: true
  - name: role
    type: string
  - name: org
    type: string
  - name: linked_orgs
    type: list
    default: "[]"
  - name: last_contact
    type: date
sections:
  - Bio
  - Role & Responsibilities
  - Relationship History
  - Productions Involved
  - Notes
```

- [ ] **Step 4: Create photographers/_type.yaml**

```yaml
name: Photographers
description: Photographer roster and potential collaborators
singular: photographer
fields:
  - name: type
    type: string
    default: photographer
  - name: name
    type: string
    required: true
  - name: tier
    type: enum
    values: [A, B, C]
    description: "A = frequent collaborator, B = occasional, C = one-off/prospect"
  - name: representation
    type: string
  - name: based
    type: string
  - name: speciality
    type: list
    default: "[]"
sections:
  - Bio
  - Style Notes
  - Productions
  - Client Relationships
  - Availability Notes
  - Sources
```

- [ ] **Step 5: Create productions/_type.yaml**

```yaml
name: Productions
description: Individual shoot, project, or event pages
singular: production
fields:
  - name: entity_type
    type: string
    default: production
  - name: date
    type: date
  - name: client
    type: string
  - name: publication
    type: string
  - name: photographer
    type: string
  - name: location
    type: string
  - name: work_type
    type: enum
    values: [editorial, advertising, lookbook, show, event]
  - name: status
    type: enum
    values: [complete, in-progress, pitched]
sections:
  - Brief
  - Team
  - Outcome & Notes
  - Sources
```

- [ ] **Step 6: Commit**

```bash
git add Wiki-Concept/clients/_type.yaml Wiki-Concept/prospects/_type.yaml Wiki-Concept/contacts/_type.yaml Wiki-Concept/photographers/_type.yaml Wiki-Concept/productions/_type.yaml
git commit -m "feat: seed _type.yaml metadata for all five existing entity folders"
```

---

## Task 2: Create schema_builder.py — dynamic type discovery and schema assembly

Build the module that reads `_type.yaml` files from disk and assembles the dynamic portion of SCHEMA.md. This is the core engine that makes everything else work.

**Files:**
- Create: `Faragopedia-Sales/backend/agent/schema_builder.py`
- Create: `Faragopedia-Sales/backend/tests/test_schema_builder.py`
- Create: `Wiki-Concept/SCHEMA_TEMPLATE.md`

- [ ] **Step 1: Write the failing tests**

Create `Faragopedia-Sales/backend/tests/test_schema_builder.py`:

```python
import os
import pytest
import yaml
from agent.schema_builder import (
    load_type_yaml,
    discover_entity_types,
    render_type_schema_section,
    build_schema_md,
)


@pytest.fixture
def wiki_with_types(tmp_path):
    """Create a wiki dir with two entity folders and _type.yaml files."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()

    clients = wiki / "clients"
    clients.mkdir()
    (clients / "_type.yaml").write_text(yaml.dump({
        "name": "Clients",
        "description": "Active client brands",
        "singular": "client",
        "fields": [
            {"name": "type", "type": "string", "default": "client"},
            {"name": "name", "type": "string", "required": True},
            {"name": "tier", "type": "enum", "values": ["A", "B", "C"]},
        ],
        "sections": ["Overview", "Key Contacts", "Sources"],
    }))

    stylists = wiki / "stylists"
    stylists.mkdir()
    (stylists / "_type.yaml").write_text(yaml.dump({
        "name": "Stylists",
        "description": "Hair and makeup stylists",
        "singular": "stylist",
        "fields": [
            {"name": "type", "type": "string", "default": "stylist"},
            {"name": "name", "type": "string", "required": True},
            {"name": "agency", "type": "string"},
        ],
        "sections": ["Bio", "Productions"],
    }))

    # A folder without _type.yaml should be ignored
    (wiki / "sources").mkdir()

    return str(wiki)


def test_load_type_yaml(wiki_with_types):
    data = load_type_yaml(os.path.join(wiki_with_types, "clients"))
    assert data["name"] == "Clients"
    assert data["singular"] == "client"
    assert len(data["fields"]) == 3


def test_load_type_yaml_missing_file(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = load_type_yaml(str(empty))
    assert result is None


def test_discover_entity_types(wiki_with_types):
    types = discover_entity_types(wiki_with_types)
    names = sorted(types.keys())
    assert names == ["clients", "stylists"]
    assert types["clients"]["name"] == "Clients"
    assert types["stylists"]["name"] == "Stylists"


def test_discover_skips_dirs_without_type_yaml(wiki_with_types):
    types = discover_entity_types(wiki_with_types)
    assert "sources" not in types


def test_render_type_schema_section():
    type_data = {
        "name": "Clients",
        "singular": "client",
        "description": "Active client brands",
        "fields": [
            {"name": "type", "type": "string", "default": "client"},
            {"name": "name", "type": "string", "required": True},
            {"name": "tier", "type": "enum", "values": ["A", "B", "C"]},
        ],
        "sections": ["Overview", "Key Contacts"],
    }
    section = render_type_schema_section("clients", type_data)
    assert "### clients/[" in section
    assert "type: client" in section or "type:" in section
    assert "tier: A | B | C" in section
    assert "## Overview" in section or "`## Overview`" in section


def test_build_schema_md(wiki_with_types, tmp_path):
    template_path = tmp_path / "SCHEMA_TEMPLATE.md"
    template_path.write_text(
        "# SCHEMA.md\n\nFixed content here.\n\n"
        "{{ENTITY_TYPES_DIRECTORY}}\n\n"
        "{{ENTITY_TYPES_SCHEMAS}}\n\n"
        "## Operations\n\nFixed operations.\n"
    )
    result = build_schema_md(wiki_with_types, str(template_path))
    assert "# SCHEMA.md" in result
    assert "clients/" in result
    assert "stylists/" in result
    assert "## Operations" in result
    assert "{{ENTITY_TYPES_DIRECTORY}}" not in result
    assert "{{ENTITY_TYPES_SCHEMAS}}" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/test_schema_builder.py -v 2>&1 | head -30
```

Expected: ImportError — `agent.schema_builder` does not exist yet.

- [ ] **Step 3: Create SCHEMA_TEMPLATE.md**

Extract the fixed portions of SCHEMA.md into a template. The two placeholders `{{ENTITY_TYPES_DIRECTORY}}` and `{{ENTITY_TYPES_SCHEMAS}}` will be filled by the builder.

Create `Wiki-Concept/SCHEMA_TEMPLATE.md`:

```markdown
# SCHEMA.md — Farago Projects LLM Wiki

This file is the operating manual for the LLM wiki agent. Read it at the start of every session before taking any action.

---

## Identity

You are the wiki agent for Farago Projects — a creative production house specialising in stills and motion for the fashion, beauty, and luxury industries. Based in London and Paris, operating globally.

Your role: maintain a persistent, compounding knowledge base of client intelligence, partner relationships, photographer rosters, and production history. You write and maintain all wiki pages. The human curates sources and directs analysis.

Read `company_profile.md` if you need full company context.

---

## Session Start Protocol

At the start of EVERY session, before responding to any request:

1. Read `SCHEMA.md` (this file)
2. Read `index.md` to load current wiki state
3. Read the last 10 entries of `log.md` to understand recent activity

---

## Directory Structure

```
Wiki/
├── SCHEMA.md              # This file — LLM operating manual
├── SCHEMA_TEMPLATE.md     # Template used to regenerate this file (do not modify)
├── index.md               # Master catalog of all wiki pages
├── log.md                 # Append-only chronological log
├── company_profile.md     # Farago Projects profile (IMMUTABLE — never modify)
│
{{ENTITY_TYPES_DIRECTORY}}
└── sources/               # Immutable raw source documents (human drops here — never modify)
    └── assets/            # Downloaded images
```

---

## Immutable Files

NEVER modify these files under any circumstances:
- `sources/` — all files and subdirectories
- `company_profile.md`
- `SCHEMA_TEMPLATE.md`

---

## Page Schemas

All wiki pages use YAML frontmatter for Obsidian Dataview compatibility. Use wikilink syntax (`[[page-name]]`) for all cross-references.

{{ENTITY_TYPES_SCHEMAS}}

---

## Operations

### Ingest
**Trigger:** User says "ingest [source]" or "ingest [filename]"

1. Read the source file from `sources/`
2. Discuss key takeaways with the user
3. Create or update all touched entity pages — file them into the correct subdirectory based on entity type
4. Update `index.md` — add any new pages, update summaries of changed pages
5. Append to `log.md`: `## [YYYY-MM-DD] ingest | [source title]` followed by a 2–3 line summary of what was updated

A single source may touch 5–15 wiki pages. Update all of them.

---

### Query
**Trigger:** Any question about clients, prospects, contacts, photographers, productions, or relationships

1. Read `index.md` to identify the most relevant pages
2. Read those pages in full
3. Synthesize a clear answer with inline wikilink citations (`[[page-name]]`)
4. If the answer is valuable enough to keep (a comparison, analysis, or synthesis), offer to file it as a new wiki page
5. Append to `log.md`: `## [YYYY-MM-DD] query | [topic]`

---

### Lint
**Trigger:** User says "lint"

1. Read all pages listed in `index.md`
2. Scan for orphan pages (pages with no inbound wikilinks from other pages)
3. Flag contradictions between pages (e.g. conflicting dates, roles, or status)
4. Identify entities mentioned in page text that lack their own page
5. Suggest data gaps that could be filled with a web search or new source
6. Flag pages whose frontmatter does not match the schema defined in their folder's `_type.yaml`
7. Append to `log.md`: `## [YYYY-MM-DD] lint | [brief summary of findings]`

---

## General Rules

1. **Never modify** `sources/`, `company_profile.md`, or `SCHEMA_TEMPLATE.md`
2. **Always use wikilinks** — cite cross-references as `[[page-name]]` not plain text
3. **Prefer updating over creating** — update an existing page before creating a new one
4. **Keep index.md current** — update it on every ingest operation
5. **Keep log.md current** — append an entry on every ingest, query, and lint operation
6. **Sources inline** — cite sources in the relevant section of entity/production pages; no separate source summary pages
7. **Frontmatter always** — every wiki page must have valid YAML frontmatter matching its folder's `_type.yaml` schema
8. **File naming** — lowercase, hyphen-separated: `louis-vuitton.md`, `jamie-hawkesworth.md`, `2026-02-louis-vuitton-editorial.md`
9. **Respect folder types** — when creating or updating pages, use the frontmatter fields defined in that folder's `_type.yaml`
```

- [ ] **Step 4: Implement schema_builder.py**

Create `Faragopedia-Sales/backend/agent/schema_builder.py`:

```python
import os
from typing import Dict, Optional

import yaml


def load_type_yaml(folder_path: str) -> Optional[Dict]:
    """Load _type.yaml from a folder. Returns None if not found."""
    yaml_path = os.path.join(folder_path, "_type.yaml")
    if not os.path.exists(yaml_path):
        return None
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def discover_entity_types(wiki_dir: str) -> Dict[str, Dict]:
    """Scan wiki_dir for subdirectories containing _type.yaml.
    Returns {folder_name: type_data} sorted alphabetically.
    """
    types = {}
    for entry in sorted(os.listdir(wiki_dir)):
        full = os.path.join(wiki_dir, entry)
        if not os.path.isdir(full):
            continue
        data = load_type_yaml(full)
        if data is not None:
            types[entry] = data
    return types


def render_type_schema_section(folder_name: str, type_data: Dict) -> str:
    """Render one entity type as a SCHEMA.md subsection."""
    singular = type_data.get("singular", folder_name.rstrip("s"))
    description = type_data.get("description", "")
    fields = type_data.get("fields", [])
    sections = type_data.get("sections", [])

    lines = [f"### {folder_name}/[{singular}-name].md"]
    if description:
        lines.append("")
        lines.append(f"*{description}*")
    lines.append("")
    lines.append("```yaml")
    lines.append("---")
    for field in fields:
        fname = field["name"]
        ftype = field.get("type", "string")
        if ftype == "enum":
            values = field.get("values", [])
            comment = field.get("description", "")
            value_str = " | ".join(str(v) for v in values)
            line = f"{fname}: {value_str}"
            if comment:
                line += f"          # {comment}"
            lines.append(line)
        elif ftype == "list":
            default = field.get("default", "[]")
            lines.append(f"{fname}: {default}")
        elif "default" in field:
            lines.append(f"{fname}: {field['default']}")
        else:
            lines.append(f"{fname}:")
    lines.append("---")
    lines.append("```")

    if sections:
        lines.append("")
        section_str = " · ".join(f"`## {s}`" for s in sections)
        lines.append(f"Sections: {section_str}")

    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def _render_directory_tree(types: Dict[str, Dict]) -> str:
    """Render the entity types as directory tree entries for SCHEMA.md."""
    lines = []
    for folder_name, type_data in types.items():
        singular = type_data.get("singular", folder_name.rstrip("s"))
        description = type_data.get("description", "")
        comment = f"  # {description}" if description else ""
        lines.append(f"├── {folder_name}/{comment}")
        lines.append(f"│   └── [{singular}-name].md")
    return "\n".join(lines)


def build_schema_md(wiki_dir: str, template_path: str) -> str:
    """Assemble SCHEMA.md from the template and _type.yaml files."""
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    types = discover_entity_types(wiki_dir)

    # Build directory tree block
    directory_block = _render_directory_tree(types)

    # Build schema sections block
    schema_sections = []
    for folder_name, type_data in types.items():
        schema_sections.append(render_type_schema_section(folder_name, type_data))
    schemas_block = "\n".join(schema_sections)

    result = template.replace("{{ENTITY_TYPES_DIRECTORY}}", directory_block)
    result = result.replace("{{ENTITY_TYPES_SCHEMAS}}", schemas_block)
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/test_schema_builder.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/backend/agent/schema_builder.py Faragopedia-Sales/backend/tests/test_schema_builder.py Wiki-Concept/SCHEMA_TEMPLATE.md
git commit -m "feat: add schema_builder for dynamic entity type discovery and SCHEMA.md assembly"
```

---

## Task 3: Add folder CRUD and page move to WikiManager

Add `create_folder()`, `delete_folder()`, `rename_folder()`, `move_page()`, and `rebuild_schema()` to WikiManager. Replace hardcoded `ENTITY_SUBDIRS` with dynamic discovery. Update `update_index()` to use dynamic types.

**Files:**
- Modify: `Faragopedia-Sales/backend/agent/wiki_manager.py`
- Create: `Faragopedia-Sales/backend/tests/test_folder_ops.py`

- [ ] **Step 1: Write the failing tests**

Create `Faragopedia-Sales/backend/tests/test_folder_ops.py`:

```python
import os
import pytest
import yaml
from unittest.mock import patch, MagicMock

from agent.wiki_manager import WikiManager


@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "AI_PROVIDER": "openai",
        "AI_MODEL": "gpt-4o-mini",
    }):
        yield


@pytest.fixture
def manager_with_types(tmp_path):
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "SCHEMA.md").write_text("# Schema")
    (schema_dir / "company_profile.md").write_text("# Profile")
    (schema_dir / "SCHEMA_TEMPLATE.md").write_text(
        "# SCHEMA\n\n{{ENTITY_TYPES_DIRECTORY}}\n\n{{ENTITY_TYPES_SCHEMAS}}\n"
    )

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    sources = tmp_path / "sources"
    sources.mkdir()

    # Create one entity folder with _type.yaml
    clients = wiki / "clients"
    clients.mkdir()
    (clients / "_type.yaml").write_text(yaml.dump({
        "name": "Clients",
        "description": "Active client brands",
        "singular": "client",
        "fields": [
            {"name": "type", "type": "string", "default": "client"},
            {"name": "name", "type": "string", "required": True},
        ],
        "sections": ["Overview"],
    }))
    (clients / "test-brand.md").write_text("---\ntype: client\nname: Test Brand\n---\n# Test Brand\n")

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        mgr = WikiManager(
            sources_dir=str(sources),
            wiki_dir=str(wiki),
            archive_dir=str(tmp_path / "archive"),
            schema_dir=str(schema_dir),
        )
    return mgr


@pytest.mark.asyncio
async def test_create_folder(manager_with_types):
    mgr = manager_with_types
    await mgr.create_folder("stylists", "Stylists", "Hair and makeup stylists")

    folder = os.path.join(mgr.wiki_dir, "stylists")
    assert os.path.isdir(folder)

    type_yaml_path = os.path.join(folder, "_type.yaml")
    assert os.path.exists(type_yaml_path)

    with open(type_yaml_path) as f:
        data = yaml.safe_load(f)
    assert data["name"] == "Stylists"
    assert data["description"] == "Hair and makeup stylists"


@pytest.mark.asyncio
async def test_create_folder_already_exists(manager_with_types):
    mgr = manager_with_types
    with pytest.raises(ValueError, match="already exists"):
        await mgr.create_folder("clients", "Clients", "Duplicate")


@pytest.mark.asyncio
async def test_delete_folder_empty(manager_with_types):
    mgr = manager_with_types
    # Create then delete an empty folder
    await mgr.create_folder("stylists", "Stylists", "Test")
    await mgr.delete_folder("stylists")

    assert not os.path.exists(os.path.join(mgr.wiki_dir, "stylists"))


@pytest.mark.asyncio
async def test_delete_folder_nonempty_raises(manager_with_types):
    mgr = manager_with_types
    with pytest.raises(ValueError, match="not empty"):
        await mgr.delete_folder("clients")


@pytest.mark.asyncio
async def test_rename_folder(manager_with_types):
    mgr = manager_with_types
    # Create a page that links to clients/test-brand
    prospects = os.path.join(mgr.wiki_dir, "prospects")
    os.makedirs(prospects)
    (open(os.path.join(prospects, "_type.yaml"), "w")).write(yaml.dump({
        "name": "Prospects", "singular": "prospect", "fields": [], "sections": [],
    }))
    with open(os.path.join(prospects, "some-prospect.md"), "w") as f:
        f.write("---\ntype: prospect\n---\n# Prospect\n\nRelated: [[clients/test-brand]]\n")

    await mgr.rename_folder("clients", "brands")

    # Old folder gone, new folder exists
    assert not os.path.exists(os.path.join(mgr.wiki_dir, "clients"))
    assert os.path.isdir(os.path.join(mgr.wiki_dir, "brands"))

    # Page moved
    assert os.path.exists(os.path.join(mgr.wiki_dir, "brands", "test-brand.md"))

    # Wikilinks in other pages updated
    with open(os.path.join(prospects, "some-prospect.md")) as f:
        content = f.read()
    assert "[[brands/test-brand]]" in content
    assert "[[clients/test-brand]]" not in content


@pytest.mark.asyncio
async def test_move_page(manager_with_types):
    mgr = manager_with_types
    # Create target folder
    await mgr.create_folder("prospects", "Prospects", "Pipeline")

    # Move the page
    new_path = await mgr.move_page("clients/test-brand.md", "prospects")

    assert new_path == "prospects/test-brand.md"
    assert not os.path.exists(os.path.join(mgr.wiki_dir, "clients", "test-brand.md"))
    assert os.path.exists(os.path.join(mgr.wiki_dir, "prospects", "test-brand.md"))


@pytest.mark.asyncio
async def test_move_page_updates_wikilinks(manager_with_types):
    mgr = manager_with_types
    await mgr.create_folder("prospects", "Prospects", "Pipeline")

    # Create a page that references clients/test-brand
    prospects_dir = os.path.join(mgr.wiki_dir, "prospects")
    with open(os.path.join(prospects_dir, "other.md"), "w") as f:
        f.write("---\ntype: prospect\n---\n# Other\n\nSee [[clients/test-brand]]\n")

    await mgr.move_page("clients/test-brand.md", "prospects")

    with open(os.path.join(prospects_dir, "other.md")) as f:
        content = f.read()
    assert "[[prospects/test-brand]]" in content
    assert "[[clients/test-brand]]" not in content


@pytest.mark.asyncio
async def test_move_page_invalid_target(manager_with_types):
    mgr = manager_with_types
    with pytest.raises(ValueError, match="does not exist"):
        await mgr.move_page("clients/test-brand.md", "nonexistent")


def test_get_entity_types_is_dynamic(manager_with_types):
    mgr = manager_with_types
    types = mgr.get_entity_types()
    assert "clients" in types
    assert isinstance(types["clients"], dict)
    assert types["clients"]["name"] == "Clients"


def test_update_index_uses_dynamic_types(manager_with_types):
    mgr = manager_with_types
    mgr.update_index()
    index_path = os.path.join(mgr.wiki_dir, "index.md")
    with open(index_path) as f:
        content = f.read()
    assert "## Clients" in content
    assert "[[clients/test-brand]]" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/test_folder_ops.py -v 2>&1 | head -40
```

Expected: AttributeError — WikiManager has no `create_folder`, `move_page`, etc.

- [ ] **Step 3: Implement the changes in wiki_manager.py**

Add these imports at the top of `wiki_manager.py`:

```python
import yaml
from agent.schema_builder import discover_entity_types, build_schema_md
```

Replace the hardcoded `ENTITY_SUBDIRS` line:

```python
# Remove this line:
# ENTITY_SUBDIRS = ["clients", "prospects", "contacts", "photographers", "productions"]
```

Add `get_entity_types()` method to WikiManager:

```python
def get_entity_types(self) -> Dict[str, Dict]:
    """Discover entity types dynamically from _type.yaml files."""
    return discover_entity_types(self.wiki_dir)
```

Replace `update_index()` to use dynamic types instead of hardcoded `ENTITY_SUBDIRS`:

```python
def update_index(self):
    """Regenerate index.md grouped by entity subdirectory (dynamic)."""
    index_path = os.path.join(self.wiki_dir, "index.md")
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    entity_types = self.get_entity_types()
    sections = {}
    for sub in entity_types:
        sub_dir = os.path.join(self.wiki_dir, sub)
        if not os.path.exists(sub_dir):
            continue
        files = sorted(
            f for f in os.listdir(sub_dir)
            if f.endswith(".md") and not f.startswith("_")
        )
        if files:
            sections[sub] = files

    lines = [
        "# Wiki Index — Farago Projects",
        "",
        f"Last updated: {today}",
        "",
        "---",
        "",
    ]

    for sub, type_data in entity_types.items():
        heading = type_data.get("name", sub.capitalize())
        lines.append(f"## {heading}")
        lines.append("")
        if sub in sections:
            for filename in sections[sub]:
                page_ref = f"{sub}/{filename[:-3]}"
                lines.append(f"- [[{page_ref}]] | last updated: {today}")
        else:
            lines.append(f"*No {sub} pages yet.*")
        lines.append("")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
```

Update `create_new_page()` to validate against dynamic types:

```python
async def create_new_page(self, entity_type: str = "clients") -> str:
    entity_types = self.get_entity_types()
    if entity_type not in entity_types:
        raise ValueError(f"Invalid entity type: {entity_type!r}. Must be one of {list(entity_types.keys())}")

    async with self._write_lock:
        sub_dir = os.path.join(self.wiki_dir, entity_type)
        os.makedirs(sub_dir, exist_ok=True)

        base_name = "Untitled"
        rel_path = f"{entity_type}/{base_name}.md"
        count = 1
        while os.path.exists(os.path.join(self.wiki_dir, rel_path.replace("/", os.sep))):
            rel_path = f"{entity_type}/{base_name}_{count}.md"
            count += 1

        singular = entity_types[entity_type].get("singular", entity_type.rstrip("s"))
        content = f"---\ntype: {singular}\nname: \n---\n\n# Untitled\n\nNew page content here.\n"
        with open(os.path.join(self.wiki_dir, rel_path.replace("/", os.sep)), "w", encoding="utf-8") as f:
            f.write(content)

        self.update_index()
        self._append_to_log("create", f"Created {rel_path}")
        return rel_path
```

Add `create_folder()`:

```python
async def create_folder(self, folder_name: str, display_name: str, description: str = ""):
    """Create a new entity folder with a _type.yaml file."""
    folder_path = os.path.join(self.wiki_dir, folder_name)
    if os.path.exists(folder_path):
        raise ValueError(f"Folder '{folder_name}' already exists")

    async with self._write_lock:
        os.makedirs(folder_path)
        type_data = {
            "name": display_name,
            "description": description,
            "singular": folder_name.rstrip("s"),
            "fields": [
                {"name": "type", "type": "string", "default": folder_name.rstrip("s")},
                {"name": "name", "type": "string", "required": True},
            ],
            "sections": ["Overview", "Notes"],
        }
        with open(os.path.join(folder_path, "_type.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(type_data, f, default_flow_style=False, sort_keys=False)

        self.rebuild_schema()
        self.update_index()
        self._append_to_log("create_folder", f"Created folder '{folder_name}' ({display_name})")
```

Add `delete_folder()`:

```python
async def delete_folder(self, folder_name: str):
    """Delete an empty entity folder."""
    folder_path = os.path.join(self.wiki_dir, folder_name)
    if not os.path.exists(folder_path):
        raise ValueError(f"Folder '{folder_name}' does not exist")

    # Check for pages (anything except _type.yaml and .gitkeep)
    contents = [f for f in os.listdir(folder_path) if f not in ("_type.yaml", ".gitkeep")]
    if contents:
        raise ValueError(f"Folder '{folder_name}' is not empty — archive or move pages first")

    async with self._write_lock:
        shutil.rmtree(folder_path)
        self.rebuild_schema()
        self.update_index()
        self._append_to_log("delete_folder", f"Deleted folder '{folder_name}'")
```

Add `rename_folder()`:

```python
async def rename_folder(self, old_name: str, new_name: str):
    """Rename an entity folder and update all wikilinks across the wiki."""
    old_path = os.path.join(self.wiki_dir, old_name)
    new_path = os.path.join(self.wiki_dir, new_name)
    if not os.path.exists(old_path):
        raise ValueError(f"Folder '{old_name}' does not exist")
    if os.path.exists(new_path):
        raise ValueError(f"Folder '{new_name}' already exists")

    async with self._write_lock:
        os.rename(old_path, new_path)
        self._rewrite_wikilinks(old_name, new_name)
        self.rebuild_schema()
        self.update_index()
        self._append_to_log("rename_folder", f"Renamed '{old_name}' → '{new_name}'")
```

Add `move_page()`:

```python
async def move_page(self, page_path: str, target_folder: str) -> str:
    """Move a wiki page to a different entity folder. Updates wikilinks.
    Returns the new page path.
    """
    target_dir = os.path.join(self.wiki_dir, target_folder)
    if not os.path.exists(target_dir) or not os.path.exists(os.path.join(target_dir, "_type.yaml")):
        raise ValueError(f"Target folder '{target_folder}' does not exist or has no _type.yaml")

    src = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
    if not os.path.exists(src):
        raise FileNotFoundError(f"Page not found: {page_path}")

    filename = os.path.basename(page_path)
    new_rel_path = f"{target_folder}/{filename}"
    dest = os.path.join(self.wiki_dir, new_rel_path.replace("/", os.sep))

    old_ref = page_path[:-3] if page_path.endswith(".md") else page_path
    new_ref = new_rel_path[:-3] if new_rel_path.endswith(".md") else new_rel_path

    async with self._write_lock:
        shutil.move(src, dest)
        self._rewrite_wikilinks_specific(old_ref, new_ref)
        self.update_index()
        self._append_to_log("move", f"Moved {page_path} → {new_rel_path}")

    return new_rel_path
```

Add wikilink rewriting helpers:

```python
def _rewrite_wikilinks(self, old_folder: str, new_folder: str):
    """Rewrite all [[old_folder/...]] wikilinks to [[new_folder/...]] across all pages."""
    pattern = re.compile(r"\[\[" + re.escape(old_folder) + r"/([^\]]+)\]\]")
    replacement = f"[[{new_folder}/\\1]]"
    for root, _dirs, files in os.walk(self.wiki_dir):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            new_content = pattern.sub(replacement, content)
            if new_content != content:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(new_content)

def _rewrite_wikilinks_specific(self, old_ref: str, new_ref: str):
    """Rewrite a specific [[old_ref]] wikilink to [[new_ref]] across all pages."""
    for root, _dirs, files in os.walk(self.wiki_dir):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            new_content = content.replace(f"[[{old_ref}]]", f"[[{new_ref}]]")
            if new_content != content:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(new_content)
```

Add `rebuild_schema()`:

```python
def rebuild_schema(self):
    """Regenerate SCHEMA.md from SCHEMA_TEMPLATE.md and _type.yaml files."""
    template_path = os.path.join(self.schema_dir, "SCHEMA_TEMPLATE.md")
    if not os.path.exists(template_path):
        return  # No template yet, skip
    schema_content = build_schema_md(self.wiki_dir, template_path)
    schema_path = os.path.join(self.schema_dir, "SCHEMA.md")
    with open(schema_path, "w", encoding="utf-8") as f:
        f.write(schema_content)
    # Reload system prompt so next LLM call sees updated schema
    self.system_prompt = self._load_system_prompt()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/test_folder_ops.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 5: Run existing tests to check for regressions**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/test_wiki_manager.py tests/test_api.py -v
```

Expected: Existing tests still pass. Some may need minor fixup if they relied on the old `ENTITY_SUBDIRS` constant — if so, fix them by adding `_type.yaml` files in the test fixtures.

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/backend/agent/wiki_manager.py Faragopedia-Sales/backend/tests/test_folder_ops.py
git commit -m "feat: add folder CRUD, page move, and dynamic schema rebuild to WikiManager"
```

---

## Task 4: Add API endpoints for folders and page move

Replace the hardcoded `VALID_ENTITY_SUBDIRS` in routes.py with dynamic discovery. Add REST endpoints for folder CRUD and page move.

**Files:**
- Modify: `Faragopedia-Sales/backend/api/routes.py`
- Modify: `Faragopedia-Sales/backend/tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `Faragopedia-Sales/backend/tests/test_api.py`:

```python
def test_get_entity_types_endpoint(client):
    with patch('api.routes.wiki_manager') as mock_wm:
        mock_wm.get_entity_types.return_value = {
            "clients": {"name": "Clients", "singular": "client"},
            "prospects": {"name": "Prospects", "singular": "prospect"},
        }
        response = client.get("/api/entity-types")
    assert response.status_code == 200
    data = response.json()
    assert "clients" in data


def test_create_folder_endpoint(client):
    with patch('api.routes.wiki_manager') as mock_wm:
        mock_wm.create_folder = AsyncMock()
        response = client.post("/api/folders", json={
            "name": "stylists",
            "display_name": "Stylists",
            "description": "Hair and makeup",
        })
    assert response.status_code in (200, 201)


def test_delete_folder_endpoint(client):
    with patch('api.routes.wiki_manager') as mock_wm:
        mock_wm.delete_folder = AsyncMock()
        response = client.delete("/api/folders/stylists")
    assert response.status_code in (200, 400)


def test_rename_folder_endpoint(client):
    with patch('api.routes.wiki_manager') as mock_wm:
        mock_wm.rename_folder = AsyncMock()
        response = client.put("/api/folders/clients", json={"new_name": "brands"})
    assert response.status_code in (200, 400)


def test_move_page_endpoint(client):
    with patch('api.routes.wiki_manager') as mock_wm:
        mock_wm.move_page = AsyncMock(return_value="prospects/test-brand.md")
        response = client.post("/api/pages/clients/test-brand.md/move", json={
            "target_folder": "prospects",
        })
    assert response.status_code in (200, 400)


def test_create_page_dynamic_entity_type(client):
    """Creating a page should accept any dynamically-registered folder."""
    with patch('api.routes.wiki_manager') as mock_wm:
        mock_wm.get_entity_types.return_value = {
            "clients": {"name": "Clients"},
            "stylists": {"name": "Stylists"},
        }
        mock_wm.create_new_page = AsyncMock(return_value="stylists/Untitled.md")
        response = client.post("/api/pages?entity_type=stylists")
    assert response.status_code in (200, 400, 500)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/test_api.py -v 2>&1 | tail -20
```

Expected: 404 for new endpoints, failures for dynamic entity type tests.

- [ ] **Step 3: Implement the route changes**

In `routes.py`, replace the hardcoded set:

```python
# Remove:
# VALID_ENTITY_SUBDIRS = {"clients", "prospects", "contacts", "photographers", "productions"}

# Add helper function:
def get_valid_entity_subdirs() -> set:
    """Get valid entity subdirectories dynamically from wiki_manager."""
    return set(wiki_manager.get_entity_types().keys())
```

Update `safe_wiki_filename()` to use dynamic lookup:

```python
def safe_wiki_filename(path: str) -> str:
    normalized = path.replace("\\", "/")
    if not normalized.endswith(".md"):
        raise ValueError(f"Invalid page path: {path!r} — must end with .md")
    parts = normalized.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid entity subdirectory in path: {path!r}")
    subdir, filename = parts
    if subdir not in get_valid_entity_subdirs():
        raise ValueError(f"Invalid entity subdirectory '{subdir}' in path: {path!r}")
    if ".." in filename or ".." in subdir:
        raise ValueError(f"Path traversal detected in: {path!r}")
    wiki_real = os.path.realpath(WIKI_DIR)
    resolved = os.path.realpath(os.path.join(wiki_real, subdir, filename))
    if os.name == "nt":
        if not resolved.lower().startswith(wiki_real.lower() + os.sep):
            raise ValueError(f"Path traversal detected in: {path!r}")
    else:
        if not resolved.startswith(wiki_real + os.sep):
            raise ValueError(f"Path traversal detected in: {path!r}")
    return normalized
```

Update `list_pages()` to use dynamic types:

```python
@router.get("/pages")
async def list_pages():
    try:
        all_pages = wiki_manager.list_pages()
        valid_subdirs = get_valid_entity_subdirs()
        grouped: Dict[str, List[str]] = {sub: [] for sub in valid_subdirs}
        for page_path in all_pages:
            parts = page_path.split("/")
            if len(parts) == 2 and parts[0] in valid_subdirs:
                grouped[parts[0]].append(page_path)
        return grouped
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing pages: {str(e)}")
```

Update `create_page()` to use dynamic validation:

```python
@router.post("/pages")
async def create_page(entity_type: str = Query("clients")):
    if entity_type not in get_valid_entity_subdirs():
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")
    try:
        filename = await wiki_manager.create_new_page(entity_type=entity_type)
        return {"filename": filename, "message": "New page created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating page: {str(e)}")
```

Add new endpoints:

```python
@router.get("/entity-types")
async def get_entity_types():
    try:
        return wiki_manager.get_entity_types()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing entity types: {str(e)}")


@router.post("/folders")
async def create_folder(payload: dict):
    name = payload.get("name", "").strip()
    display_name = payload.get("display_name", "").strip()
    description = payload.get("description", "").strip()
    if not name or not display_name:
        raise HTTPException(status_code=422, detail="name and display_name are required")
    if not re.match(r"^[a-z][a-z0-9-]*$", name):
        raise HTTPException(status_code=400, detail="Folder name must be lowercase alphanumeric with hyphens")
    try:
        await wiki_manager.create_folder(name, display_name, description)
        return {"message": f"Folder '{name}' created", "folder": name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating folder: {str(e)}")


@router.delete("/folders/{folder_name}")
async def delete_folder(folder_name: str):
    try:
        await wiki_manager.delete_folder(folder_name)
        return {"message": f"Folder '{folder_name}' deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting folder: {str(e)}")


@router.put("/folders/{folder_name}")
async def rename_folder(folder_name: str, payload: dict):
    new_name = payload.get("new_name", "").strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="new_name is required")
    if not re.match(r"^[a-z][a-z0-9-]*$", new_name):
        raise HTTPException(status_code=400, detail="Folder name must be lowercase alphanumeric with hyphens")
    try:
        await wiki_manager.rename_folder(folder_name, new_name)
        return {"message": f"Folder renamed: {folder_name} → {new_name}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renaming folder: {str(e)}")


@router.post("/pages/{path:path}/move")
async def move_page(path: str, payload: dict):
    try:
        safe_path = safe_wiki_filename(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    target_folder = payload.get("target_folder", "").strip()
    if not target_folder:
        raise HTTPException(status_code=422, detail="target_folder is required")
    try:
        new_path = await wiki_manager.move_page(safe_path, target_folder)
        return {"message": f"Page moved to {new_path}", "new_path": new_path}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error moving page: {str(e)}")
```

- [ ] **Step 4: Run all API tests**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/test_api.py -v
```

Expected: All tests PASS (old and new).

- [ ] **Step 5: Run full test suite for regressions**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add Faragopedia-Sales/backend/api/routes.py Faragopedia-Sales/backend/tests/test_api.py
git commit -m "feat: add folder CRUD, page move, and entity-types API endpoints"
```

---

## Task 5: Frontend — dynamic entity types and folder management UI

Replace the hardcoded `ENTITY_TYPES` array with data fetched from the API. Add UI for creating, renaming, and deleting folders in the sidebar.

**Files:**
- Modify: `Faragopedia-Sales/frontend/src/components/WikiView.tsx`

- [ ] **Step 1: Add state and fetch for dynamic entity types**

At the top of the WikiView component, replace the hardcoded array and add state:

```tsx
// Remove this line:
// const ENTITY_TYPES = ['clients', 'prospects', 'contacts', 'photographers', 'productions'];

// Add state:
const [entityTypes, setEntityTypes] = useState<Record<string, { name: string; description?: string; singular?: string }>>({});

// Add fetch function:
const fetchEntityTypes = async () => {
  try {
    const response = await fetch(`${API_BASE}/entity-types`);
    if (!response.ok) throw new Error('Failed to fetch entity types');
    const data = await response.json();
    setEntityTypes(data);
    // Initialize expanded state for any new sections
    setExpandedSections(prev => {
      const next = { ...prev };
      for (const key of Object.keys(data)) {
        if (!(key in next)) next[key] = true;
      }
      return next;
    });
  } catch (err: any) {
    setError(err.message);
  }
};
```

Update `useEffect` to fetch entity types:

```tsx
useEffect(() => {
  fetchEntityTypes();
  fetchPages();
  const handleResize = () => setIsDesktop(window.innerWidth >= 1024);
  window.addEventListener('resize', handleResize);
  return () => window.removeEventListener('resize', handleResize);
}, []);
```

Replace all `ENTITY_TYPES.map(...)` and `ENTITY_TYPES` references with `Object.keys(entityTypes)`.

Update `expandedSections` initial state to be empty (populated by fetchEntityTypes):

```tsx
const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
```

- [ ] **Step 2: Add folder management state and handlers**

```tsx
const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
const [newFolderName, setNewFolderName] = useState('');
const [newFolderDisplayName, setNewFolderDisplayName] = useState('');
const [newFolderDescription, setNewFolderDescription] = useState('');
const [renamingFolder, setRenamingFolder] = useState<string | null>(null);
const [renameFolderValue, setRenameFolderValue] = useState('');

const handleCreateFolder = async () => {
  if (!newFolderName.trim() || !newFolderDisplayName.trim()) return;
  try {
    const response = await fetch(`${API_BASE}/folders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newFolderName.trim().toLowerCase().replace(/\s+/g, '-'),
        display_name: newFolderDisplayName.trim(),
        description: newFolderDescription.trim(),
      }),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to create folder');
    }
    setShowNewFolderDialog(false);
    setNewFolderName('');
    setNewFolderDisplayName('');
    setNewFolderDescription('');
    await fetchEntityTypes();
    await fetchPages();
  } catch (err: any) {
    setError(err.message);
  }
};

const handleDeleteFolder = async (folderName: string) => {
  if (!window.confirm(`Delete the "${folderName}" folder? It must be empty.`)) return;
  try {
    const response = await fetch(`${API_BASE}/folders/${folderName}`, { method: 'DELETE' });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to delete folder');
    }
    await fetchEntityTypes();
    await fetchPages();
  } catch (err: any) {
    setError(err.message);
  }
};

const handleRenameFolder = async (oldName: string) => {
  if (!renameFolderValue.trim()) return;
  try {
    const response = await fetch(`${API_BASE}/folders/${oldName}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_name: renameFolderValue.trim().toLowerCase().replace(/\s+/g, '-') }),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to rename folder');
    }
    setRenamingFolder(null);
    setRenameFolderValue('');
    await fetchEntityTypes();
    await fetchPages();
    // If the currently selected page was in the renamed folder, update its path
    if (selectedPage?.startsWith(oldName + '/')) {
      const newPath = selectedPage.replace(oldName + '/', renameFolderValue.trim().toLowerCase().replace(/\s+/g, '-') + '/');
      setSelectedPage(newPath);
    }
  } catch (err: any) {
    setError(err.message);
  }
};
```

- [ ] **Step 3: Add move page state and handler**

```tsx
const [showMoveDialog, setShowMoveDialog] = useState(false);

const handleMovePage = async (targetFolder: string) => {
  if (!selectedPage) return;
  try {
    const response = await fetch(`${API_BASE}/pages/${encodeURIComponent(selectedPage)}/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_folder: targetFolder }),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to move page');
    }
    const data = await response.json();
    setSelectedPage(data.new_path);
    setShowMoveDialog(false);
    await fetchPages();
  } catch (err: any) {
    setError(err.message);
  }
};
```

- [ ] **Step 4: Update the sidebar JSX to use dynamic types and add folder management**

Add `FolderPlus`, `Pencil`, `Trash2` imports from lucide-react (Trash2 already imported, add FolderPlus and Pencil if not present).

Replace the sidebar's collapsible tree section:

```tsx
{/* Collapsible tree */}
{totalPageCount === 0 && Object.keys(entityTypes).length === 0 ? (
  <p className="text-gray-500 text-sm">No pages found. Ingest some data first!</p>
) : (
  <div className="space-y-1">
    {Object.entries(entityTypes).map(([section, typeData]) => {
      const sectionPages = pageTree[section] || [];
      return (
        <div key={section}>
          <div className="flex items-center group">
            <button
              onClick={() => toggleSection(section)}
              className="flex-1 text-left px-2 py-1.5 flex items-center justify-between text-xs font-semibold text-gray-400 uppercase tracking-wider hover:bg-gray-50 rounded-md transition-colors"
            >
              <span>{typeData.name || section}</span>
              <ChevronRight className={`w-3 h-3 transition-transform duration-150 ${expandedSections[section] ? 'rotate-90' : ''}`} />
            </button>
            <div className="hidden group-hover:flex items-center space-x-0.5 mr-1">
              <button
                onClick={() => { setRenamingFolder(section); setRenameFolderValue(section); }}
                className="p-0.5 text-gray-300 hover:text-gray-500 rounded"
                title="Rename folder"
              >
                <Pencil className="w-3 h-3" />
              </button>
              <button
                onClick={() => handleDeleteFolder(section)}
                className="p-0.5 text-gray-300 hover:text-red-500 rounded"
                title="Delete folder"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Inline rename input */}
          {renamingFolder === section && (
            <div className="flex items-center px-2 py-1 space-x-1">
              <input
                autoFocus
                value={renameFolderValue}
                onChange={e => setRenameFolderValue(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleRenameFolder(section);
                  if (e.key === 'Escape') setRenamingFolder(null);
                }}
                className="flex-1 text-xs border rounded px-2 py-1"
              />
              <button onClick={() => handleRenameFolder(section)} className="text-xs text-blue-600">Save</button>
              <button onClick={() => setRenamingFolder(null)} className="text-xs text-gray-400">Cancel</button>
            </div>
          )}

          {expandedSections[section] && sectionPages.length > 0 && (
            <ul className="ml-1 space-y-0.5 mb-1">
              {sectionPages.map(pagePath => (
                <li key={pagePath}>
                  <button
                    onClick={() => fetchPageContent(pagePath)}
                    className={`w-full text-left px-3 py-1.5 rounded-md text-sm transition-colors flex items-center ${
                      selectedPage === pagePath
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'hover:bg-gray-100 text-gray-700'
                    }`}
                  >
                    <FileText className="w-3.5 h-3.5 mr-2 flex-shrink-0 opacity-50" />
                    <span className="break-words line-clamp-2">
                      {pagePath.split('/').pop()?.replace('.md', '').replace(/-/g, ' ')}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      );
    })}
  </div>
)}
```

- [ ] **Step 5: Add "New Folder" button and dialog below the "New Page" button**

Add a "New Folder" button next to the "New Page" button in the sidebar header:

```tsx
<div className="flex items-center justify-between mb-4">
  <h2 className="text-lg font-semibold">Pages</h2>
  <div className="flex items-center space-x-1">
    {/* New Folder */}
    <button
      onClick={() => setShowNewFolderDialog(true)}
      className="p-1.5 bg-gray-50 text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
      title="New Folder"
    >
      <FolderPlus className="w-4 h-4" />
    </button>
    {/* New Page */}
    <div className="relative">
      <button
        onClick={() => setShowNewPageMenu(prev => !prev)}
        disabled={isCreating}
        className="p-1.5 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors disabled:opacity-50"
        title="New Page"
      >
        {isCreating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
      </button>
      {showNewPageMenu && (
        <div className="absolute right-0 mt-1 w-44 bg-white rounded-lg shadow-lg border border-gray-100 z-20 overflow-hidden">
          {Object.entries(entityTypes).map(([type, data]) => (
            <button
              key={type}
              onClick={() => handleNewPage(type)}
              className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700 transition-colors"
            >
              {data.name || type}
            </button>
          ))}
        </div>
      )}
    </div>
  </div>
</div>
```

Add the new folder dialog (just before the closing `</div>` of the sidebar):

```tsx
{showNewFolderDialog && (
  <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setShowNewFolderDialog(false)}>
    <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm space-y-4" onClick={e => e.stopPropagation()}>
      <h3 className="text-lg font-semibold">New Folder</h3>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
        <input
          autoFocus
          value={newFolderDisplayName}
          onChange={e => {
            setNewFolderDisplayName(e.target.value);
            setNewFolderName(e.target.value.toLowerCase().replace(/\s+/g, '-'));
          }}
          className="w-full border rounded-lg px-3 py-2 text-sm"
          placeholder="e.g. Stylists"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Folder ID</label>
        <input
          value={newFolderName}
          onChange={e => setNewFolderName(e.target.value)}
          className="w-full border rounded-lg px-3 py-2 text-sm text-gray-500"
          placeholder="e.g. stylists"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Description (for AI context)</label>
        <input
          value={newFolderDescription}
          onChange={e => setNewFolderDescription(e.target.value)}
          className="w-full border rounded-lg px-3 py-2 text-sm"
          placeholder="e.g. Hair and makeup stylists we work with"
        />
      </div>
      <div className="flex justify-end space-x-2">
        <button onClick={() => setShowNewFolderDialog(false)} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">Cancel</button>
        <button
          onClick={handleCreateFolder}
          disabled={!newFolderName.trim() || !newFolderDisplayName.trim()}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          Create
        </button>
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 6: Add "Move to..." button in the page action bar and move dialog**

In the desktop navigation header, add a move button next to download:

```tsx
<button
  onClick={() => setShowMoveDialog(true)}
  className="p-1.5 text-gray-500 hover:bg-gray-100 rounded-md transition-colors"
  title="Move to folder..."
>
  <ArrowRight className="w-5 h-5" />
</button>
```

Add the move dialog (render it at the bottom of the component, before `{error && ...}`):

```tsx
{showMoveDialog && selectedPage && (
  <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setShowMoveDialog(false)}>
    <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-xs space-y-3" onClick={e => e.stopPropagation()}>
      <h3 className="text-lg font-semibold">Move to...</h3>
      <p className="text-sm text-gray-500">Move "{selectedPage.split('/').pop()?.replace('.md', '').replace(/-/g, ' ')}" to:</p>
      <div className="space-y-1">
        {Object.entries(entityTypes)
          .filter(([key]) => key !== selectedPage.split('/')[0])
          .map(([key, data]) => (
            <button
              key={key}
              onClick={() => handleMovePage(key)}
              className="w-full text-left px-4 py-2 text-sm rounded-lg hover:bg-blue-50 hover:text-blue-700 transition-colors"
            >
              {data.name || key}
            </button>
          ))}
      </div>
      <button onClick={() => setShowMoveDialog(false)} className="w-full text-center text-sm text-gray-400 hover:text-gray-600 mt-2">Cancel</button>
    </div>
  </div>
)}
```

- [ ] **Step 7: Test in browser**

```bash
cd Faragopedia-Sales/frontend && npm run dev
```

Test:
1. Sidebar loads with dynamic entity types (same 5 as before)
2. "New Folder" button opens dialog, can create a folder (e.g. "stylists")
3. New folder appears in sidebar
4. Can rename a folder via hover icons
5. Can delete an empty folder
6. Can create a new page in the new folder
7. Can move a page between folders
8. All existing functionality (edit, save, delete, backlinks, chat) still works

- [ ] **Step 8: Commit**

```bash
git add Faragopedia-Sales/frontend/src/components/WikiView.tsx
git commit -m "feat: dynamic entity types in sidebar with folder create/rename/delete and page move UI"
```

---

## Task 6: Regenerate SCHEMA.md from template + seed data

Wire everything together: run the schema builder once to regenerate SCHEMA.md from the template and the five seed `_type.yaml` files. Verify the output matches the original schema's intent.

**Files:**
- Modify: `Wiki-Concept/SCHEMA.md` (auto-generated)

- [ ] **Step 1: Write a one-off script to regenerate**

```bash
cd Faragopedia-Sales/backend && python -c "
from agent.schema_builder import build_schema_md
import os
wiki_dir = os.path.abspath('../../Wiki-Concept')
template = os.path.join(wiki_dir, 'SCHEMA_TEMPLATE.md')
result = build_schema_md(wiki_dir, template)
schema_path = os.path.join(wiki_dir, 'SCHEMA.md')
with open(schema_path, 'w') as f:
    f.write(result)
print('SCHEMA.md regenerated successfully')
print(f'Length: {len(result)} chars')
"
```

- [ ] **Step 2: Review the generated SCHEMA.md**

Read the file and confirm:
- Directory structure lists all 5 entity types
- Page schemas section has all 5 types with correct YAML frontmatter
- Operations section is intact
- General rules reference `_type.yaml`
- No `{{...}}` template placeholders remain

- [ ] **Step 3: Run full test suite**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add Wiki-Concept/SCHEMA.md Wiki-Concept/SCHEMA_TEMPLATE.md
git commit -m "feat: regenerate SCHEMA.md from template and _type.yaml seed files"
```

---

## Task 7: End-to-end integration test

Verify the full flow works: create a folder, move a page into it, confirm schema rebuilds, and confirm the AI (mocked) sees the updated schema.

**Files:**
- Create: `Faragopedia-Sales/backend/tests/test_dynamic_folders_e2e.py`

- [ ] **Step 1: Write the integration test**

```python
import os
import pytest
import yaml
from unittest.mock import patch, MagicMock, AsyncMock

from agent.wiki_manager import WikiManager
from agent.schema_builder import discover_entity_types


@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test_key",
        "AI_PROVIDER": "openai",
        "AI_MODEL": "gpt-4o-mini",
    }):
        yield


@pytest.fixture
def full_wiki(tmp_path):
    """Set up a complete wiki with schema template, company profile, and one entity folder."""
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "company_profile.md").write_text("# Farago Projects\nA creative production house.")
    (schema_dir / "SCHEMA_TEMPLATE.md").write_text(
        "# SCHEMA.md\n\n## Directory Structure\n\n"
        "{{ENTITY_TYPES_DIRECTORY}}\n\n"
        "## Page Schemas\n\n{{ENTITY_TYPES_SCHEMAS}}\n\n"
        "## Operations\n\nIngest, query, lint.\n"
    )
    # Initial SCHEMA.md (will be regenerated)
    (schema_dir / "SCHEMA.md").write_text("# Schema placeholder")

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    sources = tmp_path / "sources"
    sources.mkdir()

    # One seed folder
    clients = wiki / "clients"
    clients.mkdir()
    (clients / "_type.yaml").write_text(yaml.dump({
        "name": "Clients",
        "description": "Active client brands",
        "singular": "client",
        "fields": [
            {"name": "type", "type": "string", "default": "client"},
            {"name": "name", "type": "string", "required": True},
        ],
        "sections": ["Overview"],
    }))
    (clients / "test-brand.md").write_text(
        "---\ntype: client\nname: Test Brand\n---\n# Test Brand\n\n## Overview\n\nA test brand.\n"
    )

    with patch('agent.wiki_manager.WikiManager._init_llm', return_value=MagicMock()):
        mgr = WikiManager(
            sources_dir=str(sources),
            wiki_dir=str(wiki),
            archive_dir=str(tmp_path / "archive"),
            schema_dir=str(schema_dir),
        )
    return mgr


@pytest.mark.asyncio
async def test_full_flow_create_folder_move_page_schema_updates(full_wiki):
    mgr = full_wiki

    # 1. Create a new folder
    await mgr.create_folder("prospects", "Prospects", "Pipeline targets")

    # Verify folder exists with _type.yaml
    prospects_dir = os.path.join(mgr.wiki_dir, "prospects")
    assert os.path.isdir(prospects_dir)
    assert os.path.exists(os.path.join(prospects_dir, "_type.yaml"))

    # 2. Verify schema was rebuilt
    schema_path = os.path.join(mgr.schema_dir, "SCHEMA.md")
    with open(schema_path) as f:
        schema = f.read()
    assert "prospects/" in schema
    assert "Pipeline targets" in schema

    # 3. Verify system_prompt was reloaded (includes new schema)
    assert "prospects/" in mgr.system_prompt or "Prospects" in mgr.system_prompt

    # 4. Move a page from clients to prospects
    new_path = await mgr.move_page("clients/test-brand.md", "prospects")
    assert new_path == "prospects/test-brand.md"
    assert os.path.exists(os.path.join(mgr.wiki_dir, "prospects", "test-brand.md"))
    assert not os.path.exists(os.path.join(mgr.wiki_dir, "clients", "test-brand.md"))

    # 5. Verify index was updated
    index_path = os.path.join(mgr.wiki_dir, "index.md")
    with open(index_path) as f:
        index = f.read()
    assert "[[prospects/test-brand]]" in index
    assert "[[clients/test-brand]]" not in index

    # 6. Verify dynamic entity type discovery
    types = mgr.get_entity_types()
    assert "clients" in types
    assert "prospects" in types

    # 7. Delete the now-empty clients folder
    await mgr.delete_folder("clients")
    assert not os.path.exists(os.path.join(mgr.wiki_dir, "clients"))
    types_after = mgr.get_entity_types()
    assert "clients" not in types_after

    # 8. Verify schema no longer includes clients
    with open(schema_path) as f:
        schema_after = f.read()
    assert "clients/" not in schema_after
```

- [ ] **Step 2: Run the test**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/test_dynamic_folders_e2e.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full test suite one final time**

```bash
cd Faragopedia-Sales/backend && python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add Faragopedia-Sales/backend/tests/test_dynamic_folders_e2e.py
git commit -m "test: add end-to-end integration test for dynamic folders flow"
```

---

## Summary of changes by layer

| Layer | What changed | Why |
|-------|-------------|-----|
| **Wiki-Concept/** | Added `_type.yaml` per folder, `SCHEMA_TEMPLATE.md`, SCHEMA.md is now auto-generated | Folder metadata drives the entire system |
| **schema_builder.py** | New module: reads `_type.yaml`, assembles SCHEMA.md | Single source of truth for type discovery |
| **wiki_manager.py** | Dynamic `ENTITY_SUBDIRS`, folder CRUD, page move, wikilink rewriting, schema rebuild | Core operations now respect dynamic types |
| **routes.py** | Dynamic validation, new endpoints for folders/move/entity-types | Frontend can manage folders via API |
| **WikiView.tsx** | Dynamic sidebar, folder create/rename/delete UI, page move dialog | User-facing folder management |
