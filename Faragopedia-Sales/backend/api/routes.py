from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, BackgroundTasks, Depends, Body
from datetime import datetime
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, validator
import os
import json
import shutil
import re
import zipfile
import io
import asyncio
from typing import Annotated, Dict, List
from agent.wiki_manager import WikiManager, LintFinding, FixReport, Snapshot
from agent.workspace_manager import (
    get_wiki_dir, get_sources_dir, get_archive_dir, get_snapshots_dir
)

router = APIRouter()

class TagsUpdate(BaseModel):
    tags: List[str]

class BulkFilenames(BaseModel):
    filenames: List[str]

class BulkPaths(BaseModel):
    paths: List[str]

class BulkMove(BaseModel):
    paths: List[str]
    destination: str

class BulkArchiveItems(BaseModel):
    pages: List[str] = []
    sources: List[str] = []

class LintFixRequest(BaseModel):
    findings: List[LintFinding]

    @validator('findings')
    def findings_not_empty(cls, v):
        if not v:
            raise ValueError('findings must not be empty')
        return v

# ── Dependency injection ──────────────────────────────────────────────────────

_wiki_manager: WikiManager | None = None

def get_wiki_manager() -> WikiManager:
    if _wiki_manager is None:
        raise HTTPException(status_code=503, detail="Wiki setup not complete")
    return _wiki_manager

def set_wiki_manager(wm: "WikiManager | None") -> None:
    global _wiki_manager
    _wiki_manager = wm

WM = Annotated[WikiManager, Depends(get_wiki_manager)]

# ─────────────────────────────────────────────────────────────────────────────

def get_valid_entity_subdirs(wm: WikiManager) -> set:
    return set(wm.get_entity_types().keys())

def rewrite_wikilinks(path_map: dict, wiki_dir: str) -> dict:
    """Scan all .md files in wiki_dir and rewrite wikilinks for moved pages.

    path_map: {old_path: new_path} e.g. {"prospects/acme.md": "clients/acme.md"}
    Returns: {file_path: count_of_rewrites}
    """
    links_rewritten = {}
    for root, dirs, files in os.walk(wiki_dir):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            full = os.path.join(root, fname)
            try:
                with open(full, "r", encoding="utf-8") as f:
                    original = f.read()
            except OSError:
                continue
            updated = original
            count = 0
            for old_path, new_path in path_map.items():
                # Strip .md for wikilink format: [[subdir/page-name]]
                old_link = old_path[:-3] if old_path.endswith(".md") else old_path
                new_link = new_path[:-3] if new_path.endswith(".md") else new_path
                pattern = r'\[\[' + re.escape(old_link) + r'\]\]'
                replacement = f'[[{new_link}]]'
                new_text, n = re.subn(pattern, replacement, updated)
                updated = new_text
                count += n
            if count > 0 and updated != original:
                with open(full, "w", encoding="utf-8") as f:
                    f.write(updated)
                # Use relative path from wiki_dir for the key
                rel = os.path.relpath(full, wiki_dir).replace("\\", "/")
                links_rewritten[rel] = count
    return links_rewritten

