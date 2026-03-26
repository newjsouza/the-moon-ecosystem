"""
skills/radar/__init__.py
Unified data type for all radar scanners.
"""
import hashlib
from dataclasses import dataclass, field


@dataclass
class RadarItem:
    """Unified data type returned by all radar scanners."""
    source: str
    title: str
    description: str
    url: str
    category: str = "general"
    relevance_score: float = 0.0
    item_hash: str = field(default="", init=True)
    timestamp: str = ""

    def __post_init__(self):
        if not self.item_hash:
            raw = f"{self.source}|{self.url}|{self.title}"
            self.item_hash = hashlib.md5(raw.encode()).hexdigest()[:16]
