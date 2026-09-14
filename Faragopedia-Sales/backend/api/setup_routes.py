import os
import shutil

from fastapi import APIRouter, HTTPException

from agent.setup_wizard import (
    EntityTypeDefinition,  # noqa: F401 — re-exported for tests
    EntityTypeField,  # noqa: F401
    SetupPayload,
    SuggestRequest,
    SuggestedSchema,  # noqa: F401
    clear_setup,
    complete_setup,
    get_existing_folders,
    get_wiki_config,
    is_setup_complete,
    suggest_schema_llm,
)
from api.routes import set_wiki_manager
from agent.workspace_manager import (
    get_wiki_dir, get_sources_dir, get_archive_dir, get_snapshots_dir, get_schema_dir,
    update_workspace_name, get_active_workspace_id, create_workspace,
)

setup_router = APIRouter()


@setup_router.get("/status")
def setup_status():
    config = get_wiki_config(get_schema_dir())
    if config and config.get("setup_complete"):
        return {"setup_required": False, "wiki_name": config.get("wiki_name", "")}
    return {"setup_required": True}


@setup_router.get("/config")
def setup_config():
    config = get_wiki_config(get_schema_dir())
    if not config:
        raise HTTPException(status_code=404, detail="Wiki not configured")
    return {"wiki_name": config.get("wiki_name", ""), "org_name": config.get("org_name", "")}


@setup_router.get("/folders")
def setup_folders():
    return {"existing_folders": get_existing_folders(get_wiki_dir())}


@setup_router.post("/suggest-schema")
def suggest_schema(req: SuggestRequest):
    try:
        from agent.wiki_manager import WikiManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            wm = WikiManager(
                sources_dir=tmpdir,
                wiki_dir=tmpdir,
                archive_dir=tmpdir,
                snapshots_dir=tmpdir,
                schema_dir=tmpdir,
            )
            llm = wm._init_llm("chat")
        result = suggest_schema_llm(req.org_name, req.org_description, llm)
        return result.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="LLM unavailable") from exc


@setup_router.post("/complete")
def setup_complete(payload: SetupPayload):
    try:
        from agent.wiki_manager import WikiManager
        if get_active_workspace_id() is None:
            create_workspace(payload.wiki_name)
        complete_setup(get_schema_dir(), get_wiki_dir(), payload)
        wm = WikiManager(
            sources_dir=get_sources_dir(),
            wiki_dir=get_wiki_dir(),
            archive_dir=get_archive_dir(),
            snapshots_dir=get_snapshots_dir(),
            schema_dir=get_schema_dir(),
        )
        set_wiki_manager(wm)
        workspace_id = get_active_workspace_id()
        if workspace_id is not None:
            update_workspace_name(workspace_id, payload.wiki_name)
        return {"success": True, "wiki_name": payload.wiki_name}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@setup_router.post("/clear")
def setup_clear():
    set_wiki_manager(None)
    folders = clear_setup(get_schema_dir(), get_wiki_dir())
    return {"existing_folders": folders}


@setup_router.delete("/folder/{folder_name}")
def delete_setup_folder(folder_name: str):
    import re
    if not re.match(r"^[a-z][a-z0-9-]*$", folder_name):
        raise HTTPException(status_code=400, detail="Invalid folder name")
    folder_path = os.path.join(get_wiki_dir(), folder_name)
    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=404, detail="Folder not found")
    shutil.rmtree(folder_path)
    return {"success": True}
