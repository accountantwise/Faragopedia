from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from agent import workspace_manager
from api.routes import set_wiki_manager

workspace_router = APIRouter()


class CreateWorkspaceRequest(BaseModel):
    name: str


class RenameWorkspaceRequest(BaseModel):
    name: str


@workspace_router.get("")
def list_workspaces_endpoint():
    return {
        "workspaces": workspace_manager.list_workspaces(),
        "active_workspace_id": workspace_manager.get_active_workspace_id(),
    }


@workspace_router.post("")
def create_workspace_endpoint(payload: CreateWorkspaceRequest):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    return workspace_manager.create_workspace(name)


@workspace_router.post("/{workspace_id}/switch")
def switch_workspace(workspace_id: str):
    try:
        workspace_manager.set_active_workspace(workspace_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found")

    from agent.setup_wizard import is_setup_complete
    schema_dir = workspace_manager.get_schema_dir()
    if is_setup_complete(schema_dir):
        from agent.wiki_manager import WikiManager
        from agent.setup_wizard import get_wiki_config
        try:
            wm = WikiManager(
                sources_dir=workspace_manager.get_sources_dir(),
                wiki_dir=workspace_manager.get_wiki_dir(),
                archive_dir=workspace_manager.get_archive_dir(),
                snapshots_dir=workspace_manager.get_snapshots_dir(),
                schema_dir=schema_dir,
            )
            set_wiki_manager(wm)
        except Exception:
            set_wiki_manager(None)
            return {"id": workspace_id, "setup_required": True, "wiki_name": ""}
        config = get_wiki_config(schema_dir)
        wiki_name = (config or {}).get("wiki_name", "")
        return {"id": workspace_id, "setup_required": False, "wiki_name": wiki_name}
    else:
        set_wiki_manager(None)
        return {"id": workspace_id, "setup_required": True, "wiki_name": ""}


@workspace_router.delete("/{workspace_id}")
def delete_workspace_endpoint(workspace_id: str):
    if workspace_id == workspace_manager.get_active_workspace_id():
        raise HTTPException(status_code=400, detail="Cannot delete the active workspace")
    try:
        workspace_manager.delete_workspace(workspace_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found")
    return {"success": True}


class DuplicateWorkspaceRequest(BaseModel):
    name: str
    mode: str  # "full" or "template"


@workspace_router.post("/{workspace_id}/archive")
def archive_workspace_endpoint(workspace_id: str):
    if workspace_id == workspace_manager.get_active_workspace_id():
        raise HTTPException(status_code=400, detail="Cannot archive the active workspace")
    try:
        workspace = workspace_manager.archive_workspace(workspace_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found")
    return workspace


@workspace_router.post("/{workspace_id}/unarchive")
def unarchive_workspace_endpoint(workspace_id: str):
    try:
        workspace = workspace_manager.unarchive_workspace(workspace_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found")
    return workspace


@workspace_router.patch("/{workspace_id}")
def rename_workspace_endpoint(workspace_id: str, payload: RenameWorkspaceRequest):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    try:
        workspace_manager.update_workspace_name(workspace_id, name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found")
    registry = workspace_manager.list_workspaces()
    entry = next((ws for ws in registry if ws["id"] == workspace_id), None)
    return entry


@workspace_router.post("/{workspace_id}/duplicate")
def duplicate_workspace_endpoint(workspace_id: str, payload: DuplicateWorkspaceRequest):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    if payload.mode not in ("full", "template"):
        raise HTTPException(status_code=422, detail="mode must be 'full' or 'template'")
    try:
        result = workspace_manager.duplicate_workspace(workspace_id, name, payload.mode)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not result["setup_required"]:
        from agent.setup_wizard import is_setup_complete
        schema_dir = workspace_manager.get_schema_dir()
        if is_setup_complete(schema_dir):
            from agent.wiki_manager import WikiManager
            from agent.setup_wizard import get_wiki_config
            try:
                wm = WikiManager(
                    sources_dir=workspace_manager.get_sources_dir(),
                    wiki_dir=workspace_manager.get_wiki_dir(),
                    archive_dir=workspace_manager.get_archive_dir(),
                    snapshots_dir=workspace_manager.get_snapshots_dir(),
                    schema_dir=schema_dir,
                )
                set_wiki_manager(wm)
            except Exception:
                set_wiki_manager(None)
        else:
            set_wiki_manager(None)
    else:
        set_wiki_manager(None)

    return result
