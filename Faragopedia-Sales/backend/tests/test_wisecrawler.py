import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def make_mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = json_data
    mock.status_code = status_code
    return mock


def make_mock_client(post_response=None, get_responses=None):
    """Build a mock httpx.AsyncClient context manager."""
    mock_client = AsyncMock()
    if post_response:
        mock_client.post = AsyncMock(return_value=post_response)
    if get_responses:
        mock_client.get = AsyncMock(side_effect=get_responses)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_start_crawl_returns_job_id():
    mock_client = make_mock_client(
        post_response=make_mock_response({"id": "job-abc123", "url": "https://example.com"})
    )
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": "test-key"}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            from agent.wisecrawler import start_crawl
            result = await start_crawl("https://example.com")

    assert result == "job-abc123"
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[1]["json"]["url"] == "https://example.com"
    assert "Authorization" in call_kwargs[1]["headers"]


@pytest.mark.asyncio
async def test_poll_until_done_waits_for_completion():
    get_responses = [
        make_mock_response({"status": "scraping", "total": 3, "completed": 1}),
        make_mock_response({"status": "scraping", "total": 3, "completed": 2}),
        make_mock_response({"status": "completed", "total": 3, "completed": 3, "data": []}),
    ]
    mock_client = make_mock_client(get_responses=get_responses)
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": ""}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            with patch("agent.wisecrawler.asyncio.sleep", new_callable=AsyncMock):
                from agent.wisecrawler import poll_until_done
                result = await poll_until_done("job-abc123", poll_interval=0)

    assert result["status"] == "completed"
    assert mock_client.get.call_count == 3


@pytest.mark.asyncio
async def test_poll_until_done_raises_on_failure():
    get_responses = [
        make_mock_response({"status": "failed"}),
    ]
    mock_client = make_mock_client(get_responses=get_responses)
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": ""}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            with patch("agent.wisecrawler.asyncio.sleep", new_callable=AsyncMock):
                from agent.wisecrawler import poll_until_done
                with pytest.raises(RuntimeError, match="failed"):
                    await poll_until_done("job-abc123", poll_interval=0)


@pytest.mark.asyncio
async def test_analyze_crawl_returns_analysis():
    mock_client = make_mock_client(
        post_response=make_mock_response({
            "success": True,
            "crawl_id": "job-abc123",
            "analysis": "Key findings: the site covers X and Y.",
        })
    )
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": ""}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            from agent.wisecrawler import analyze_crawl
            result = await analyze_crawl("job-abc123", "Summarize this.")

    assert result == "Key findings: the site covers X and Y."
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[1]["json"]["crawl_id"] == "job-abc123"
    assert call_kwargs[1]["json"]["prompt"] == "Summarize this."


@pytest.mark.asyncio
async def test_search_returns_results():
    mock_client = make_mock_client(
        post_response=make_mock_response({
            "results": [
                {"title": "First", "url": "https://a.com", "snippet": "first snippet"},
                {"title": "Second", "url": "https://b.com", "snippet": "second snippet"},
            ]
        })
    )
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": "test-key"}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            from agent.wisecrawler import search
            result = await search("lv fall 2026", count=5)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == {"title": "First", "url": "https://a.com", "snippet": "first snippet"}
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[1]["json"] == {"query": "lv fall 2026", "count": 5}
    assert call_kwargs[0][0].endswith("/v1/search")
    assert "Authorization" in call_kwargs[1]["headers"]


@pytest.mark.asyncio
async def test_search_uses_default_count():
    mock_client = make_mock_client(
        post_response=make_mock_response({"results": []})
    )
    with patch.dict(os.environ, {"WISECRAWLER_BASE_URL": "http://test-wc", "WISECRAWLER_API_KEY": "test-key"}):
        with patch("agent.wisecrawler.httpx.AsyncClient", return_value=mock_client):
            from agent.wisecrawler import search
            await search("anything")
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[1]["json"]["count"] == 10


@pytest.mark.asyncio
async def test_search_raises_when_base_url_missing():
    env = {k: v for k, v in os.environ.items() if k != "WISECRAWLER_BASE_URL"}
    with patch.dict(os.environ, env, clear=True):
        from agent.wisecrawler import search
        with pytest.raises(ValueError, match="WISECRAWLER_BASE_URL"):
            await search("anything")
