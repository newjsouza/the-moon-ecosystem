import httpx
from typing import List, Dict
from .schemas import SearchResult

_DDGO_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/122.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded",
}


async def search_duckduckgo(query: str, max_results: int = 8) -> SearchResult:
    """Busca no DuckDuckGo via HTML scraping. Custo: zero."""
    results: List[Dict[str, str]] = []

    async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
        resp = await client.post(_DDGO_URL, data={"q": query, "kl": "br-pt"})
        resp.raise_for_status()
        html = resp.text

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for r in soup.select(".result")[:max_results]:
            title_el = r.select_one(".result__title")
            url_el = r.select_one(".result__url")
            snip_el = r.select_one(".result__snippet")
            if title_el and url_el:
                raw_url = url_el.get_text(strip=True)
                if not raw_url.startswith("http"):
                    raw_url = "https://" + raw_url
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": raw_url,
                    "snippet": snip_el.get_text(strip=True) if snip_el else "",
                })
    except ImportError:
        import re
        for title, url in re.findall(
            r'class="result__title"[^>]*>(.*?)</a>.*?'
            r'class="result__url"[^>]*>(.*?)</span>',
            html, re.DOTALL
        )[:max_results]:
            results.append({"title": title.strip(), "url": url.strip(), "snippet": ""})

    return SearchResult(query=query, results=results, total_found=len(results))
