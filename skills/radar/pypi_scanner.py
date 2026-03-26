"""
skills/radar/pypi_scanner.py
Scan PyPI new releases filtered by Moon-relevant keywords.
"""
import asyncio
import feedparser
import logging
from skills.radar import RadarItem

logger = logging.getLogger(__name__)

MOON_RELEVANT_KEYWORDS: list[str] = [
    "llm", "agent", "ai", "gpt", "transformer", "async",
    "automation", "telegram", "fastapi", "langchain", "groq",
    "scheduler", "workflow", "rag", "embedding", "vector",
    "mcp", "tool", "anthropic", "openai",
]

PYPI_RSS_URL = "https://pypi.org/rss/updates.xml"


async def scan_pypi_new_packages(
    keywords: list[str] | None = None,
    max_items: int = 50,
) -> list[RadarItem]:
    """Scan PyPI new releases filtered by Moon-relevant keywords."""
    kws = keywords or MOON_RELEVANT_KEYWORDS
    loop = asyncio.get_event_loop()
    try:
        feed = await loop.run_in_executor(None, feedparser.parse, PYPI_RSS_URL)
        items = []
        for entry in feed.entries[:max_items]:
            combined = f"{entry.get('title', '').lower()} {entry.get('summary', '').lower()}"
            if any(kw in combined for kw in kws):
                items.append(RadarItem(
                    source="pypi_new",
                    title=entry.get("title", ""),
                    description=(entry.get("summary") or "")[:300],
                    url=entry.get("link", ""),
                    category="python_package",
                    timestamp=entry.get("published", ""),
                ))
        return items
    except Exception as e:
        logger.error(f"PyPI scan error: {e}")
        return []
