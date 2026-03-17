from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class WebPage:
    url: str
    title: str
    content: str
    links: List[str] = field(default_factory=list)
    fetched_at: str = ""
    rendered: bool = False  # True se veio do BrowserPilot (Playwright)


@dataclass
class SearchResult:
    query: str
    results: List[Dict[str, str]] = field(default_factory=list)
    source: str = "duckduckgo"
    total_found: int = 0
