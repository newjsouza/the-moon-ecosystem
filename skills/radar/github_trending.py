"""
skills/radar/github_trending.py
Fetch recently created trending repositories via GitHub Search API.
"""
import httpx
import os
import logging
from datetime import datetime, timedelta
from skills.radar import RadarItem

logger = logging.getLogger(__name__)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


async def scan_github_trending(
    days_back: int = 7,
    per_page: int = 25,
) -> list[RadarItem]:
    """Fetch recently created trending repositories via GitHub Search API."""
    since_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    query = f"created:>{since_date} stars:>50"
    url = "https://api.github.com/search/repositories"
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": per_page}
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "TheMoonRadar/1.0"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
        return [
            RadarItem(
                source="github_trending",
                title=repo.get("full_name", ""),
                description=(repo.get("description") or "")[:300],
                url=repo.get("html_url", ""),
                category="code_repository",
                timestamp=repo.get("created_at", ""),
            )
            for repo in response.json().get("items", [])
        ]
    except Exception as e:
        logger.error(f"GitHub trending scan error: {e}")
        return []
