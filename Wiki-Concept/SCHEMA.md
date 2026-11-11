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
├── clients/  # Active client brands and fashion houses
│   └── [client-name].md
├── contacts/  # Individual people across all organisations
│   └── [contact-name].md
├── photographers/  # Photographer roster and potential collaborators
│   └── [photographer-name].md
├── productions/  # Individual shoot, project, or event pages
│   └── [production-name].md
├── prospects/  # Pipeline and potential clients or publications being actively pursued
│   └── [prospect-name].md
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

### clients/[client-name].md

*Active client brands and fashion houses*

```yaml
---
type: client
name:
industry:
tier: A | B | C          # A = active/high value, B = occasional, C = cold
status: active | inactive
hq:
relationship_since:
last_contact:
source_count:
---
```

Sections: `## Overview` · `## Key Contacts` · `## Production History` · `## Relationship Notes` · `## Open Opportunities` · `## Sources`

---
### contacts/[contact-name].md

*Individual people across all organisations*

```yaml
---
type: contact
name:
role:
org:
linked_orgs: []
last_contact:
---
```

Sections: `## Bio` · `## Role & Responsibilities` · `## Relationship History` · `## Productions Involved` · `## Notes`

---
### photographers/[photographer-name].md

*Photographer roster and potential collaborators*

```yaml
---
type: photographer
name:
tier: A | B | C          # A = frequent collaborator, B = occasional, C = one-off/prospect
representation:
based:
speciality: []
---
```

Sections: `## Bio` · `## Style Notes` · `## Productions` · `## Client Relationships` · `## Availability Notes` · `## Sources`

---
### productions/[production-name].md

*Individual shoot, project, or event pages*

```yaml
---
entity_type: production
date:
client:
publication:
photographer:
location:
work_type: editorial | advertising | lookbook | show | event
status: complete | in-progress | pitched
---
```

Sections: `## Brief` · `## Team` · `## Outcome & Notes` · `## Sources`

---
### prospects/[prospect-name].md

*Pipeline and potential clients or publications being actively pursued*

```yaml
---
type: prospect
name:
industry:
tier: A | B | C          # A = high priority, B = medium, C = low/watch
status: prospect | target
hq:
last_contact:
source_count:
---
```

Sections: `## Overview` · `## Key Contacts` · `## Why Farago` · `## Outreach History` · `## Open Opportunities` · `## Sources`

---

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
