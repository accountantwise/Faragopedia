import os
import asyncio
import httpx

DEFAULT_ANALYZE_PROMPT = (
    "Extract and summarize all key information, facts, names, and details "
    "from this website. Be thorough."
)


def _get_base_url() -> str:
    url = os.getenv("WISECRAWLER_BASE_URL", "").rstrip("/")
    if not url:
        raise ValueError("WISECRAWLER_BASE_URL is not configured")
    return url


def _get_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    key = os.getenv("WISECRAWLER_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def start_crawl(url: str) -> str:
    """POST /v1/crawl — returns job_id."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_base_url()}/v1/crawl",
            json={"url": url, "maxDepth": 1, "limit": 10},
            headers=_get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["id"]


async def poll_until_done(job_id: str, poll_interval: float = 3.0) -> dict:
    """GET /v1/crawl/{job_id} every poll_interval seconds until status == 'completed'."""
    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                f"{_get_base_url()}/v1/crawl/{job_id}",
                headers=_get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            if data["status"] == "completed":
                return data
            if data["status"] in ("failed", "cancelled"):
                raise RuntimeError(f"Crawl {job_id} ended with status: {data['status']}")
            await asyncio.sleep(poll_interval)


async def scrape(url: str) -> str:
    """POST /v1/scrape — returns markdown content for a single URL."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_base_url()}/v1/scrape",
            json={"url": url, "formats": ["markdown"]},
            headers=_get_headers(),
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["data"]["markdown"] or ""


async def analyze_crawl(job_id: str, prompt: str = DEFAULT_ANALYZE_PROMPT) -> str:
    """POST /v1/crawl/analyze — returns the analysis string."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_base_url()}/v1/crawl/analyze",
            json={"crawl_id": job_id, "prompt": prompt},
            headers=_get_headers(),
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["analysis"]


async def search(query: str, count: int = 10) -> list[dict]:
    """POST /v1/search — returns a list of {title, url, snippet} dicts."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_base_url()}/v1/search",
            json={"query": query, "count": count},
            headers=_get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["results"]
