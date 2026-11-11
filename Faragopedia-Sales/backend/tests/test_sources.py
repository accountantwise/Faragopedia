from fastapi.testclient import TestClient
import sys
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# Add the project root and backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock environment variable for OpenAI API key
os.environ["OPENAI_API_KEY"] = "sk-dummy"
os.environ["AI_PROVIDER"] = "openai"
os.environ["AI_MODEL"] = "gpt-4o-mini"

from main import app
from api.routes import set_wiki_manager

client = TestClient(app)


def test_list_sources():
    mock_wm = MagicMock()
    mock_wm.list_sources.return_value = ["source1.txt", "source2.pdf"]
    set_wiki_manager(mock_wm)
    response = client.get("/api/sources")
    set_wiki_manager(None)
    assert response.status_code == 200
    assert response.json() == ["source1.txt", "source2.pdf"]


def test_get_source():
    mock_wm = MagicMock()
    mock_wm.get_source_content = AsyncMock(return_value="Source Content")
    set_wiki_manager(mock_wm)
    response = client.get("/api/sources/source1.txt")
    set_wiki_manager(None)
    assert response.status_code == 200
    assert response.json() == {"content": "Source Content"}


def test_get_source_not_found():
    mock_wm = MagicMock()
    mock_wm.get_source_content = AsyncMock(side_effect=FileNotFoundError())
    set_wiki_manager(mock_wm)
    response = client.get("/api/sources/nonexistent.txt")
    set_wiki_manager(None)
    assert response.status_code == 404


# ── Paste endpoint ────────────────────────────────────────────────────────────

def test_paste_source_happy_path(tmp_path):
    with patch("api.routes.get_sources_dir", return_value=str(tmp_path)):
        response = client.post("/api/paste", json={"content": "Hello world"})
    assert response.status_code == 200
    data = response.json()
    assert "filename" in data
    assert data["filename"].startswith("paste-")
    assert data["filename"].endswith(".txt")
    assert (tmp_path / data["filename"]).read_text(encoding="utf-8") == "Hello world"


def test_paste_source_with_custom_name(tmp_path):
    with patch("api.routes.get_sources_dir", return_value=str(tmp_path)):
        response = client.post("/api/paste", json={"content": "Notes", "name": "my notes"})
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "my_notes.txt"
    assert (tmp_path / "my_notes.txt").read_text(encoding="utf-8") == "Notes"


def test_paste_source_empty_content():
    response = client.post("/api/paste", json={"content": "   "})
    assert response.status_code == 422


def test_paste_source_with_explicit_filename(tmp_path):
    # External automations (e.g. Trigger.dev) send a full filename with its
    # own extension already chosen — it must be honored verbatim, not have
    # .txt forced onto it like the "name" field used by the paste UI.
    with patch("api.routes.get_sources_dir", return_value=str(tmp_path)):
        response = client.post(
            "/api/paste",
            json={"content": "CRM notes", "filename": "crm-john-doe-acme.md"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "crm-john-doe-acme.md"
    assert (tmp_path / "crm-john-doe-acme.md").read_text(encoding="utf-8") == "CRM notes"


def test_paste_source_explicit_filename_takes_precedence_over_name(tmp_path):
    with patch("api.routes.get_sources_dir", return_value=str(tmp_path)):
        response = client.post(
            "/api/paste",
            json={"content": "x", "filename": "explicit.md", "name": "ignored"},
        )
    assert response.status_code == 200
    assert response.json()["filename"] == "explicit.md"


def test_paste_source_explicit_filename_is_sanitized(tmp_path):
    with patch("api.routes.get_sources_dir", return_value=str(tmp_path)):
        response = client.post(
            "/api/paste",
            json={"content": "x", "filename": "../../etc/passwd.md"},
        )
    assert response.status_code == 200
    assert response.json()["filename"] == "passwd.md"
    assert (tmp_path / "passwd.md").exists()


# ── Scrape URLs endpoint ──────────────────────────────────────────────────────

def test_scrape_urls_starts_background_jobs():
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc"}):
        with patch("api.routes._crawl_and_save", new_callable=AsyncMock):
            response = client.post(
                "/api/scrape-urls",
                json={"urls": ["https://example.com", "https://other.com"]},
            )
    assert response.status_code == 202
    assert response.json()["message"] == "Started 2 crawl job(s)"


def test_scrape_urls_empty_list():
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc"}):
        response = client.post("/api/scrape-urls", json={"urls": []})
    assert response.status_code == 422


def test_scrape_urls_no_wisecrawler_url():
    env = {k: v for k, v in os.environ.items() if k != "WISECRAWLER_BASE_URL"}
    with patch.dict(os.environ, env, clear=True):
        response = client.post("/api/scrape-urls", json={"urls": ["https://example.com"]})
    assert response.status_code == 503


# ── Search endpoint ───────────────────────────────────────────────────────────

def test_search_returns_results():
    fake_results = [
        {"title": "A", "url": "https://a.com", "snippet": "a snip"},
        {"title": "B", "url": "https://b.com", "snippet": "b snip"},
    ]
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc"}):
        with patch("api.routes._wc_search", new_callable=AsyncMock, return_value=fake_results):
            response = client.post("/api/search", json={"query": "lv fall 2026", "count": 5})
    assert response.status_code == 200
    body = response.json()
    assert body == {"results": fake_results}


def test_search_default_count():
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc"}):
        with patch("api.routes._wc_search", new_callable=AsyncMock, return_value=[]) as mock:
            response = client.post("/api/search", json={"query": "x"})
    assert response.status_code == 200
    mock.assert_called_once_with("x", 10)


def test_search_empty_query():
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc"}):
        response = client.post("/api/search", json={"query": "   "})
    assert response.status_code == 422


def test_search_no_wisecrawler_url():
    env = {k: v for k, v in os.environ.items() if k != "WISECRAWLER_BASE_URL"}
    with patch.dict(os.environ, env, clear=True):
        response = client.post("/api/search", json={"query": "anything"})
    assert response.status_code == 503


def test_search_wisecrawler_503_passthrough():
    import httpx as _httpx
    def raise_503(*args, **kwargs):
        request = _httpx.Request("POST", "http://test-wc/v1/search")
        response = _httpx.Response(503, request=request, json={"detail": "BRAVE_API_KEY not configured"})
        raise _httpx.HTTPStatusError("503", request=request, response=response)

    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc"}):
        with patch("api.routes._wc_search", new_callable=AsyncMock, side_effect=raise_503):
            response = client.post("/api/search", json={"query": "x"})
    assert response.status_code == 503


def test_search_wisecrawler_429_passthrough():
    import httpx as _httpx
    def raise_429(*args, **kwargs):
        request = _httpx.Request("POST", "http://test-wc/v1/search")
        response = _httpx.Response(429, request=request, json={"detail": "Search rate limit reached"})
        raise _httpx.HTTPStatusError("429", request=request, response=response)

    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc"}):
        with patch("api.routes._wc_search", new_callable=AsyncMock, side_effect=raise_429):
            response = client.post("/api/search", json={"query": "x"})
    assert response.status_code == 429
