"""workspace_manager.py — manages multiple workspaces (each is an independent wiki instance)."""

import json
import os
import re
import shutil
from datetime import datetime

# ── Path constants ────────────────────────────────────────────────────────────

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/agent/
BACKEND_DIR = os.path.dirname(_THIS_DIR)                # backend/
BASE_DIR = os.path.dirname(BACKEND_DIR)                 # project root

LEGACY_DIRS = {
    "wiki_dir":      os.path.join(BACKEND_DIR, "wiki"),
    "sources_dir":   os.path.join(BACKEND_DIR, "sources"),
    "archive_dir":   os.path.join(BACKEND_DIR, "archive"),
    "snapshots_dir": os.path.join(BACKEND_DIR, "snapshots"),
    "schema_dir":    os.path.join(BACKEND_DIR, "schema"),
}

WORKSPACES_BASE = os.path.join(BACKEND_DIR, "workspaces")
REGISTRY_PATH   = os.path.join(WORKSPACES_BASE, "registry.json")

# ── Module-level state ────────────────────────────────────────────────────────

_active_workspace_id: str | None = None
_active_dirs: dict = {}

# ── Registry helpers ──────────────────────────────────────────────────────────

def _read_registry() -> dict:
    """Read and return the registry JSON from REGISTRY_PATH."""
    with open(REGISTRY_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_registry(data: dict) -> None:
    """Write data as JSON to REGISTRY_PATH."""
    with open(REGISTRY_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# ── Workspace path helper ─────────────────────────────────────────────────────

def workspace_dirs(workspace_id: str) -> dict:
    """Return the path dict for a given workspace id."""
    return {
        "wiki_dir":      os.path.join(WORKSPACES_BASE, workspace_id, "wiki"),
        "sources_dir":   os.path.join(WORKSPACES_BASE, workspace_id, "sources"),
        "archive_dir":   os.path.join(WORKSPACES_BASE, workspace_id, "archive"),
        "snapshots_dir": os.path.join(WORKSPACES_BASE, workspace_id, "snapshots"),
        "schema_dir":    os.path.join(WORKSPACES_BASE, workspace_id, "schema"),
    }


# ── Initialisation ────────────────────────────────────────────────────────────

def initialize_workspaces() -> None:
    """Called at startup. Creates WORKSPACES_BASE if needed, then either loads
    an existing registry, migrates legacy data, or initialises an empty registry.
    """
    global _active_workspace_id, _active_dirs

    os.makedirs(WORKSPACES_BASE, exist_ok=True)

    if os.path.isfile(REGISTRY_PATH):
        # Registry already exists — load it and activate the stored workspace.
        registry = _read_registry()
        active_id = registry.get("active_workspace_id")
        # Cross-validate: discard a stored active ID that no longer exists.
        known_ids = {ws["id"] for ws in registry.get("workspaces", [])}
        if active_id and active_id not in known_ids:
            active_id = None
        _active_workspace_id = active_id
        if active_id:
            _active_dirs = workspace_dirs(active_id)
        else:
            _active_dirs = {}
        return

    legacy_schema = os.path.join(LEGACY_DIRS["schema_dir"], "wiki_config.json")
    if os.path.isfile(legacy_schema):
        # Legacy installation detected — migrate data into workspaces/default/.
        dirs = workspace_dirs("default")
        for key, src in LEGACY_DIRS.items():
            if os.path.isdir(src):
                dst = dirs[key]
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)

        # Read wiki name from legacy config.
        with open(legacy_schema, "r", encoding="utf-8") as fh:
            wiki_config = json.load(fh)
        wiki_name = wiki_config.get("wiki_name", "Default")

        registry = {
            "active_workspace_id": "default",
            "workspaces": [
                {
                    "id": "default",
                    "name": wiki_name,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            ],
        }
        _write_registry(registry)
        _active_workspace_id = "default"
        _active_dirs = dirs
        return

    # No existing data — write an empty registry.
    _write_registry({"active_workspace_id": None, "workspaces": []})
    _active_workspace_id = None
    _active_dirs = {}


# ── Read-only accessors ───────────────────────────────────────────────────────

def list_workspaces() -> list[dict]:
    """Return all workspace entries from the registry."""
    registry = _read_registry()
    return registry.get("workspaces", [])


def get_active_workspace_id() -> str | None:
    """Return the currently active workspace id."""
    return _active_workspace_id


def get_active_workspace_info() -> dict | None:
    """Return the registry entry for the currently active workspace, or None."""
    if _active_workspace_id is None:
        return None
    registry = _read_registry()
    for ws in registry.get("workspaces", []):
        if ws["id"] == _active_workspace_id:
            return ws
    return None


# ── Mutating operations ───────────────────────────────────────────────────────

def set_active_workspace(workspace_id: str) -> None:
    """Set the active workspace, update in-memory state, and persist to registry."""
    global _active_workspace_id, _active_dirs

    registry = _read_registry()
    ids = {ws["id"] for ws in registry.get("workspaces", [])}
    if workspace_id not in ids:
        raise ValueError(f"Workspace '{workspace_id}' not found in registry.")

    _active_workspace_id = workspace_id
    _active_dirs = workspace_dirs(workspace_id)

    registry["active_workspace_id"] = workspace_id
    _write_registry(registry)


def create_workspace(name: str) -> dict:
    """Create a new workspace, make it active, and return a summary dict."""
    # Slugify the name.
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = slug[:50]
    if not slug:
        slug = "workspace"

    # Ensure slug uniqueness.
    registry = _read_registry()
    existing_ids = {ws["id"] for ws in registry.get("workspaces", [])}
    if slug in existing_ids:
        counter = 2
        while f"{slug}-{counter}" in existing_ids:
            counter += 1
        slug = f"{slug}-{counter}"

    # Create all 5 workspace subdirectories.
    dirs = workspace_dirs(slug)
    for path in dirs.values():
        os.makedirs(path, exist_ok=True)

    # Add registry entry.
    entry = {
        "id": slug,
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    registry.setdefault("workspaces", []).append(entry)
    _write_registry(registry)

    # Activate the new workspace.
    set_active_workspace(slug)

    return {"id": slug, "name": name, "setup_required": True}


def update_workspace_name(workspace_id: str, name: str) -> None:
    """Update the display name of a workspace in the registry."""
    registry = _read_registry()
    for ws in registry.get("workspaces", []):
        if ws["id"] == workspace_id:
            ws["name"] = name
            _write_registry(registry)
            return
    raise ValueError(f"Workspace '{workspace_id}' not found.")


def delete_workspace(workspace_id: str) -> None:
    """Delete a workspace's directories and remove it from the registry."""
    workspace_root = os.path.join(WORKSPACES_BASE, workspace_id)
    if os.path.isdir(workspace_root):
        shutil.rmtree(workspace_root)

    registry = _read_registry()
    registry["workspaces"] = [ws for ws in registry.get("workspaces", []) if ws["id"] != workspace_id]

    # If the deleted workspace was active, clear the active state.
    if registry.get("active_workspace_id") == workspace_id:
        remaining = registry["workspaces"]
        registry["active_workspace_id"] = remaining[0]["id"] if remaining else None

    _write_registry(registry)

    # Sync in-memory state if needed.
    global _active_workspace_id, _active_dirs
    if _active_workspace_id == workspace_id:
        new_active = registry["active_workspace_id"]
        _active_workspace_id = new_active
        _active_dirs = workspace_dirs(new_active) if new_active else {}


def archive_workspace(workspace_id: str) -> dict:
    """Set archived=True on a workspace registry entry."""
    if workspace_id == _active_workspace_id:
        raise ValueError("Cannot archive the active workspace.")
    registry = _read_registry()
    for ws in registry.get("workspaces", []):
        if ws["id"] == workspace_id:
            ws["archived"] = True
            _write_registry(registry)
            return ws
    raise ValueError(f"Workspace '{workspace_id}' not found.")


def unarchive_workspace(workspace_id: str) -> dict:
    """Set archived=False on a workspace registry entry."""
    registry = _read_registry()
    for ws in registry.get("workspaces", []):
        if ws["id"] == workspace_id:
            ws["archived"] = False
            _write_registry(registry)
            return ws
    raise ValueError(f"Workspace '{workspace_id}' not found.")


def duplicate_workspace(source_id: str, name: str, mode: str) -> dict:
    """Duplicate a workspace. mode must be 'full' or 'template'."""
    if mode not in ("full", "template"):
        raise ValueError(f"Invalid mode: {mode!r}. Must be 'full' or 'template'.")

    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = slug[:50]
    if not slug:
        slug = "workspace"

    registry = _read_registry()
    existing_ids = {ws["id"] for ws in registry.get("workspaces", [])}

    source_entry = next((ws for ws in registry.get("workspaces", []) if ws["id"] == source_id), None)
    if source_entry is None:
        raise ValueError(f"Workspace '{source_id}' not found.")

    if slug in existing_ids:
        counter = 2
        while f"{slug}-{counter}" in existing_ids:
            counter += 1
        slug = f"{slug}-{counter}"

    source_dirs = workspace_dirs(source_id)
    new_dirs = workspace_dirs(slug)

    if mode == "full":
        for key in ("wiki_dir", "sources_dir", "archive_dir", "snapshots_dir", "schema_dir"):
            src = source_dirs[key]
            dst = new_dirs[key]
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                os.makedirs(dst, exist_ok=True)
        setup_required = False
    else:  # template
        for path in new_dirs.values():
            os.makedirs(path, exist_ok=True)
        src_schema = source_dirs["schema_dir"]
        dst_schema = new_dirs["schema_dir"]
        if os.path.isdir(src_schema):
            shutil.copytree(src_schema, dst_schema, dirs_exist_ok=True)
        wiki_config_path = os.path.join(dst_schema, "wiki_config.json")
        if os.path.isfile(wiki_config_path):
            os.remove(wiki_config_path)
        src_wiki = source_dirs["wiki_dir"]
        dst_wiki = new_dirs["wiki_dir"]
        if os.path.isdir(src_wiki):
            for item in os.listdir(src_wiki):
                src_folder = os.path.join(src_wiki, item)
                if os.path.isdir(src_folder):
                    dst_folder = os.path.join(dst_wiki, item)
                    os.makedirs(dst_folder, exist_ok=True)
                    for fname in ("_type.yaml", "_template.md"):
                        src_file = os.path.join(src_folder, fname)
                        if os.path.isfile(src_file):
                            shutil.copy2(src_file, os.path.join(dst_folder, fname))
        setup_required = True

    entry = {
        "id": slug,
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "archived": False,
    }
    registry.setdefault("workspaces", []).append(entry)
    _write_registry(registry)
    set_active_workspace(slug)

    return {"id": slug, "name": name, "setup_required": setup_required}


# ── Directory accessors (delegate to active workspace) ───────────────────────

def get_wiki_dir() -> str:
    return _active_dirs.get("wiki_dir", "")


def get_sources_dir() -> str:
    return _active_dirs.get("sources_dir", "")


def get_archive_dir() -> str:
    return _active_dirs.get("archive_dir", "")


def get_snapshots_dir() -> str:
    return _active_dirs.get("snapshots_dir", "")


def get_schema_dir() -> str:
    return _active_dirs.get("schema_dir", "")
