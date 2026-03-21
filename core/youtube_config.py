"""
YouTubeConfig — topics, categories and script templates
for The Moon YouTube content automation.
"""
from dataclasses import dataclass, field
from typing import Optional


# ── Topic domains to monitor ──────────────────────────────────
YOUTUBE_DOMAINS = {
    "tech":       ["tecnologia", "inteligência artificial", "python", "programação"],
    "economy":    ["economia", "mercado financeiro", "bitcoin", "investimentos"],
    "sports":     ["brasileirao", "champions league", "futebol"],
    "philosophy": ["filosofia", "estoicismo", "geopolítica"],
    "ufology":    ["ufologia", "UAP", "fenômenos não identificados"],
}

DEFAULT_DOMAINS = ["tech", "economy"]

# ── Script structure ──────────────────────────────────────────
SCRIPT_SECTIONS = [
    "hook",           # 0-15s: gancho inicial — captura atenção
    "intro",          # 15-45s: apresentação do tema
    "development",    # 45s-7min: desenvolvimento principal
    "data_points",    # pontos de dados / evidências
    "analysis",       # análise e perspectiva única
    "cta",            # call to action
    "outro",          # encerramento + cards
]


@dataclass
class ScriptConfig:
    """Configuration for a YouTube script generation run."""
    topic: str
    domain: str = "tech"
    target_duration_min: int = 8
    language: str = "pt-BR"
    tone: str = "analytical"        # analytical | educational | narrative
    include_timestamps: bool = True
    seo_optimize: bool = True
    repurpose_to_blog: bool = True   # publish script → blog post
    notify_telegram: bool = True
    dry_run: bool = False
    thumbnail_style: str = "text_overlay"  # text_overlay | minimal | branded
    max_tags: int = 15

    # SEO
    target_keywords: list = field(default_factory=list)
    competitor_videos: list = field(default_factory=list)
