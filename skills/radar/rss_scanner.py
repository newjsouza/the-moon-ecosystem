"""
skills/radar/rss_scanner.py
Scan multiple RSS feeds for tech intelligence signals.
"""
import asyncio
import feedparser
import logging
from skills.radar import RadarItem

logger = logging.getLogger(__name__)

RADAR_FEEDS: dict[str, str] = {
    "hacker_news_top":  "https://hnrss.org/frontpage?points=100",
    "arxiv_ai":         "https://arxiv.org/rss/cs.AI",
    "arxiv_ml":         "https://arxiv.org/rss/cs.LG",
    "arxiv_cv":         "https://arxiv.org/rss/cs.CV",
    "github_blog":      "https://github.blog/feed/",
    "huggingface_blog": "https://huggingface.co/blog/feed.xml",
    "python_news":      "https://www.python.org/news/rss/",
}


async def scan_rss_feeds(
    feed_keys: list[str] | None = None,
    max_per_feed: int = 10,
) -> list[RadarItem]:
    """Fetch and parse multiple RSS feeds (non-blocking via run_in_executor)."""
    keys = feed_keys or list(RADAR_FEEDS.keys())
    loop = asyncio.get_event_loop()
    items: list[RadarItem] = []
    for key in keys:
        url = RADAR_FEEDS.get(key)
        if not url:
            logger.warning(f"Unknown feed key: {key}")
            continue
        try:
            feed = await loop.run_in_executor(None, feedparser.parse, url)
            for entry in feed.entries[:max_per_feed]:
                items.append(RadarItem(
                    source=f"rss_{key}",
                    title=entry.get("title", ""),
                    description=(entry.get("summary") or "")[:300],
                    url=entry.get("link", ""),
                    category="article",
                    timestamp=entry.get("published", ""),
                ))
        except Exception as e:
            logger.error(f"RSS scan error [{key}]: {e}")
    return items
