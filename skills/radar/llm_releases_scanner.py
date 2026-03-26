"""
skills/radar/llm_releases_scanner.py
Scan OpenRouter (free models) and Groq (all models) for new LLM releases.
"""
import httpx
import os
import logging
from skills.radar import RadarItem

logger = logging.getLogger(__name__)


async def scan_openrouter_free_models() -> list[RadarItem]:
    """List all free (cost=0) models on OpenRouter."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
        items = []
        for model in response.json().get("data", []):
            pricing = model.get("pricing", {})
            try:
                is_free = float(pricing.get("prompt", "1")) == 0.0
            except (ValueError, TypeError):
                is_free = str(pricing.get("prompt", "1")) == "0"
            if is_free:
                items.append(RadarItem(
                    source="openrouter_free",
                    title=model.get("id", ""),
                    description=f"ctx: {model.get('context_length', '?')} | {model.get('name', '')}",
                    url=f"https://openrouter.ai/{model.get('id', '')}",
                    category="llm_model",
                ))
        return items
    except Exception as e:
        logger.error(f"OpenRouter scan error: {e}")
        return []


async def scan_groq_models() -> list[RadarItem]:
    """List all models available on Groq (all are free tier)."""
    token = os.getenv("GROQ_API_KEY", "")
    if not token:
        logger.warning("GROQ_API_KEY not set — skipping Groq scan")
        return []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
        return [
            RadarItem(
                source="groq_models",
                title=m.get("id", ""),
                description=f"owned_by: {m.get('owned_by', '?')}",
                url=f"https://console.groq.com/playground?model={m.get('id', '')}",
                category="llm_model",
            )
            for m in response.json().get("data", [])
        ]
    except Exception as e:
        logger.error(f"Groq models scan error: {e}")
        return []
