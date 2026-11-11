import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from api.routes import set_wiki_manager
from agent.workspace_manager import (
    get_wiki_dir, get_sources_dir, get_archive_dir, get_snapshots_dir, get_schema_dir,
    get_active_workspace_id, create_workspace,
)

export_router = APIRouter()

_APP_VERSION = "1.0.0"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@export_router.get("/bundle/full")
def export_bundle_full():
    manifest = {
        "version": 1,
        "type": "full",
        "exported_at": _utcnow(),
        "app_version": _APP_VERSION,
    }
    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            for dir_name, dir_str in [
                ("schema", get_schema_dir()),
                ("wiki", get_wiki_dir()),
                ("sources", get_sources_dir()),
                ("archive", get_archive_dir()),
                ("snapshots", get_snapshots_dir()),
            ]:
                dir_path = Path(dir_str)
                if not dir_path.exists():
                    continue
                for fp in sorted(dir_path.rglob("*")):
                    if fp.is_file():
                        rel = str(fp.relative_to(dir_path)).replace("\\", "/")
                        zf.write(fp, f"{dir_name}/{rel}")
        buf.seek(0)
        ts = _timestamp()
        return Response(
            content=buf.read(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="faragopedia-full-{ts}.zip"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Export failed") from exc


@export_router.get("/bundle/template")
def export_bundle_template():
    manifest = {
        "version": 1,
        "type": "template",
        "exported_at": _utcnow(),
        "app_version": _APP_VERSION,
    }
    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            schema_path = Path(get_schema_dir())
            if schema_path.exists():
                for fp in sorted(schema_path.rglob("*")):
                    if fp.is_file():
                        rel = str(fp.relative_to(schema_path)).replace("\\", "/")
                        zf.write(fp, f"schema/{rel}")
            wiki_path = Path(get_wiki_dir())
            if wiki_path.exists():
                for fp in sorted(wiki_path.rglob("_type.yaml")):
                    rel = str(fp.relative_to(wiki_path)).replace("\\", "/")
                    zf.write(fp, f"wiki/{rel}")
        buf.seek(0)
        ts = _timestamp()
        return Response(
            content=buf.read(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="faragopedia-template-{ts}.zip"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Export failed") from exc


@export_router.post("/import")
async def import_bundle(file: UploadFile = File(...)):
    content = await file.read()

    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive")

    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
        names = set(zf.namelist())

        # Detect optional wrapper directory (e.g. when OS re-zips an extracted folder)
        prefix = _find_bundle_prefix(names)
        if prefix is None:
            raise HTTPException(status_code=400, detail="Missing manifest.json — not a Faragopedia bundle")

        manifest = json.loads(zf.read(f"{prefix}manifest.json"))

        if manifest.get("version") != 1:
            raise HTTPException(
                status_code=400,
                detail=f"Incompatible bundle version {manifest.get('version')!r}. Expected 1.",
            )

        bundle_type = manifest.get("type")
        if bundle_type not in ("full", "template"):
            raise HTTPException(status_code=400, detail=f"Unknown bundle type {bundle_type!r}")

        if f"{prefix}schema/wiki_config.json" not in names:
            raise HTTPException(status_code=400, detail="Missing schema/wiki_config.json in bundle")

        wiki_config = json.loads(zf.read(f"{prefix}schema/wiki_config.json"))

        with tempfile.TemporaryDirectory() as staging_str:
            staging = Path(staging_str)
            zf.extractall(staging)
            # If the zip had a wrapper directory, descend into it
            actual_staging = staging / prefix.rstrip("/") if prefix else staging

            try:
                if get_active_workspace_id() is None:
                    create_workspace(wiki_config.get("wiki_name") or "Default")

                if bundle_type == "full":
                    _restore_full(actual_staging)
                    _reinit_wiki_manager()
                    return {"status": "ok", "type": "full"}
                else:
                    entity_types = _restore_template(actual_staging, wiki_config)
                    return {
                        "status": "ok",
                        "type": "template",
                        "wiki_name": wiki_config.get("wiki_name", ""),
                        "org_name": wiki_config.get("org_name", ""),
                        "org_description": wiki_config.get("org_description", ""),
                        "entity_types": entity_types,
                        "folders": [et["folder_name"] for et in entity_types],
                    }
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Restore failed: {exc}") from exc


def _find_bundle_prefix(names: set) -> "str | None":
    """Return the path prefix ('' or 'dir/') where manifest.json lives, or None."""
    if "manifest.json" in names:
        return ""
    for name in names:
        parts = name.split("/")
        if len(parts) == 2 and parts[1] == "manifest.json" and parts[0]:
            return parts[0] + "/"
    return None


def _clear_dir(path: Path) -> None:
    """Clear directory contents without deleting the directory itself."""
    for item in path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _restore_full(staging: Path) -> None:
    for dir_name, dir_str in [
        ("schema", get_schema_dir()),
        ("wiki", get_wiki_dir()),
        ("sources", get_sources_dir()),
        ("archive", get_archive_dir()),
        ("snapshots", get_snapshots_dir()),
    ]:
        target = Path(dir_str)
        source = staging / dir_name
        target.mkdir(parents=True, exist_ok=True)
        _clear_dir(target)
        if source.exists():
            shutil.copytree(source, target, dirs_exist_ok=True)

    # Ensure sources/.metadata.json exists — if missing from bundle, write empty dict
    sources_path = Path(get_sources_dir())
    metadata_path = sources_path / ".metadata.json"
    if sources_path.exists() and not metadata_path.exists():
        metadata_path.write_text("{}")


def _restore_template(staging: Path, wiki_config: dict) -> list:
    # Restore schema directory
    schema_target = Path(get_schema_dir())
    schema_staging = staging / "schema"
    schema_target.mkdir(parents=True, exist_ok=True)
    _clear_dir(schema_target)
    if schema_staging.exists():
        shutil.copytree(schema_staging, schema_target, dirs_exist_ok=True)

    # Remove wiki_config.json — setup wizard writes it after user confirms
    config_path = schema_target / "wiki_config.json"
    if config_path.exists():
        config_path.unlink()

    # Clear wiki, restore only _type.yaml files
    wiki_target = Path(get_wiki_dir())
    wiki_target.mkdir(parents=True, exist_ok=True)
    _clear_dir(wiki_target)

    wiki_staging = staging / "wiki"
    if wiki_staging.exists():
        for type_yaml in sorted(wiki_staging.rglob("_type.yaml")):
            rel = type_yaml.relative_to(wiki_staging)
            dest = wiki_target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(type_yaml, dest)

    return wiki_config.get("entity_types", [])


def _reinit_wiki_manager() -> None:
    from agent.wiki_manager import WikiManager
    try:
        wm = WikiManager(
            sources_dir=get_sources_dir(),
            wiki_dir=get_wiki_dir(),
            archive_dir=get_archive_dir(),
            snapshots_dir=get_snapshots_dir(),
            schema_dir=get_schema_dir(),
        )
        set_wiki_manager(wm)
    except Exception:
        # WikiManager may fail if LLM is not yet configured; wiki files are already
        # restored to disk. The user will configure the LLM on first use.
        pass
