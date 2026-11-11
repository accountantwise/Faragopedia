import json
import os
import re

import yaml
from pydantic import BaseModel, field_validator
from agent.schema_builder import build_schema_md, write_entity_templates


# ── Pydantic models (shared with setup_routes.py via import) ──────────────────

class EntityTypeField(BaseModel):
    name: str
    type: str  # string | date | integer | enum | list
    default: str | None = None
    required: bool | None = None
    values: list[str] | None = None
    description: str | None = None


class EntityTypeDefinition(BaseModel):
    folder_name: str
    display_name: str
    description: str
    singular: str
    fields: list[EntityTypeField]
    sections: list[str]

    @field_validator("folder_name")
    @classmethod
    def folder_name_slug(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9-]*$", v):
            raise ValueError("folder_name must be lowercase alphanumeric with hyphens")
        return v


class SuggestedSchema(BaseModel):
    entity_types: list[EntityTypeDefinition]


class SuggestRequest(BaseModel):
    org_name: str
    org_description: str


class SetupPayload(BaseModel):
    wiki_name: str
    org_name: str
    org_description: str
    entity_types: list[EntityTypeDefinition]


BASE_SCHEMA_TEMPLATE = """\
# SCHEMA.md — {{ORG_NAME}} LLM Wiki

This file is the operating manual for the LLM wiki agent. Read it at the start of every session before taking any action.

---

## Identity

You are the wiki agent for {{ORG_NAME}}. {{ORG_DESCRIPTION}}

Your role: maintain a persistent, compounding knowledge base. You write and maintain all wiki pages. The human curates sources and directs analysis.

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
├── index.md               # Master catalog of all wiki pages
├── log.md                 # Append-only chronological log
├── company_profile.md     # Organisation profile (IMMUTABLE — never modify)
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

---

## Page Schemas

All wiki pages use YAML frontmatter for Obsidian Dataview compatibility. Use wikilink syntax (`[[page-name]]`) for all cross-references.

{{ENTITY_TYPES_SCHEMAS}}

## Operations

### Ingest
**Trigger:** User says "ingest [source]" or "ingest [filename]"

1. Read the source file from `sources/`
2. Discuss key takeaways with the user
3. Create or update all touched entity pages — check the Directory Structure above for available folders
4. Update `index.md` — add any new pages, update summaries of changed pages
5. Append to `log.md`: `## [YYYY-MM-DD] ingest | [source title]` followed by a 2–3 line summary of what was updated

A single source may touch 5–15 wiki pages. Update all of them.

---

### Query
**Trigger:** Any question about any entity in the wiki

1. Read `index.md` to identify the most relevant pages
2. Read those pages in full
3. Synthesize a clear answer with inline wikilink citations (`[[page-name]]`)
4. If the answer is valuable enough to keep, offer to file it as a new wiki page
5. Append to `log.md`: `## [YYYY-MM-DD] query | [topic]`

---

### Lint
**Trigger:** User says "lint"

1. Read all pages listed in `index.md`
2. Scan for orphan pages, contradictions, missing entities, data gaps
3. Append to `log.md`: `## [YYYY-MM-DD] lint | [brief summary of findings]`

---

## General Rules

1. **Never modify** `sources/` or `company_profile.md`
2. **Always use wikilinks** — cite cross-references as `[[page-name]]` not plain text
3. **Prefer updating over creating** — update an existing page before creating a new one
4. **Keep index.md current** — update it on every ingest operation
5. **Keep log.md current** — append an entry on every ingest, query, and lint operation
6. **Frontmatter always** — every wiki page must have valid YAML frontmatter matching its schema
7. **File naming** — lowercase, hyphen-separated: `acme-corp.md`, `jane-smith.md`
"""


def is_setup_complete(schema_dir: str) -> bool:
    return os.path.exists(os.path.join(schema_dir, "wiki_config.json"))


def get_wiki_config(schema_dir: str) -> dict | None:
    path = os.path.join(schema_dir, "wiki_config.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_existing(schema_dir: str) -> None:
    config_path = os.path.join(schema_dir, "wiki_config.json")
    profile_path = os.path.join(schema_dir, "company_profile.md")
    if os.path.exists(profile_path) and not os.path.exists(config_path):
        config = {
            "wiki_name": "Faragopedia",
            "org_name": "Farago Projects",
            "setup_complete": True,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)


def get_existing_folders(wiki_dir: str) -> list[str]:
    """Scan wiki_dir for valid entity folders (containing _type.yaml)."""
    folders = []
    if os.path.isdir(wiki_dir):
        for entry in sorted(os.listdir(wiki_dir)):
            full = os.path.join(wiki_dir, entry)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, "_type.yaml")):
                folders.append(entry)
    return folders


