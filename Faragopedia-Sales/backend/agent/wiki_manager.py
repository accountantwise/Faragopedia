import os
import asyncio
import datetime
import re
import json
import shutil
import yaml
import zipfile
from pydantic import BaseModel, Field
from typing import List, Dict, Literal
from agent.schema_builder import discover_entity_types, build_schema_md, bootstrap_type_yamls
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import Runnable

class _LLMProxy(Runnable):
    """Thin ``Runnable`` wrapper around a LangChain LLM.

    Inheriting from ``Runnable`` (not from Pydantic's ``BaseModel``) means
    instance attributes like ``ainvoke`` can be freely replaced in tests
    via simple assignment while still being recognised by LangChain chains
    (``prompt | self.llm | parser``).

    Attribute access falls through to the wrapped LLM so that callers can
    read provider-specific attributes (e.g. ``model_name``) transparently.
    """

    def __init__(self, llm):
        self._llm = llm

    # ── Runnable interface ────────────────────────────────────────────────

    def invoke(self, input, config=None, **kwargs):
        return self._llm.invoke(input, config, **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        return await self._llm.ainvoke(input, config, **kwargs)

    # ── Transparent attribute delegation ─────────────────────────────────

    def __getattr__(self, name):
        # Called only when the attribute is NOT found on the proxy itself,
        # so instance-level overrides (e.g. mock replacements) take priority.
        return getattr(self._llm, name)


class WikiPage(BaseModel):
    path: str = Field(description="Relative path for the wiki page, e.g. 'clients/louis-vuitton.md'")
    content: str = Field(description="Full markdown content including YAML frontmatter and all sections")
    action: str = Field(description="'create' for new pages, 'update' for existing pages")

class FaragoIngestionResult(BaseModel):
    pages: List[WikiPage] = Field(description="All wiki pages to create or update")
    log_entry: str = Field(description="2-3 line summary of what was ingested, for log.md")

class LintFinding(BaseModel):
    severity: str = Field(description="'error', 'warning', or 'suggestion'")
    page: str = Field(description="Affected page path (e.g. 'clients/louis-vuitton.md') or 'global'")
    description: str = Field(description="Description of the issue or suggestion")
    fix_confidence: Literal["full", "stub", "needs_source"] = Field(default="stub", description="'full' (LLM can resolve from existing context), 'stub' (LLM creates a starting-point), or 'needs_source' (requires ingesting new source material first)")
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


# Split so the (largely stable, often-reused) wiki-context portion can carry
# a prompt-caching breakpoint separately from the (always-different) source
# document and instructions. Concatenated with "\n\n" these reproduce the
# original single-block template byte-for-byte.
INGEST_HUMAN_TEMPLATE_PREFIX = """You are ingesting a new source document into the Farago Projects wiki.

Current wiki index:
{index_content}

Existing pages that may need updating:
{existing_pages}"""

INGEST_HUMAN_TEMPLATE_SUFFIX = """Source document filename: {filename}
Source document content:
{source_content}

Instructions:
1. Identify all entities in the source that match the Farago schema. Available entity folders: {entity_types}.
2. For each entity, produce a complete wiki page with valid YAML frontmatter matching the schema for that entity type.
3. Use the exact file path format: "clients/brand-name.md", "photographers/first-last.md", "productions/YYYY-MM-client-description.md", etc.
4. File names must be lowercase and hyphen-separated.
5. For existing pages (action="update"), produce the full merged content.
6. For new pages (action="create"), produce the full page with all schema sections.
7. Always use [[subdir/page-name]] wikilink syntax for cross-references.
8. Write a 2-3 line log_entry summarising what was ingested."""

RELEVANCE_HUMAN_TEMPLATE = """Given the wiki index below, list the 3-5 most relevant page paths to answer the user query.
Return ONLY a comma-separated list of relative page paths (e.g. 'clients/louis-vuitton.md, contacts/jane-doe.md').
If nothing is relevant, return 'None'.

Wiki index:
{index}

Query: {query}"""

ANSWER_HUMAN_TEMPLATE = """Answer the user query using the provided wiki context.
Cite sources using [[subdir/page-name]] wikilink syntax.
If the context doesn't contain the answer, say so.

Context:
{context}

Query: {query}"""

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

Return at most 30 findings total, prioritising errors first, then warnings, then suggestions."""

FIX_HUMAN_TEMPLATE = """You are applying selected lint fixes to the Farago Projects wiki.

All current wiki pages:
{wiki_content}

Selected findings to fix (each entry shows: index. [CONFIDENCE] description (page: path) / Fix: fix_description):
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
9. Write a one-line summary (e.g. "Fixed 3 findings: updated 2 pages, created 1 stub")."""


class WikiManager:
    def __init__(self, sources_dir="sources", wiki_dir="wiki", archive_dir="archive", snapshots_dir="snapshots", llm=None, schema_dir=None):
        self.sources_dir = sources_dir
        self.wiki_dir = wiki_dir
        self.archive_dir = archive_dir
        self.archive_wiki_dir = os.path.join(archive_dir, "wiki")
        self.archive_sources_dir = os.path.join(archive_dir, "sources")
        self.snapshots_dir = snapshots_dir
        self.metadata_path = os.path.join(sources_dir, ".metadata.json")
        self.page_metadata_path = os.path.join(self.wiki_dir, ".page-metadata.json")
        self.schema_dir = schema_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "schema"
        )
        self.system_prompt = self._load_system_prompt()
        self.llm = llm if llm else self._init_llm()
        self.ingest_llm = llm if llm else self._init_llm("ingest")
        self.chat_llm = llm if llm else self._init_llm("chat")
        self._write_lock = asyncio.Lock()

        for d in [self.sources_dir, self.wiki_dir, self.archive_dir,
                  self.archive_wiki_dir, self.archive_sources_dir, self.snapshots_dir]:
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)

        bootstrap_type_yamls(self.wiki_dir)
        try:
            self.rebuild_schema()
        except FileNotFoundError:
            pass  # No SCHEMA_TEMPLATE.md yet — schema_dir not fully set up

        # Build search index on startup if missing
        index_path = os.path.join(self.wiki_dir, "search-index.json")
        if not os.path.exists(index_path):
            self._rebuild_search_index()

    def _load_system_prompt(self) -> str:
        schema_path = os.path.join(self.schema_dir, "SCHEMA.md")
        profile_path = os.path.join(self.schema_dir, "company_profile.md")
        if not os.path.exists(schema_path) or not os.path.exists(profile_path):
            return "Wiki not yet configured. Setup required."
        with open(schema_path, "r", encoding="utf-8", errors="replace") as f:
            schema = f.read()
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = f.read()
        return f"{schema}\n\n---\n\n{profile}"

    def _init_llm(self, operation: str = None):
        prefix = f"{operation.upper()}_" if operation else ""
        provider = (os.getenv(f"{prefix}AI_PROVIDER") or os.getenv("AI_PROVIDER", "openai")).lower()
        model = os.getenv(f"{prefix}AI_MODEL") or os.getenv("AI_MODEL", "gpt-4o-mini")

        if provider == "openai":
            llm = ChatOpenAI(model=model)
        elif provider == "anthropic":
            llm = ChatAnthropic(model=model)
        elif provider == "google":
            llm = ChatGoogleGenerativeAI(model=model)
        elif provider == "openrouter":
            llm = ChatOpenAI(
                model=model,
                openai_api_base="https://openrouter.ai/api/v1",
                openai_api_key=os.getenv("OPENROUTER_API_KEY")
            )
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")
        return _LLMProxy(llm)

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        match = re.match(r'^---\n(.*?)\n---\n?(.*)', content, re.DOTALL)
        if match:
            try:
                fm = yaml.safe_load(match.group(1))
                if not isinstance(fm, dict):
                    fm = {}
            except yaml.YAMLError:
                fm = {}
            return fm, match.group(2)
        return {}, content

    def _render_frontmatter(self, frontmatter: dict, body: str) -> str:
        class _WikilinkSafeDumper(yaml.Dumper):
            pass

        def _str_representer(dumper, data):
            if '\n' in data:
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            # Force double-quote style for wikilinks so [[Name]] is never
            # single-quote escaped to '[[Name]]' or '[[L''Oreal]]'
            if data.startswith('[['):
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)

        _WikilinkSafeDumper.add_representer(str, _str_representer)

        fm_str = yaml.dump(frontmatter, Dumper=_WikilinkSafeDumper, default_flow_style=False,
                           allow_unicode=True, sort_keys=False).rstrip()
        return f"---\n{fm_str}\n---\n{body}"

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a name to a slug suitable for filenames.
        Lowercase, hyphen-separated, alphanumeric + hyphens only.
        Returns 'untitled' for empty or non-alphanumeric-only strings.
        """
        slug = name.lower().strip()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')
        return slug or "untitled"

    def _strip_markdown(self, text: str) -> str:
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'[*_`~]', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _rebuild_search_index(self) -> None:
        pages = []
        for rel_path in self.list_pages():
            try:
                content = self.get_page_content(rel_path)
                fm, body = self._parse_frontmatter(content)
                entity_type = rel_path.split("/")[0]
                title = fm.get("name") or fm.get("title") or \
                    rel_path.split("/")[-1].replace("-", " ").replace("_", " ").title()
                tags = fm.get("tags", [])
                if not isinstance(tags, list):
                    tags = []
                def _json_safe(v):
                    if isinstance(v, (datetime.date, datetime.datetime)):
                        return v.isoformat()
                    return v

                pages.append({
                    "path": rel_path,
                    "title": str(title),
                    "entity_type": entity_type,
                    "tags": [str(t) for t in tags],
                    "frontmatter": {k: _json_safe(v) for k, v in fm.items() if k != "tags"},
                    "content_preview": self._strip_markdown(body)[:500],
                })
            except Exception:
                continue

        raw_meta = self._load_metadata()
        sources = []
        for filename in self.list_sources():
            m = raw_meta.get(filename, {})
            tags = m.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            sources.append({
                "filename": filename,
                "display_name": filename,
                "tags": [str(t) for t in tags],
                "metadata": {
                    "ingested": m.get("ingested", False),
                    "upload_date": m.get("ingested_at"),
                },
            })

        index = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "pages": pages,
            "sources": sources,
        }
        import tempfile
        index_path = os.path.join(self.wiki_dir, "search-index.json")
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.wiki_dir)
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                json.dump(index, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, index_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        self._rebuild_index_md(pages, index["generated_at"])

    def _rebuild_index_md(self, pages: list[dict], generated_at: str) -> None:
        """Write wiki/_meta/index.md from the in-memory pages list.

        Called immediately after search-index.json is written so both files
        share the same page data without extra I/O. `pages` is the list of
        page dicts built in `_rebuild_search_index()`; `generated_at` is the
        ISO-8601 UTC timestamp from the index header.
        """
        meta_dir = os.path.join(self.wiki_dir, "_meta")
        os.makedirs(meta_dir, exist_ok=True)

        by_type: dict = {}
        for page in pages:
            by_type.setdefault(page["entity_type"], []).append(page)

        lines = [
            "---",
            "system: true",
            f"generated_at: {generated_at}",
            "---",
            "",
            "# Wiki Index",
            "",
            "## By Type",
            "",
        ]

        for et in sorted(by_type.keys()):
            heading = et.replace("-", " ").replace("_", " ").title()
            lines.append(f"### {heading}")
            for page in sorted(by_type[et], key=lambda p: p["title"].lower()):
                path_no_ext = page["path"].removesuffix(".md")
                tag_str = " ".join(f"`#{t}`" for t in page["tags"]) if page["tags"] else ""
                entry = f"- [[{path_no_ext}]] — {page['title']}"
                if tag_str:
                    entry += f" {tag_str}"
                lines.append(entry)
            lines.append("")

        lines += [
            "---",
            "",
            "## All Pages (A–Z)",
            "",
        ]

        for page in sorted(pages, key=lambda p: p["title"].lower()):
            path_no_ext = page["path"].removesuffix(".md")
            lines.append(f"- [[{path_no_ext}]] — {page['title']}")

        index_md_path = os.path.join(meta_dir, "index.md")
        with open(index_md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    async def update_page_tags(self, page_path: str, tags: list[str], _rebuild: bool = True) -> None:
        """Replace the tags list on a wiki page's YAML frontmatter and rebuild index."""
        path = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
        if not os.path.exists(path):
            raise FileNotFoundError(f"Page not found: {page_path}")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        fm, body = self._parse_frontmatter(content)
        fm["tags"] = [str(t).lower().strip() for t in tags]
        new_content = self._render_frontmatter(fm, body)
        async with self._write_lock:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
        if _rebuild:
            self._rebuild_search_index()

    def update_source_tags(self, filename: str, tags: list[str], _rebuild: bool = True) -> None:
        """Replace the tags list on a source's metadata entry and rebuild index."""
        metadata = self._load_metadata()
        entry = metadata.get(filename, {"ingested": False, "ingested_at": None})
        entry["tags"] = [str(t).lower().strip() for t in tags]
        metadata[filename] = entry
        self._save_metadata(metadata)
        if _rebuild:
            self._rebuild_search_index()

    async def _suggest_tags(self, content: str, entity_type: str) -> list[str]:
        """Ask the LLM for 3-5 tags. Returns empty list on any failure."""
        prompt = ChatPromptTemplate.from_messages([
            ("human", (
                "Suggest 3-5 short, lowercase tags for this {entity_type} page. "
                "Return ONLY a JSON array of strings, e.g. [\"tag1\", \"tag2\"]. "
                "Content:\n{content}"
            ))
        ])
        chain = prompt | self.ingest_llm
        try:
            response = await chain.ainvoke({
                "entity_type": entity_type,
                "content": content[:2000],
            })
            text = response.content if hasattr(response, "content") else str(response)
            match = re.search(r'\[.*?\]', text, re.DOTALL)
            if match:
                tags = json.loads(match.group())
                return [str(t).lower().strip() for t in tags if isinstance(t, str)][:5]
        except Exception:
            pass
        return []

    def _load_metadata(self) -> Dict:
        if not os.path.exists(self.metadata_path):
            return {}
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_metadata(self, metadata: Dict):
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

    def get_sources_metadata(self) -> Dict:
        """Return metadata for all current sources."""
        metadata = self._load_metadata()
        current_sources = self.list_sources()
        result = {}
        for s in current_sources:
            stored = metadata.get(s, {})
            result[s] = {
                "ingested": stored.get("ingested", False),
                "ingested_at": stored.get("ingested_at", None),
                "tags": stored.get("tags", []),
            }
        return result

    def _load_page_metadata(self) -> Dict:
        if not os.path.exists(self.page_metadata_path):
            return {}
        try:
            with open(self.page_metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_page_metadata(self, metadata: Dict) -> None:
        with open(self.page_metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

    def get_pages_metadata(self) -> Dict:
        return self._load_page_metadata()

    def _mark_pages_unread(self, paths: List[str]) -> None:
        """Mark pages as unread. Must be called while holding self._write_lock."""
        metadata = self._load_page_metadata()
        for path in paths:
            metadata[path] = {"read": False, "read_at": None}
        self._save_page_metadata(metadata)

    async def mark_page_read(self, path: str) -> None:
        async with self._write_lock:
            metadata = self._load_page_metadata()
            metadata[path] = {
                "read": True,
                "read_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save_page_metadata(metadata)

    def mark_source_ingested(self, file_name: str, status: bool = True):
        """Mark a source as ingested in the metadata."""
        metadata = self._load_metadata()
        existing = metadata.get(file_name, {})
        if status:
            existing["ingested"] = True
            existing["ingested_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            existing["ingested"] = False
            existing["ingested_at"] = None
        metadata[file_name] = existing
        self._save_metadata(metadata)

    def _get_page_path(self, title: str) -> str:
        # Sanitize title for filename
        safe_title = title.replace("/", "_").replace("\\", "_").replace(" ", "_")
        return os.path.join(self.wiki_dir, f"{safe_title}.md")

    def _write_page(self, title: str, content: str):
        path = self._get_page_path(title)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _append_to_log(self, action: str, details: str):
        log_path = os.path.join(self.wiki_dir, "log.md")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"## [{timestamp}] {action} | {details}\n")

    def get_entity_types(self) -> Dict[str, Dict]:
        """Discover entity types dynamically from _type.yaml files."""
        return discover_entity_types(self.wiki_dir)

    def get_field_schema(self, entity_type: str) -> dict:
        from agent.schema_builder import load_type_yaml
        folder_path = os.path.join(self.wiki_dir, entity_type)
        type_data = load_type_yaml(folder_path)
        if not type_data:
            return {}
        return {
            field["name"]: field["values"]
            for field in type_data.get("fields", [])
            if field.get("type") == "enum" and field.get("values")
        }

    async def patch_frontmatter_field(self, page_path: str, field: str, value) -> None:
        """Update a single frontmatter field in a page and rebuild the search index."""
        abs_path = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Page not found: {page_path}")
        async with self._write_lock:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
            fm, body = self._parse_frontmatter(content)
            fm[field] = value
            updated = self._render_frontmatter(fm, body)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(updated)
        self._rebuild_search_index()

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
                    page_ref = f"{sub}/{filename[:-3]}"  # strip .md
                    lines.append(f"- [[{page_ref}]] | last updated: {today}")
            else:
                lines.append(f"*No {sub} pages yet.*")
            lines.append("")

        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _supports_cache_control(self, operation: str = None) -> bool:
        """cache_control content blocks are an Anthropic-specific extension.

        Only Anthropic (native, or routed through OpenRouter to an Anthropic
        model) is known to honor them — other providers may reject the extra
        field outright, so default to plain string content for everyone else.
        """
        prefix = f"{operation.upper()}_" if operation else ""
        provider = (os.getenv(f"{prefix}AI_PROVIDER") or os.getenv("AI_PROVIDER", "openai")).lower()
        model = os.getenv(f"{prefix}AI_MODEL") or os.getenv("AI_MODEL", "gpt-4o-mini")
        if provider == "anthropic":
            return True
        if provider == "openrouter" and model.startswith("anthropic/"):
            return True
        return False

    async def _run_ingest_llm(
        self, filename: str, source_content: str, index_content: str, existing_pages: str
    ) -> FaragoIngestionResult:
        """Run the LLM ingest call. Extracted for testability."""
        entity_types = self.get_entity_types()
        entity_types_str = ", ".join(entity_types.keys()) if entity_types else "clients, prospects, contacts, photographers, productions"

        prefix_text = INGEST_HUMAN_TEMPLATE_PREFIX.format(
            index_content=index_content, existing_pages=existing_pages
        )
        suffix_text = INGEST_HUMAN_TEMPLATE_SUFFIX.format(
            filename=filename, source_content=source_content, entity_types=entity_types_str
        )

        if self._supports_cache_control("ingest"):
            system_message = SystemMessage(content=[
                {"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}},
            ])
            human_message = HumanMessage(content=[
                {"type": "text", "text": prefix_text, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": suffix_text},
            ])
        else:
            system_message = SystemMessage(content=self.system_prompt)
            human_message = HumanMessage(content=f"{prefix_text}\n\n{suffix_text}")

        structured_llm = self.ingest_llm.with_structured_output(FaragoIngestionResult)
        return await structured_llm.ainvoke([system_message, human_message])

    async def ingest_source(self, file_name: str):
        """Phase 1: Read file and call LLM (concurrent). Phase 2: Write files (serialized)."""
        file_path = os.path.join(self.sources_dir, file_name)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Source file not found: {file_path}")

        # Read source content
        ext = os.path.splitext(file_name)[1].lower()
        content = ""
        try:
            if ext == ".pdf":
                from langchain_community.document_loaders import PyPDFLoader
                loader = PyPDFLoader(file_path)
                docs = await asyncio.to_thread(loader.load)
                content = "\n\n".join([doc.page_content for doc in docs])
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
        except Exception as e:
            print(f"ERROR: Failed to read {file_name}: {e}")
            self._append_to_log("error", f"Failed to read {file_name}: {e}")
            return

        if not content.strip():
            print(f"WARNING: No content extracted from {file_name}")
            return

        # Load current index
        index_path = os.path.join(self.wiki_dir, "index.md")
        index_content = ""
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                index_content = f.read()

        # Load existing pages that may be updated (all current pages as context)
        existing_pages_str = ""
        for rel_path in self.list_pages():
            full_path = os.path.join(self.wiki_dir, rel_path.replace("/", os.sep))
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    existing_pages_str += f"\n--- {rel_path} ---\n{f.read()}\n"

        # LLM call with retry (max 2 retries)
        result = None
        last_error = None
        for attempt in range(3):
            try:
                ingest_content = content
                if attempt > 0 and last_error:
                    ingest_content = f"{content}\n\n[Previous attempt failed with: {last_error}. Please fix and retry.]"
                result = await self._run_ingest_llm(file_name, ingest_content, index_content, existing_pages_str)
                break
            except Exception as e:
                last_error = str(e)
                print(f"WARNING: Ingest attempt {attempt + 1} failed: {e}")

        if result is None:
            msg = f"Ingest failed after 3 attempts for {file_name}: {last_error}"
            print(f"ERROR: {msg}")
            self._append_to_log("error", msg)
            self.mark_source_ingested(file_name, False)
            return

        # Phase 2: Write files (serialized)
        async with self._write_lock:
            for page in result.pages:
                page_full_path = os.path.join(self.wiki_dir, page.path.replace("/", os.sep))
                os.makedirs(os.path.dirname(page_full_path), exist_ok=True)
                with open(page_full_path, "w", encoding="utf-8") as f:
                    f.write(page.content)

            self.update_index()
            self.mark_source_ingested(file_name, True)
            self._append_to_log("ingest", result.log_entry)
            self._mark_pages_unread([page.path for page in result.pages])

        # Phase 3: Auto-apply AI tags (outside lock — async LLM calls)
        for page in result.pages:
            try:
                entity_type = page.path.split("/")[0]
                tags = await self._suggest_tags(page.content, entity_type)
                if tags:
                    await self.update_page_tags(page.path, tags, _rebuild=False)
            except Exception:
                pass
        try:
            source_tags = await self._suggest_tags(content[:2000], "source")
            if source_tags:
                self.update_source_tags(file_name, source_tags, _rebuild=False)
        except Exception:
            pass
        self._rebuild_search_index()

        return result

    async def _run_query_llm(self, user_query: str, context: str) -> str:
        """Run the answer LLM call. Extracted for testability."""
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template("{system_prompt}"),
            HumanMessagePromptTemplate.from_template(ANSWER_HUMAN_TEMPLATE),
        ])
        chain = prompt | self.chat_llm
        response = await chain.ainvoke({
            "system_prompt": self.system_prompt,
            "context": context,
            "query": user_query,
        })
        return response.content

    async def query(self, user_query: str) -> str:
        # Build page catalog from the actual filesystem so we're never dependent
        # on index.md being up to date.
        page_list = self.list_pages()
        if not page_list:
            return "No wiki content available yet. Please ingest some sources first."

        # Enrich catalog with titles and previews from the search index if available.
        search_index_path = os.path.join(self.wiki_dir, "search-index.json")
        page_meta: dict = {}
        if os.path.exists(search_index_path):
            try:
                with open(search_index_path, "r", encoding="utf-8") as f:
                    si = json.load(f)
                for entry in si.get("pages", []):
                    page_meta[entry["path"]] = entry
            except Exception:
                pass

        catalog_lines = []
        for path in page_list:
            meta = page_meta.get(path, {})
            title = meta.get("title", path)
            tags = ", ".join(meta.get("tags", []))
            preview = meta.get("content_preview", "")[:200]
            line = f"- {path} | {title}"
            if tags:
                line += f" | tags: {tags}"
            if preview:
                line += f" | {preview}"
            catalog_lines.append(line)

        catalog = "\n".join(catalog_lines)

        # Step 1: Find relevant pages using the LLM
        relevance_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template("{system_prompt}"),
            HumanMessagePromptTemplate.from_template(RELEVANCE_HUMAN_TEMPLATE),
        ])
        relevance_chain = relevance_prompt | self.chat_llm
        relevance_resp = await relevance_chain.ainvoke({
            "system_prompt": self.system_prompt,
            "index": catalog,
            "query": user_query,
        })

        raw_content = relevance_resp.content
        page_names_str = raw_content if isinstance(raw_content, str) else ""
        page_names_str = page_names_str.strip()

        if page_names_str.lower() == "none":
            return "I couldn't find relevant information in the wiki to answer your question."

        page_paths = [p.strip() for p in page_names_str.split(",") if p.strip()]

        # If LLM returned no usable paths, fall back to all pages
        if not page_paths:
            page_paths = page_list

        # Step 2: Read relevant pages
        context = ""
        for path in page_paths:
            clean_path = path.replace("[[", "").replace("]]", "").strip()
            if not clean_path.endswith(".md"):
                clean_path = f"{clean_path}.md"
            full_path = os.path.join(self.wiki_dir, clean_path.replace("/", os.sep))
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    context += f"\n--- {clean_path} ---\n{f.read()}\n"

        if not context:
            return "I found relevant page names but the pages appear to be missing."

        # Step 3: Synthesize answer
        answer = await self._run_query_llm(user_query, context)
        self._append_to_log("query", f"Answered: {user_query}")
        return answer

    async def _run_lint_llm(self, wiki_content: str) -> LintReport:
        """Run the LLM lint call. Extracted for testability."""
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template("{system_prompt}"),
            HumanMessagePromptTemplate.from_template(LINT_HUMAN_TEMPLATE),
        ])
        llm = self._init_llm("lint")
        chain = prompt | llm.with_structured_output(LintReport)
        return await chain.ainvoke({
            "system_prompt": self.system_prompt,
            "wiki_content": wiki_content,
        })

    async def lint(self) -> LintReport:
        """LLM-powered wiki lint. Read-only — returns a LintReport, writes only to log.md."""
        # Gather all wiki content
        wiki_content = ""
        for rel_path in self.list_pages():
            full_path = os.path.join(self.wiki_dir, rel_path.replace("/", os.sep))
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    wiki_content += f"\n=== {rel_path} ===\n{f.read()}\n"

        if not wiki_content.strip():
            return LintReport(findings=[], summary="Wiki is empty — nothing to lint.")

        report = await self._run_lint_llm(wiki_content)
        self._append_to_log("lint", report.summary)
        return report

    def create_snapshot(self, label: str = None) -> Snapshot:
        now = datetime.datetime.now()
        snapshot_id = now.strftime("%Y%m%d-%H%M%S-%f")
        created_at = now.isoformat()
        if label is None:
            label = f"pre-lint {now.strftime('%Y-%m-%d %H:%M')}"

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

        with zipfile.ZipFile(zip_path, 'r') as zf:
            bad = zf.testzip()
            if bad is not None:
                raise zipfile.BadZipFile(f"Corrupt entry in snapshot: {bad}")

            for item in os.listdir(self.wiki_dir):
                item_path = os.path.join(self.wiki_dir, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)

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

    async def _run_fix_llm(self, findings: List[LintFinding], wiki_content: str) -> LintFixPlan:
        findings_text = "\n".join([
            f"{i+1}. [{f.fix_confidence.upper()}] {f.description} (page: {f.page})\n   Fix: {f.fix_description}"
            for i, f in enumerate(findings)
        ])
        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template("{system_prompt}"),
            HumanMessagePromptTemplate.from_template(FIX_HUMAN_TEMPLATE),
        ])
        llm = self._init_llm("lint")
        chain = prompt | llm.with_structured_output(LintFixPlan)
        return await chain.ainvoke({
            "system_prompt": self.system_prompt,
            "wiki_content": wiki_content,
            "findings_text": findings_text,
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
            self._mark_pages_unread(files_changed)

        self._rebuild_search_index()

        return FixReport(
            files_changed=files_changed,
            skipped=fix_plan.skipped,
            summary=fix_plan.summary,
            snapshot_id=snapshot.id,
        )

    async def create_new_page(self, entity_type: str = "clients") -> str:
        """Create a new Untitled page in the given entity subdirectory.
        Returns the relative path, e.g. 'clients/Untitled.md'.
        """
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
            template_path = os.path.join(sub_dir, "_template.md")
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as _tf:
                    content = _tf.read()
            else:
                content = f"---\ntype: {singular}\nname: \n---\n\n# Untitled\n\nNew page content here.\n"
            with open(os.path.join(self.wiki_dir, rel_path.replace("/", os.sep)), "w", encoding="utf-8") as f:
                f.write(content)

            self.update_index()
            self._append_to_log("create", f"Created {rel_path}")
        self._rebuild_search_index()
        return rel_path

    async def auto_rename_if_untitled(self, rel_path: str) -> str | None:
        """Rename an Untitled page to a slug based on its 'name' frontmatter field.

        Returns the new relative path if a rename occurred, None otherwise.
        Renames only if:
        1. File basename matches Untitled(_N)?.md pattern
        2. File exists
        3. Frontmatter contains a non-empty 'name' field

        Handles collisions by appending -2, -3, etc.
        """
        basename = os.path.basename(rel_path)
        if not re.match(r'^Untitled(_\d+)?\.md$', basename):
            return None

        abs_path = os.path.join(self.wiki_dir, rel_path.replace("/", os.sep))
        if not os.path.exists(abs_path):
            return None

        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()

        fm, _ = self._parse_frontmatter(content)
        name_value = fm.get("name")
        # Skip if name is None or empty/whitespace string
        if name_value is None:
            return None
        name = str(name_value).strip()
        if not name:
            return None

        entity_type = rel_path.split("/")[0]
        sub_dir = os.path.join(self.wiki_dir, entity_type)
        slug = self._slugify(name)
        new_rel_path = f"{entity_type}/{slug}.md"
        new_abs_path = os.path.join(sub_dir, f"{slug}.md")

        # Handle collisions
        counter = 2
        while os.path.exists(new_abs_path):
            new_rel_path = f"{entity_type}/{slug}-{counter}.md"
            new_abs_path = os.path.join(sub_dir, f"{slug}-{counter}.md")
            counter += 1

        async with self._write_lock:
            os.rename(abs_path, new_abs_path)
            self.update_index()
        self._rebuild_search_index()
        return new_rel_path

    def rebuild_schema(self):
        """Regenerate SCHEMA.md from SCHEMA_TEMPLATE.md and _type.yaml files."""
        template_path = os.path.join(self.schema_dir, "SCHEMA_TEMPLATE.md")
        if not os.path.exists(template_path):
            # WikiManager is only constructed post-setup, by which point setup_wizard
            # guarantees SCHEMA_TEMPLATE.md exists — a missing template here means the
            # workspace is corrupted, so fail loud instead of leaving SCHEMA.md stale.
            raise FileNotFoundError(f"SCHEMA_TEMPLATE.md not found in {self.schema_dir}")
        schema_content = build_schema_md(self.wiki_dir, template_path)
        schema_path = os.path.join(self.schema_dir, "SCHEMA.md")
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write(schema_content)
        # Reload system prompt so next LLM call sees updated schema
        self.system_prompt = self._load_system_prompt()

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

    async def create_folder(
        self,
        folder_name: str,
        display_name: str,
        description: str = "",
        fields: list[dict] | None = None,
        sections: list[str] | None = None,
        singular: str | None = None,
    ):
        """Create a new entity folder with a _type.yaml file.

        fields/sections/singular are optional: omitted, they fall back to the minimal
        two-field type this method has always written, so the UI's New Folder dialog
        (which sends only name/display_name/description) is unaffected. Passing them
        lets an API caller create a folder whose _type.yaml is as expressive as the ones
        the setup wizard writes directly — previously the only way to get a real field
        schema was to bypass this method.

        singular is explicit rather than guessed because the rstrip("s") fallback strips
        every trailing "s": "jobs" -> "job" is right by luck, "classes" -> "clas" is not.
        """
        folder_path = os.path.join(self.wiki_dir, folder_name)
        if os.path.exists(folder_path):
            raise ValueError(f"Folder '{folder_name}' already exists")

        resolved_singular = singular or folder_name.rstrip("s")

        async with self._write_lock:
            os.makedirs(folder_path)
            type_data = {
                "name": display_name,
                "description": description,
                "singular": resolved_singular,
                "fields": fields if fields is not None else [
                    {"name": "type", "type": "string", "default": resolved_singular},
                    {"name": "name", "type": "string", "required": True},
                ],
                "sections": sections if sections is not None else ["Overview", "Notes"],
            }
            with open(os.path.join(folder_path, "_type.yaml"), "w", encoding="utf-8") as f:
                yaml.dump(type_data, f, default_flow_style=False, sort_keys=False)

            self.rebuild_schema()
            self.update_index()
            self._append_to_log("create_folder", f"Created folder '{folder_name}' ({display_name})")

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

    async def rename_page(self, rel_path: str, new_name: str) -> str:
        """Rename a page within its entity type folder.
        Rewrites all wikilinks pointing to the old path.
        Returns the new relative path (unchanged if slug is identical).
        """
        slug = self._slugify(new_name)
        entity_type = rel_path.split('/')[0]
        sub_dir = os.path.join(self.wiki_dir, entity_type)
        old_abs = os.path.join(self.wiki_dir, rel_path.replace('/', os.sep))

        new_rel = f"{entity_type}/{slug}.md"
        new_abs = os.path.join(sub_dir, f"{slug}.md")

        if new_abs == old_abs:
            return rel_path

        counter = 2
        while os.path.exists(new_abs):
            new_rel = f"{entity_type}/{slug}-{counter}.md"
            new_abs = os.path.join(sub_dir, f"{slug}-{counter}.md")
            counter += 1

        old_ref = rel_path[:-3]   # strip .md for wikilink format
        new_ref = new_rel[:-3]

        async with self._write_lock:
            os.rename(old_abs, new_abs)
            self._rewrite_wikilinks_specific(old_ref, new_ref)
            self.update_index()
            self._append_to_log("rename", f"Renamed {rel_path} → {new_rel}")
        self._rebuild_search_index()
        return new_rel

    async def archive_page(self, page_path: str):
        """Move a wiki page to the archive."""
        src = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
        dest = os.path.join(self.archive_wiki_dir, page_path.replace("/", os.sep))
        async with self._write_lock:
            if not os.path.exists(src):
                raise FileNotFoundError(f"Page not found: {page_path}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.exists(dest):
                base, ext = os.path.splitext(dest)
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                dest = f"{base}_{timestamp}{ext}"
            shutil.move(src, dest)
            self.update_index()
            self._append_to_log("archive", f"Archived {page_path}")
        self._rebuild_search_index()

    async def archive_source(self, filename: str):
        """Move a source file to the archive."""
        src = os.path.join(self.sources_dir, filename)
        dest = os.path.join(self.archive_sources_dir, filename)
        
        async with self._write_lock:
            if not os.path.exists(src):
                raise FileNotFoundError(f"Source not found: {filename}")
            
            # Handle collision in archive
            if os.path.exists(dest):
                base, ext = os.path.splitext(filename)
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                dest = os.path.join(self.archive_sources_dir, f"{base}_{timestamp}{ext}")
                
            shutil.move(src, dest)
            self._append_to_log("archive", f"Archived source {filename}")

    async def restore_page(self, filename: str):
        """Move an archived wiki page back to the main wiki directory."""
        src = os.path.join(self.archive_wiki_dir, filename)
        dest = os.path.join(self.wiki_dir, filename)
        
        async with self._write_lock:
            if not os.path.exists(src):
                raise FileNotFoundError(f"Archived page not found: {filename}")

            # Handle collision in wiki_dir
            if os.path.exists(dest):
                base, ext = os.path.splitext(filename)
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                dest = os.path.join(self.wiki_dir, f"{base}_{timestamp}{ext}")

            shutil.move(src, dest)
            self.update_index()
            self._append_to_log("restore", f"Restored {filename}")
        self._rebuild_search_index()

    async def restore_source(self, filename: str):
        """Move an archived source file back to the main sources directory."""
        src = os.path.join(self.archive_sources_dir, filename)
        dest = os.path.join(self.sources_dir, filename)
        
        async with self._write_lock:
            if not os.path.exists(src):
                raise FileNotFoundError(f"Archived source not found: {filename}")
            
            # Handle collision in sources_dir
            if os.path.exists(dest):
                base, ext = os.path.splitext(filename)
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                dest = os.path.join(self.sources_dir, f"{base}_{timestamp}{ext}")
                
            shutil.move(src, dest)
            self._append_to_log("restore", f"Restored source {filename}")

    async def delete_archived_page(self, filename: str):
        """Permanently delete a wiki page from the archive."""
        path = os.path.join(self.archive_wiki_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Archived page not found: {filename}")
        os.remove(path)
        self._append_to_log("delete_permanent", f"Permanently deleted archived {filename}")

    async def delete_archived_source(self, filename: str):
        """Permanently delete a source file from the archive."""
        path = os.path.join(self.archive_sources_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Archived source not found: {filename}")
        os.remove(path)
        self._append_to_log("delete_permanent", f"Permanently deleted archived source {filename}")

    def list_archived_pages(self) -> List[str]:
        """List all markdown files in the archive wiki directory (recursive)."""
        pages = []
        for root, _dirs, files in os.walk(self.archive_wiki_dir):
            for f in files:
                if f.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, f), self.archive_wiki_dir)
                    pages.append(rel.replace(os.sep, "/"))
        return pages

    def list_archived_sources(self) -> List[str]:
        """List all files in the archive sources directory."""
        return [f for f in os.listdir(self.archive_sources_dir) if os.path.isfile(os.path.join(self.archive_sources_dir, f)) and not f.startswith(".")]

    def get_archived_page_content(self, filename: str) -> str:
        """Read and return the content of an archived wiki page."""
        path = os.path.join(self.archive_wiki_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Archived page not found: {filename}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    async def get_archived_source_content(self, filename: str) -> str:
        """Read and return the content of an archived source file."""
        # Use existing logic by passing the archive path
        old_sources_dir = self.sources_dir
        self.sources_dir = self.archive_sources_dir
        try:
            return await self.get_source_content(filename)
        finally:
            self.sources_dir = old_sources_dir

    def list_pages(self) -> List[str]:
        """List all entity pages as relative paths (e.g. 'clients/louis-vuitton.md').
        Excludes index.md, log.md, all _meta/ paths, and all _-prefixed .md files."""
        pages = []
        for root, _dirs, files in os.walk(self.wiki_dir):
            for filename in sorted(files):
                if not filename.endswith(".md") or filename.startswith("_"):
                    continue
                rel_path = os.path.relpath(os.path.join(root, filename), self.wiki_dir)
                # Normalize to forward slashes
                rel_path = rel_path.replace(os.sep, "/")
                if rel_path in ("index.md", "log.md") or rel_path.startswith("_meta/"):
                    continue
                pages.append(rel_path)
        return pages

    async def import_pages(
        self,
        folder: str,
        files: list[tuple[str, bytes]],
        resolutions: dict[str, str | dict],
    ) -> dict:
        folder_path = os.path.join(self.wiki_dir, folder)
        if not os.path.isdir(folder_path):
            raise FileNotFoundError(f"Folder '{folder}' does not exist")

        imported: list[str] = []
        skipped: list[str] = []
        errors: dict[str, str] = {}

        # Held across the whole batch, matching create_folder/patch_frontmatter_field:
        # a bulk import racing a lint or a folder rename would otherwise interleave
        # writes with an index rebuild and leave the index describing a half-written set.
        async with self._write_lock:
            for filename, content in files:
                resolution = resolutions.get(filename, "overwrite")

                if resolution == "skip":
                    skipped.append(filename)
                    continue

                if isinstance(resolution, dict) and "rename" in resolution:
                    target_name = resolution["rename"]
                else:
                    target_name = filename

                target_path = os.path.join(folder_path, target_name)

                if isinstance(resolution, dict) and "rename" in resolution and os.path.exists(target_path):
                    errors[filename] = f"Rename target '{target_name}' already exists"
                    continue

                try:
                    with open(target_path, "wb") as fh:
                        fh.write(content)
                    imported.append(f"{folder}/{target_name}")
                except OSError as e:
                    errors[filename] = str(e)

        # Outside the lock, as elsewhere — these read the tree, they don't write pages.
        #
        # _rebuild_search_index also rewrites wiki/_meta/index.md, so the index a reader
        # actually sees was never stale here. update_index maintains the separate legacy
        # wiki/index.md, which the API cannot even serve (the path validator rejects it)
        # but which fourteen other write paths in this class still update. Called here
        # only so import is not the one operation that leaves it behind; if that file is
        # genuinely dead it should be removed from all fifteen call sites at once.
        #
        # The log entry is the substantive addition: every other write path records
        # itself and a bulk import of 91 pages left no audit trail at all.
        if imported:
            self._rebuild_search_index()
            self.update_index()
            self._append_to_log(
                "import_pages",
                f"Imported {len(imported)} page(s) into '{folder}'",
            )

        return {"imported": imported, "skipped": skipped, "errors": errors}

    def list_sources(self) -> List[str]:
        """List all files in the sources directory."""
        return [f for f in os.listdir(self.sources_dir) if os.path.isfile(os.path.join(self.sources_dir, f)) and f != ".gitkeep" and not f.startswith(".")]

    def get_page_content(self, page_path: str) -> str:
        """Read and return the content of a wiki page."""
        path = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
        if not os.path.exists(path):
            raise FileNotFoundError(f"Page not found: {page_path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    async def get_source_content(self, filename: str) -> str:
        """Read and return the content of a source file."""
        path = os.path.join(self.sources_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Source file not found: {filename}")
        
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".pdf":
            try:
                from langchain_community.document_loaders import PyPDFLoader
                loader = PyPDFLoader(path)
                docs = await asyncio.to_thread(loader.load)
                return "\n\n".join([doc.page_content for doc in docs])
            except Exception as e:
                return f"Error extracting PDF content: {str(e)}"
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            # Fallback for non-utf8 files
            with open(path, "r", encoding="latin-1") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def get_backlinks(self, page_path: str) -> List[str]:
        """Find all pages that contain a wikilink to page_path.
        page_path is a relative path like 'clients/louis-vuitton.md'.
        Searches for [[clients/louis-vuitton]] style links.
        """
        # Build the link target string (without .md)
        target_ref = page_path[:-3] if page_path.endswith(".md") else page_path

        wiki_link_pattern = re.compile(r"\[\[(.*?)\]\]")
        backlinks = []

        for root, _dirs, files in os.walk(self.wiki_dir):
            for filename in sorted(files):
                if not filename.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(root, filename), self.wiki_dir).replace(os.sep, "/")
                if rel == page_path or rel in ("index.md", "log.md") or rel.startswith("_meta/"):
                    continue
                full_path = os.path.join(root, filename)
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                for link in wiki_link_pattern.findall(content):
                    if link == target_ref:
                        backlinks.append(rel)
                        break

        return sorted(backlinks)

    def get_link_graph(self) -> dict:
        """Build the full wikilink graph in a single pass over the wiki.

        Returns all pages as nodes, deduplicated wikilink edges whose target
        resolves to an existing page, and the entity types as groups — so the
        frontend can render the whole crosslink structure without calling
        get_backlinks() per page (which re-scans every file per call).
        """
        wiki_link_pattern = re.compile(r"\[\[(.*?)\]\]")
        entity_types = self.get_entity_types()
        pages = [
            p for p in self.list_pages()
            if len(p.split("/")) == 2 and p.split("/")[0] in entity_types
        ]
        page_set = set(pages)

        nodes = []
        edges = []
        seen_edges = set()
        for rel_path in pages:
            try:
                content = self.get_page_content(rel_path)
            except (OSError, FileNotFoundError):
                continue
            frontmatter, _ = self._parse_frontmatter(content)
            title = frontmatter.get("name")
            if not isinstance(title, str) or not title.strip():
                stem = rel_path.rsplit("/", 1)[-1][:-3]
                title = stem.replace("-", " ").replace("_", " ").title()
            nodes.append({
                "id": rel_path,
                "title": title.strip(),
                "group": rel_path.split("/")[0],
            })
            for link in wiki_link_pattern.findall(content):
                target = link.strip()
                target_path = target if target.endswith(".md") else f"{target}.md"
                if target_path in page_set and target_path != rel_path:
                    key = (rel_path, target_path)
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append({"source": rel_path, "target": target_path})

        groups = [
            {
                "id": folder,
                "name": data.get("name") or folder.replace("-", " ").title(),
                "description": data.get("description", "") or "",
            }
            for folder, data in entity_types.items()
        ]
        return {"nodes": nodes, "edges": edges, "groups": groups}

    async def save_page_content(self, page_path: str, content: str) -> list[str]:
        """
        Save content to a wiki page and log the action.
        Returns AI-suggested tags not already present on the page.
        """
        path = os.path.join(self.wiki_dir, page_path.replace("/", os.sep))
        async with self._write_lock:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.update_index()
            self._append_to_log("edit", f"Updated {page_path}")
        self._rebuild_search_index()

        entity_type = page_path.split("/")[0]
        fm, _ = self._parse_frontmatter(content)
        existing_tags = [str(t).lower() for t in fm.get("tags", []) if isinstance(t, str)]
        all_suggestions = await self._suggest_tags(content, entity_type)
        return [t for t in all_suggestions if t not in existing_tags]

