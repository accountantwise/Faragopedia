import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.routes import router as api_router, set_wiki_manager
from api.setup_routes import setup_router
from api.export_routes import export_router
from api.workspace_routes import workspace_router
from api.job_links import job_links_router
from agent.setup_wizard import is_setup_complete
from agent.workspace_manager import (
    initialize_workspaces, get_active_workspace_id,
    get_wiki_dir, get_sources_dir, get_archive_dir, get_snapshots_dir, get_schema_dir,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def external_api_key_middleware(request: Request, call_next):
    # cf-connecting-ip is injected by Cloudflare on ALL tunneled requests,
    # including normal browser traffic to the main frontend hostname — it
    # does not distinguish the external Trigger.dev automation from a real
    # user. Gate only requests arriving on the dedicated external-API
    # hostname instead.
    external_hostname = os.getenv("FARAGOPEDIA_API_HOSTNAME", "")
    is_api_route = request.url.path.startswith("/api/")
    request_host = request.headers.get("host", "").split(":")[0]
    api_key = os.getenv("FARAGOPEDIA_API_KEY", "")

    if external_hostname and is_api_route and request_host == external_hostname and api_key:
        key = request.headers.get("x-api-key", "")
        if key != api_key:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    return await call_next(request)

app.include_router(api_router, prefix="/api")
app.include_router(setup_router, prefix="/api/setup")
app.include_router(export_router, prefix="/api/export")
app.include_router(workspace_router, prefix="/api/workspaces")
# Source-document link resolver. Under /api so the wiki frontend's same-origin proxy
# serves it to a browser without a separate access policy.
app.include_router(job_links_router, prefix="/api")

initialize_workspaces()
active_id = get_active_workspace_id()
if active_id and is_setup_complete(get_schema_dir()):
    from agent.wiki_manager import WikiManager
    wm = WikiManager(
        sources_dir=get_sources_dir(),
        wiki_dir=get_wiki_dir(),
        archive_dir=get_archive_dir(),
        snapshots_dir=get_snapshots_dir(),
        schema_dir=get_schema_dir(),
    )
    set_wiki_manager(wm)

@app.get("/")
def read_root():
    return {"message": "Hello World from FastAPI"}
