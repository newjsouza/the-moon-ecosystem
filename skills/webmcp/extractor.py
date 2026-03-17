import re
from datetime import datetime, timezone
from typing import List
from .schemas import WebPage

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False


def _naive_strip(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s{2,}", " ", html).strip()


def extract_links(html: str) -> List[str]:
    if _BS4:
        soup = BeautifulSoup(html, "html.parser")
        return [
            a["href"] for a in soup.find_all("a", href=True)
            if a["href"].startswith("http")
        ][:40]
    return re.findall(r'href=["\'](https?://[^"\']{10,})["\']', html)[:40]


def parse_html(url: str, html: str, rendered: bool = False) -> WebPage:
    if _BS4:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        content = soup.get_text(separator="\n", strip=True)
    else:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = m.group(1).strip() if m else ""
        content = _naive_strip(html)

    return WebPage(
        url=url,
        title=title,
        content=content[:8000],
        links=extract_links(html),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        rendered=rendered,
    )