def clear_setup(schema_dir: str, wiki_dir: str) -> list[str]:
    config_path = os.path.join(schema_dir, "wiki_config.json")
    if os.path.exists(config_path):
        os.remove(config_path)
    return get_existing_folders(wiki_dir)


def complete_setup(schema_dir: str, wiki_dir: str, payload) -> None:
    """Write all config files from a validated SetupPayload. Returns None; caller builds WikiManager."""
    # 1. Write company_profile.md
    profile_path = os.path.join(schema_dir, "company_profile.md")
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(f"# {payload.org_name}\n\n{payload.org_description}\n")

    # 2. Write SCHEMA_TEMPLATE.md from BASE_SCHEMA_TEMPLATE
    template_content = (
        BASE_SCHEMA_TEMPLATE
        .replace("{{ORG_NAME}}", payload.org_name)
        .replace("{{ORG_DESCRIPTION}}", payload.org_description)
    )
    template_path = os.path.join(schema_dir, "SCHEMA_TEMPLATE.md")
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(template_content)

    # 3. Create entity folders and write _type.yaml per entity type
    for et in payload.entity_types:
        folder_path = os.path.join(wiki_dir, et.folder_name)
        os.makedirs(folder_path, exist_ok=True)
        type_data = {
            "name": et.display_name,
            "description": et.description,
            "singular": et.singular,
            "fields": [_field_to_dict(f) for f in et.fields],
            "sections": et.sections,
        }
        yaml_path = os.path.join(folder_path, "_type.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(type_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # 4b. Write _template.md for each entity type
    entity_type_dicts = [
        {
            "folder_name": et.folder_name,
            "singular": et.singular,
            "fields": [_field_to_dict(f) for f in et.fields],
            "sections": et.sections,
        }
        for et in payload.entity_types
    ]
    write_entity_templates(wiki_dir, entity_type_dicts)

    # 4. Build SCHEMA.md
    schema_md = build_schema_md(wiki_dir, template_path)
    with open(os.path.join(schema_dir, "SCHEMA.md"), "w", encoding="utf-8") as f:
        f.write(schema_md)

    # 5. Write wiki_config.json
    config = {
        "wiki_name": payload.wiki_name,
        "org_name": payload.org_name,
        "setup_complete": True,
    }
    with open(os.path.join(schema_dir, "wiki_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def finalize_import(schema_dir: str, wiki_dir: str, payload) -> None:
    """Finalise an import: create entity folders and write wiki_config.json.
    Does NOT touch SCHEMA.md or company_profile.md — import step already placed them.
    """
    for et in payload.entity_types:
        folder_path = os.path.join(wiki_dir, et.folder_name)
        os.makedirs(folder_path, exist_ok=True)
        type_data = {
            "name": et.display_name,
            "description": et.description,
            "singular": et.singular,
            "fields": [_field_to_dict(f) for f in et.fields],
            "sections": et.sections,
        }
        yaml_path = os.path.join(folder_path, "_type.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(type_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    config = {
        "wiki_name": payload.wiki_name,
        "org_name": payload.org_name,
        "setup_complete": True,
    }
    with open(os.path.join(schema_dir, "wiki_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def suggest_schema_llm(org_name: str, org_description: str, llm) -> SuggestedSchema:
    from langchain_core.output_parsers import PydanticOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    parser = PydanticOutputParser(pydantic_object=SuggestedSchema)

    system = (
        "You are a wiki schema designer. Given a description of an organisation, "
        "design the entity types that the wiki should track. Each entity type becomes a folder.\n\n"
        "Rules:\n"
        "- 3–7 entity types; fewer is better\n"
        "- Each field must have name and type (string | date | integer | enum | list)\n"
        "- Enum fields must have a values list\n"
        "- folder_name must be plural, lowercase, hyphen-separated (e.g. 'project-clients')\n"
        "- singular is the lowercase singular form\n"
        "- Every entity type must have a 'name' field (type: string, required: true) as the first field\n"
        "- Sections are markdown heading names for the page template\n"
    )
    human = (
        "Organisation: {org_name}\nDescription: {org_description}\n\n"
        "Design the wiki entity types for this organisation.\n{format_instructions}"
    )

    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])
    chain = prompt | llm | parser
    return chain.invoke({
        "org_name": org_name,
        "org_description": org_description,
        "format_instructions": parser.get_format_instructions(),
    })


def _field_to_dict(field) -> dict:
    d: dict = {"name": field.name, "type": field.type}
    if field.required is not None:
        d["required"] = field.required
    if field.values is not None:
        d["values"] = field.values
    if field.default is not None:
        d["default"] = field.default
    if field.description is not None:
        d["description"] = field.description
    return d
