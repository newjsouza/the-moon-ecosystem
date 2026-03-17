import httpx
from urllib.parse import urlparse
from .schemas import WebPage
from .extractor import parse_html

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Domínios conhecidos por requerer JS — delegar ao BrowserPilot
JS_HEAVY_DOMAINS = {
    "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "facebook.com", "tiktok.com", "youtube.com", "reddit.com",
    "airbnb.com", "amazon.com.br", "mercadolivre.com.br",
}


def needs_browser(url: str) -> bool:
    """Retorna True se a URL pertence a domínio JS-heavy."""
    domain = urlparse(url).netloc.lstrip("www.")
    return any(domain.endswith(d) for d in JS_HEAVY_DOMAINS)


async def fetch_page(url: str, timeout: int = 15) -> WebPage:
    """Requisição HTTP leve via httpx."""
    async with httpx.AsyncClient(
        headers=_HEADERS, follow_redirects=True, timeout=timeout
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return parse_html(url, resp.text)
