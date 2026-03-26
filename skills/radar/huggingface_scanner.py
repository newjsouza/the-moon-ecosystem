"""
skills/radar/huggingface_scanner.py
Fetch trending models and Spaces from HuggingFace public API (no key required).
"""
import httpx
import logging
from skills.radar import RadarItem

logger = logging.getLogger(__name__)


async def scan_huggingface_models(limit: int = 15) -> list[RadarItem]:
    """Fetch trending models from HuggingFace public API."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://huggingface.co/api/models",
                params={"sort": "trendingScore", "direction": -1, "limit": limit, "full": "False"},
            )
            response.raise_for_status()
        return [
            RadarItem(
                source="huggingface_models",
                title=m.get("id", m.get("modelId", "")),
                description=f"pipeline: {m.get('pipeline_tag', 'N/A')} | downloads: {m.get('downloads', 0)}",
                url=f"https://huggingface.co/{m.get('id', m.get('modelId', ''))}",
                category="llm_model",
                timestamp=m.get("lastModified", ""),
            )
            for m in response.json()
        ]
    except Exception as e:
        logger.error(f"HuggingFace models scan error: {e}")
        return []


async def scan_huggingface_spaces(limit: int = 10) -> list[RadarItem]:
    """Fetch trending Spaces from HuggingFace public API."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://huggingface.co/api/spaces",
                params={"sort": "trendingScore", "direction": -1, "limit": limit},
            )
            response.raise_for_status()
        return [
            RadarItem(
                source="huggingface_spaces",
                title=s.get("id", ""),
                description=f"sdk: {s.get('sdk', 'N/A')}",
                url=f"https://huggingface.co/spaces/{s.get('id', '')}",
                category="demo_app",
            )
            for s in response.json()
        ]
    except Exception as e:
        logger.error(f"HuggingFace spaces scan error: {e}")
        return []