def secure_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal.
    Used for uploaded files where the name comes from untrusted user input.
    """
    filename = os.path.basename(filename)
    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    return filename

def safe_wiki_filename(path: str, wm: WikiManager) -> str:
    """Validate a wiki page path of the form 'subdir/page-name.md'.
    Accepts exactly one level of subdirectory from VALID_ENTITY_SUBDIRS.
    Also allows _meta/ system paths without entity-type validation.
    Rejects path traversal, unknown subdirectories, and non-.md files.
    """
    # Normalize separators
    normalized = path.replace("\\", "/")

    # Must end with .md
    if not normalized.endswith(".md"):
        raise ValueError(f"Invalid page path: {path!r} — must end with .md")

    # Allow _meta/ system paths without entity-type validation
    if normalized.startswith("_meta/"):
        if ".." in normalized:
            raise ValueError(f"Path traversal detected in: {path!r}")
        wiki_real = os.path.realpath(get_wiki_dir())
        resolved = os.path.realpath(os.path.join(wiki_real, normalized))
        if os.name == "nt":
            if not resolved.lower().startswith(wiki_real.lower() + os.sep):
                raise ValueError(f"Path traversal detected in: {path!r}")
        else:
            if not resolved.startswith(wiki_real + os.sep):
                raise ValueError(f"Path traversal detected in: {path!r}")
        return normalized

    parts = normalized.split("/")

    # Must be exactly subdir/filename.md (2 parts)
    if len(parts) != 2:
        raise ValueError(f"Invalid entity subdirectory in path: {path!r}")

    subdir, filename = parts

    # Subdir must be a known entity type
    if subdir not in get_valid_entity_subdirs(wm):
        raise ValueError(f"Invalid entity subdirectory '{subdir}' in path: {path!r}")

    # No path traversal components
    if ".." in filename or ".." in subdir:
        raise ValueError(f"Path traversal detected in: {path!r}")

    # Validate the full resolved path stays within wiki dir
    wiki_real = os.path.realpath(get_wiki_dir())
    resolved = os.path.realpath(os.path.join(wiki_real, subdir, filename))

    if os.name == "nt":
        if not resolved.lower().startswith(wiki_real.lower() + os.sep):
            raise ValueError(f"Path traversal detected in: {path!r}")
    else:
        if not resolved.startswith(wiki_real + os.sep):
            raise ValueError(f"Path traversal detected in: {path!r}")

    return normalized

@router.post("/upload")
async def upload_file(wm: WM, file: UploadFile = File(...), ingest: bool = Query(True)):
    if not os.path.exists(get_sources_dir()):
        try:
            os.makedirs(get_sources_dir(), exist_ok=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not create sources directory: {str(e)}")

    if not os.access(get_sources_dir(), os.W_OK):
        raise HTTPException(status_code=500, detail="Sources directory is not writeable")

    safe_name = secure_filename(file.filename)
    file_path = os.path.join(get_sources_dir(), safe_name)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save file: {str(e)}")

    if ingest:
        asyncio.create_task(wm.ingest_source(safe_name))
        message = "File uploaded and ingestion started"
    else:
        message = "File uploaded successfully (ingestion skipped)"

    return {"filename": safe_name, "message": message}

@router.post("/paste")
async def paste_source(payload: dict):
    content = payload.get("content", "")
    if not content or not content.strip():
        raise HTTPException(status_code=422, detail="Content is required")

    explicit_filename = (payload.get("filename") or "").strip()
    name = (payload.get("name") or "").strip()
    if explicit_filename:
        # Caller (e.g. an external automation) chose the full filename,
        # extension included — honor it verbatim rather than forcing .txt.
        filename = secure_filename(explicit_filename)
    elif name:
        filename = secure_filename(name)
        if not filename.endswith(".txt"):
            filename += ".txt"
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"paste-{timestamp}.txt"

    os.makedirs(get_sources_dir(), exist_ok=True)
    file_path = os.path.join(get_sources_dir(), filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {"filename": filename, "message": "Text saved as source"}


@router.post("/chat")
async def chat(wm: WM, query: str):
    if not query or not query.strip():
        raise HTTPException(status_code=422, detail="Query parameter is required")
    try:
        response = await wm.query(query)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

@router.get("/pages")
async def list_pages(wm: WM):
    """Return wiki pages grouped by entity subdirectory."""
    try:
        all_pages = wm.list_pages()
        valid_subdirs = get_valid_entity_subdirs(wm)
        grouped: Dict[str, List[str]] = {sub: [] for sub in valid_subdirs}
        for page_path in all_pages:
            parts = page_path.split("/")
            if len(parts) == 2 and parts[0] in valid_subdirs:
                grouped[parts[0]].append(page_path)
        return grouped
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing pages: {str(e)}")

@router.get("/pages/graph")
async def get_link_graph(wm: WM):
    """Return the full wikilink graph (nodes + edges + groups) in one pass.

    Registered before GET /pages/{path:path} so 'graph' is not captured as a
    page path. Avoids the N+1 pattern of calling /backlinks per page.
    """
    try:
        return wm.get_link_graph()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error building link graph: {str(e)}")

@router.get("/sources")
async def list_sources(wm: WM):
    try:
        return wm.list_sources()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing sources: {str(e)}")

@router.get("/sources/metadata")
async def get_sources_metadata(wm: WM):
    try:
        return wm.get_sources_metadata()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching source metadata: {str(e)}")

@router.post("/sources/{filename}/ingest")
async def ingest_source(wm: WM, filename: str):
    try:
        safe_name = os.path.basename(filename)
        if not os.path.exists(os.path.join(get_sources_dir(), safe_name)):
            raise FileNotFoundError("Source file not found")
        asyncio.create_task(wm.ingest_source(safe_name))
        return {"message": f"Ingestion started for {safe_name}"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Source file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting ingestion: {str(e)}")

@router.post("/sources/bulk-ingest")
async def bulk_ingest_sources(wm: WM, payload: BulkFilenames):
    queued = []
    skipped = []
    for filename in payload.filenames:
        safe_name = os.path.basename(filename)
        if os.path.exists(os.path.join(get_sources_dir(), safe_name)):
            asyncio.create_task(wm.ingest_source(safe_name))
            queued.append(safe_name)
        else:
            skipped.append(safe_name)
    return JSONResponse(status_code=202, content={"queued": queued, "skipped": skipped})

@router.get("/pages/{path:path}/backlinks")
async def get_backlinks(wm: WM, path: str):
    try:
        safe_path = safe_wiki_filename(path, wm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        return wm.get_backlinks(safe_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching backlinks: {str(e)}")


@router.get("/pages/{path:path}/download")
async def download_page(wm: WM, path: str):
    try:
        safe_path = safe_wiki_filename(path, wm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    full_path = os.path.join(get_wiki_dir(), safe_path.replace("/", os.sep))
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Page not found")
    filename = safe_path.split("/")[-1]
    return FileResponse(full_path, filename=filename, media_type="text/markdown")


@router.patch("/pages/{path:path}/frontmatter")
async def patch_frontmatter(wm: WM, path: str, payload: dict = Body(...)):
    field = payload.get("field")
    if not field:
        raise HTTPException(status_code=422, detail="'field' is required")
    value = payload.get("value", "")
    try:
        safe_path = safe_wiki_filename(path, wm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        await wm.patch_frontmatter_field(safe_path, field, value)
        return {"ok": True}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MarkReadRequest(BaseModel):
    path: str


@router.get("/pages/metadata")
async def get_pages_metadata_endpoint(wm: WM):
    try:
        return wm.get_pages_metadata()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching pages metadata: {str(e)}")


@router.post("/pages/mark-read")
async def mark_page_read_endpoint(wm: WM, body: MarkReadRequest):
    try:
        await wm.mark_page_read(body.path)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error marking page as read: {str(e)}")


@router.get("/pages/{path:path}")
async def get_page(wm: WM, path: str):
    try:
        safe_path = safe_wiki_filename(path, wm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        return {"content": wm.get_page_content(safe_path)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading page: {str(e)}")


@router.get("/sources/{filename}")
async def get_source(wm: WM, filename: str):
    try:
        safe_name = os.path.basename(filename)
        return {"content": await wm.get_source_content(safe_name)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Source not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading source: {str(e)}")


@router.post("/pages")
async def create_page(wm: WM, entity_type: str = Query("clients")):
    if entity_type not in get_valid_entity_subdirs(wm):
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")
    try:
        filename = await wm.create_new_page(entity_type=entity_type)
        return {"filename": filename, "message": "New page created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating page: {str(e)}")


@router.get("/entity-types")
async def get_entity_types(wm: WM):
    try:
        return wm.get_entity_types()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing entity types: {str(e)}")


@router.get("/entity-types/{entity_type}/field-schema")
async def get_field_schema(wm: WM, entity_type: str):
    if entity_type not in get_valid_entity_subdirs(wm):
        raise HTTPException(status_code=404, detail=f"Unknown entity type: {entity_type}")
    try:
        return {"schema": wm.get_field_schema(entity_type)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# The field-type vocabulary _type.yaml already supports; see setup_wizard.EntityTypeField
# and the built-in clients/contacts types, which between them use all five.
VALID_FIELD_TYPES = {"string", "date", "integer", "enum", "list"}


def validate_type_fields(fields) -> None:
    """Reject a malformed `fields` list before it reaches _type.yaml.

    An invalid schema here is silently corrosive rather than loud: schema_builder
    renders whatever it finds, so a field without a name or an enum without values
    produces a broken SCHEMA.md, and SCHEMA.md is the document the ingest and lint
    agents read for every entity type — not just this folder's.
    """
    if not isinstance(fields, list):
        raise HTTPException(status_code=422, detail="fields must be a list")
    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            raise HTTPException(status_code=422, detail=f"fields[{i}] must be an object")
        if not str(field.get("name", "")).strip():
            raise HTTPException(status_code=422, detail=f"fields[{i}] is missing a name")
        ftype = field.get("type", "string")
        if ftype not in VALID_FIELD_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"fields[{i}] has unknown type '{ftype}'; "
                       f"expected one of {', '.join(sorted(VALID_FIELD_TYPES))}",
            )
        if ftype == "enum" and not field.get("values"):
            raise HTTPException(
                status_code=422,
                detail=f"fields[{i}] ('{field['name']}') is an enum and needs a values list",
            )


@router.post("/folders")
async def create_folder(wm: WM, payload: dict):
    name = payload.get("name", "").strip()
    display_name = payload.get("display_name", "").strip()
    description = payload.get("description", "").strip()
    if not name or not display_name:
        raise HTTPException(status_code=422, detail="name and display_name are required")
    if not re.match(r"^[a-z][a-z0-9-]*$", name):
        raise HTTPException(status_code=400, detail="Folder name must be lowercase alphanumeric with hyphens")

    # All optional. Absent, create_folder writes the same minimal type it always has,
    # so the UI's New Folder dialog keeps working byte-for-byte unchanged.
    fields = payload.get("fields")
    sections = payload.get("sections")
    singular = (payload.get("singular") or "").strip() or None
    if fields is not None:
        validate_type_fields(fields)
    if sections is not None:
        if not isinstance(sections, list) or not all(isinstance(x, str) for x in sections):
            raise HTTPException(status_code=422, detail="sections must be a list of strings")

    try:
        await wm.create_folder(
            name, display_name, description,
            fields=fields, sections=sections, singular=singular,
        )
        return {"message": f"Folder '{name}' created", "folder": name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating folder: {str(e)}")


@router.delete("/folders/{folder_name}")
async def delete_folder(wm: WM, folder_name: str):
    try:
        await wm.delete_folder(folder_name)
        return {"message": f"Folder '{folder_name}' deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting folder: {str(e)}")


@router.put("/folders/{folder_name}")
async def rename_folder(wm: WM, folder_name: str, payload: dict):
    new_name = payload.get("new_name", "").strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="new_name is required")
    if not re.match(r"^[a-z][a-z0-9-]*$", new_name):
        raise HTTPException(status_code=400, detail="Folder name must be lowercase alphanumeric with hyphens")
    try:
        await wm.rename_folder(folder_name, new_name)
        return {"message": f"Folder renamed: {folder_name} → {new_name}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renaming folder: {str(e)}")


@router.post("/pages/{path:path}/move")
async def move_page(wm: WM, path: str, payload: dict):
    try:
        safe_path = safe_wiki_filename(path, wm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    target_folder = payload.get("target_folder", "").strip()
    if not target_folder:
        raise HTTPException(status_code=422, detail="target_folder is required")
    try:
        new_path = await wm.move_page(safe_path, target_folder)
        return {"message": f"Page moved to {new_path}", "new_path": new_path}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error moving page: {str(e)}")


@router.post("/pages/{path:path}/rename")
async def rename_page_endpoint(wm: WM, path: str, payload: dict):
    try:
        safe_path = safe_wiki_filename(path, wm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    new_name = (payload.get("new_name") or "").strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="new_name is required")
    try:
        new_path = await wm.rename_page(safe_path, new_name)
        return {"new_path": new_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renaming page: {str(e)}")


@router.post("/lint")
async def run_lint(wm: WM):
    try:
        report = await wm.lint()
        return report.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running lint: {str(e)}")


@router.post("/lint/fix")
async def fix_lint_findings(wm: WM, request: LintFixRequest):
    try:
        report = await wm.fix_lint_findings(request.findings)
        return report.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying lint fixes: {str(e)}")


@router.get("/snapshots")
async def list_snapshots(wm: WM):
    try:
        snapshots = wm.list_snapshots()
        return [s.model_dump() for s in snapshots]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing snapshots: {str(e)}")


@router.post("/snapshots/{snapshot_id}/restore")
async def restore_snapshot(wm: WM, snapshot_id: str):
    try:
        wm.restore_snapshot(snapshot_id)
        return {"success": True, "message": f"Snapshot {snapshot_id} restored successfully"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error restoring snapshot: {str(e)}")


@router.delete("/snapshots/{snapshot_id}")
async def delete_snapshot(wm: WM, snapshot_id: str):
    try:
        wm.delete_snapshot(snapshot_id)
        return {"success": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting snapshot: {str(e)}")


@router.delete("/sources/bulk")
async def bulk_archive_sources(wm: WM, payload: BulkFilenames):
    archived = []
    errors = []
    for filename in payload.filenames:
        safe_name = os.path.basename(filename)
        try:
            await wm.archive_source(safe_name)
            archived.append(safe_name)
        except Exception:
            errors.append(safe_name)
    return {"archived": archived, "errors": errors}


@router.delete("/pages/bulk")
async def bulk_archive_pages(wm: WM, payload: BulkPaths):
    archived = []
    errors = []
    for path in payload.paths:
        try:
            safe_path = safe_wiki_filename(path, wm)
            await wm.archive_page(safe_path)
            archived.append(path)
        except Exception:
            errors.append(path)
    return {"archived": archived, "errors": errors}


@router.post("/pages/bulk-move")
async def bulk_move_pages(wm: WM, payload: BulkMove):
    valid_destinations = get_valid_entity_subdirs(wm)
    if payload.destination not in valid_destinations:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid destination '{payload.destination}'. Must be one of: {sorted(valid_destinations)}"
        )
    moved = []
    errors = []
    path_map = {}
    for path in payload.paths:
        try:
            safe_path = safe_wiki_filename(path, wm)
        except ValueError as e:
            errors.append({"path": path, "error": str(e)})
            continue
        filename = safe_path.split("/")[1]  # e.g. "acme.md"
        new_path = f"{payload.destination}/{filename}"
        src = os.path.join(get_wiki_dir(), safe_path.replace("/", os.sep))
        dst = os.path.join(get_wiki_dir(), new_path.replace("/", os.sep))
        if os.path.exists(dst):
            errors.append({"path": path, "error": "destination already exists"})
            continue
        try:
            os.rename(src, dst)
            moved.append(f"{safe_path} → {new_path}")
            path_map[safe_path] = new_path
        except OSError as e:
            errors.append({"path": path, "error": str(e)})
    links_rewritten = rewrite_wikilinks(path_map, get_wiki_dir()) if path_map else {}
    return {"moved": moved, "errors": errors, "links_rewritten": links_rewritten}


@router.post("/pages/bulk-download")
async def bulk_download_pages(wm: WM, payload: BulkPaths):
    resolved = []
    for path in payload.paths:
        try:
            safe_path = safe_wiki_filename(path, wm)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        full_path = os.path.join(get_wiki_dir(), safe_path.replace("/", os.sep))
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail=f"Page not found: {path}")
        resolved.append((safe_path, full_path))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for safe_path, full_path in resolved:
            with open(full_path, "rb") as f:
                zf.writestr(safe_path, f.read())
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="pages-export.zip"'}
    )


@router.post("/sources/bulk-download")
async def bulk_download_sources(payload: BulkFilenames):
    resolved = []
    for filename in payload.filenames:
        safe_name = os.path.basename(filename)
        full_path = os.path.join(get_sources_dir(), safe_name)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail=f"Source not found: {filename}")
        resolved.append((safe_name, full_path))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for safe_name, full_path in resolved:
            with open(full_path, "rb") as f:
                zf.writestr(safe_name, f.read())
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="sources-export.zip"'}
    )


@router.delete("/pages/{path:path}")
async def delete_page(wm: WM, path: str):
    try:
        safe_path = safe_wiki_filename(path, wm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        await wm.archive_page(safe_path)
        return {"message": "Page moved to archive"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error archiving page: {str(e)}")

@router.delete("/sources/{filename}")
async def delete_source(wm: WM, filename: str):
    try:
        safe_name = os.path.basename(filename)
        await wm.archive_source(safe_name)
        return {"message": "Source moved to archive"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Source not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error archiving source: {str(e)}")

@router.get("/archive/pages")
async def list_archived_pages(wm: WM):
    try:
        return wm.list_archived_pages()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing archived pages: {str(e)}")

@router.get("/archive/sources")
async def list_archived_sources(wm: WM):
    try:
        return wm.list_archived_sources()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing archived sources: {str(e)}")

@router.post("/archive/bulk/restore")
async def bulk_restore_archive_items(wm: WM, payload: BulkArchiveItems):
    restored = []
    errors = []
    for page in payload.pages:
        try:
            safe_name = safe_wiki_filename(page, wm)
            await wm.restore_page(safe_name)
            restored.append(f"page:{page}")
        except Exception:
            errors.append(f"page:{page}")
    for source in payload.sources:
        try:
            safe_name = os.path.basename(source)
            await wm.restore_source(safe_name)
            restored.append(f"source:{source}")
        except Exception:
            errors.append(f"source:{source}")
    return {"restored": restored, "errors": errors}

@router.delete("/archive/bulk/permanent")
async def bulk_delete_archive_items_permanent(wm: WM, payload: BulkArchiveItems):
    deleted = []
    errors = []
    for page in payload.pages:
        try:
            safe_name = safe_wiki_filename(page, wm)
            await wm.delete_archived_page(safe_name)
            deleted.append(f"page:{page}")
        except Exception:
            errors.append(f"page:{page}")
    for source in payload.sources:
        try:
            safe_name = os.path.basename(source)
            await wm.delete_archived_source(safe_name)
            deleted.append(f"source:{source}")
        except Exception:
            errors.append(f"source:{source}")
    return {"deleted": deleted, "errors": errors}

@router.post("/archive/pages/{filename:path}/restore")
async def restore_page(wm: WM, filename: str):
    try:
        safe_name = safe_wiki_filename(filename, wm)
        await wm.restore_page(safe_name)
        return {"message": "Page restored from archive"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archived page not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error restoring page: {str(e)}")

@router.post("/archive/sources/{filename}/restore")
async def restore_source(wm: WM, filename: str):
    try:
        safe_name = os.path.basename(filename)
        await wm.restore_source(safe_name)
        return {"message": "Source restored from archive"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archived source not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error restoring source: {str(e)}")

@router.delete("/archive/pages/{filename:path}/permanent")
async def delete_archived_page_permanent(wm: WM, filename: str):
    try:
        safe_name = safe_wiki_filename(filename, wm)
        await wm.delete_archived_page(safe_name)
        return {"message": "Page permanently deleted from archive"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archived page not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting page: {str(e)}")

# ── URL scraping via WiseCrawler ──────────────────────────────────────────────

async def _crawl_and_save(url: str) -> None:
    """Background task: crawl a URL with WiseCrawler, save raw markdown to sources/."""
    import logging
    from urllib.parse import urlparse
    from agent.wisecrawler import start_crawl, poll_until_done

    logger = logging.getLogger(__name__)
    try:
        job_id = await start_crawl(url)
        result = await poll_until_done(job_id)

        pages = result.get("data", [])
        parts = []
        for page in pages:
            md = page.get("markdown") or ""
            page_url = (page.get("metadata") or {}).get("url", "")
            if md.strip():
                parts.append(f"## {page_url}\n\n{md}" if page_url else md)
        content = "\n\n---\n\n".join(parts) if parts else "(no content extracted)"

        parsed = urlparse(url)
        domain = parsed.netloc.replace(".", "-").replace(":", "-")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{domain}-{timestamp}.md"

        os.makedirs(get_sources_dir(), exist_ok=True)
        file_path = os.path.join(get_sources_dir(), filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# Source: {url}\n\n{content}")

        logger.info(f"Saved crawl result for {url} → {filename}")
    except Exception as exc:
        logger.error(f"Failed to crawl {url}: {exc}")


async def _scrape_and_save(url: str) -> None:
    """Background task: scrape a single URL with WiseCrawler, save raw markdown to sources/."""
    import logging
    from urllib.parse import urlparse
    from agent.wisecrawler import scrape

    logger = logging.getLogger(__name__)
    try:
        markdown = await scrape(url)

        parsed = urlparse(url)
        domain = parsed.netloc.replace(".", "-").replace(":", "-")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{domain}-{timestamp}.md"

        os.makedirs(get_sources_dir(), exist_ok=True)
        file_path = os.path.join(get_sources_dir(), filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# Source: {url}\n\n{markdown}")

        logger.info(f"Saved scrape result for {url} → {filename}")
    except Exception as exc:
        logger.error(f"Failed to scrape {url}: {exc}")


@router.post("/scrape-urls", status_code=202)
async def scrape_urls(payload: dict, background_tasks: BackgroundTasks):
    base_url = os.getenv("WISECRAWLER_BASE_URL", "")
    if not base_url:
        raise HTTPException(status_code=503, detail="WISECRAWLER_BASE_URL is not configured")

    urls = payload.get("urls", [])
    if not urls:
        raise HTTPException(status_code=422, detail="urls list is required and cannot be empty")

    mode = payload.get("mode", "crawl")
    task = _scrape_and_save if mode == "scrape" else _crawl_and_save

    for url in urls:
        background_tasks.add_task(task, url)

    return {"message": f"Started {len(urls)} {mode} job(s)"}


# ── Search via WiseCrawler (Brave-backed) ─────────────────────────────────────

async def _wc_search(query: str, count: int) -> list[dict]:
    """Indirection seam so tests can patch this symbol on api.routes."""
    from agent.wisecrawler import search as _search
    return await _search(query, count)


@router.post("/search")
async def search_web(payload: dict):
    import httpx as _httpx

    base_url = os.getenv("WISECRAWLER_BASE_URL", "")
    if not base_url:
        raise HTTPException(status_code=503, detail="WISECRAWLER_BASE_URL is not configured")

    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query is required")

    count = payload.get("count", 10)
    if not isinstance(count, int) or count < 1 or count > 20:
        raise HTTPException(status_code=422, detail="count must be an integer between 1 and 20")

    try:
        results = await _wc_search(query, count)
    except _httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            raise HTTPException(status_code=429, detail="Search rate limit reached. Try again in a minute.")
        if status == 503:
            raise HTTPException(status_code=503, detail="Web search isn't configured on the crawler service.")
        if status >= 500:
            raise HTTPException(status_code=502, detail="Web search failed. Please try again.")
        raise HTTPException(status_code=status, detail="Web search request rejected.")
    except _httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Web search service unavailable.")

    return {"results": results}


@router.delete("/archive/sources/{filename}/permanent")
async def delete_archived_source_permanent(wm: WM, filename: str):
    try:
        safe_name = os.path.basename(filename)
        await wm.delete_archived_source(safe_name)
        return {"message": "Source permanently deleted from archive"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archived source not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting source: {str(e)}")

@router.get("/sources/{filename}/download")
async def download_source(filename: str):
    safe_name = os.path.basename(filename)
    path = os.path.join(get_sources_dir(), safe_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Source not found")
    return FileResponse(path, filename=safe_name)

@router.get("/search/index")
async def get_search_index(wm: WM):
    index_path = os.path.join(get_wiki_dir(), "search-index.json")
    if not os.path.exists(index_path):
        wm._rebuild_search_index()
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading search index: {str(e)}")


@router.get("/tags")
async def get_tags(wm: WM):
    index_path = os.path.join(get_wiki_dir(), "search-index.json")
    if not os.path.exists(index_path):
        wm._rebuild_search_index()
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        tag_counts: dict[str, int] = {}
        for page in index.get("pages", []):
            for t in page.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        for src in index.get("sources", []):
            for t in src.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        return tag_counts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading tags: {str(e)}")


@router.patch("/pages/{path:path}/tags")
async def update_page_tags(wm: WM, path: str, body: TagsUpdate):
    try:
        safe_path = safe_wiki_filename(path, wm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        await wm.update_page_tags(safe_path, body.tags)
        return {"tags": body.tags}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating tags: {str(e)}")


@router.patch("/sources/{filename}/tags")
async def update_source_tags(wm: WM, filename: str, body: TagsUpdate):
    safe_name = os.path.basename(filename)
    src_path = os.path.join(get_sources_dir(), safe_name)
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        wm.update_source_tags(safe_name, body.tags)
        return {"tags": body.tags}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating source tags: {str(e)}")


@router.post("/search/rebuild")
async def rebuild_search_index(wm: WM):
    try:
        wm._rebuild_search_index()
        return {"message": "Search index rebuilt"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rebuilding index: {str(e)}")


@router.put("/pages/{path:path}")
async def update_page(wm: WM, path: str, payload: dict):
    try:
        safe_path = safe_wiki_filename(path, wm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    content = payload.get("content")
    if content is None:
        raise HTTPException(status_code=422, detail="Content is required")
    try:
        suggested_tags = await wm.save_page_content(safe_path, content)
        new_filename = await wm.auto_rename_if_untitled(safe_path)
        return {
            "message": "Page updated successfully",
            "suggested_tags": suggested_tags,
            "new_filename": new_filename,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating page: {str(e)}")


@router.post("/wiki/import")
async def import_wiki_files(
    wm: WM,
    folder: str = Form(...),
    files: list[UploadFile] = File(...),
    conflict_resolutions: str = Form(default="{}"),
):
    folder_path = os.path.join(wm.wiki_dir, folder)
    if not os.path.realpath(folder_path).startswith(os.path.realpath(wm.wiki_dir) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid folder path")
    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=404, detail=f"Folder '{folder}' not found")

    for f in files:
        if not (f.filename or "").endswith(".md"):
            raise HTTPException(status_code=400, detail=f"File '{f.filename}' is not a .md file")

    try:
        resolutions = json.loads(conflict_resolutions)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid conflict_resolutions JSON")

    file_data: list[tuple[str, bytes]] = []
    for f in files:
        safe_name = secure_filename(f.filename or "unnamed.md")
        if not safe_name:
            raise HTTPException(status_code=400, detail=f"Invalid filename '{f.filename}'")
        content = await f.read()
        file_data.append((safe_name, content))

    try:
        result = await wm.import_pages(folder, file_data, resolutions)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return result
