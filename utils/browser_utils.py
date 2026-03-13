"""
utils/browser_utils.py
Playwright-based browser utilities for autonomous research.
"""
import asyncio
from playwright.async_api import async_playwright
from utils.logger import setup_logger

logger = setup_logger("BrowserUtils")

class BrowserManager:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        self.page = await self.context.new_page()
        logger.info("Playwright browser started.")

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'pw'):
            await self.pw.stop()
        logger.info("Playwright browser stopped.")

    async def search_duckduckgo(self, query: str):
        """Perform a DuckDuckGo search and return titles and links."""
        try:
            await self.page.goto(f"https://duckduckgo.com/html/?q={query}")
            # The HTML version is easier to scrape without heavy JS
            results = await self.page.query_selector_all(".result__a")
            data = []
            for res in results[:5]: # Top 5 results
                title = await res.inner_text()
                link = await res.get_attribute("href")
                data.append({"title": title, "link": link})
            return data
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []

    async def get_page_content(self, url: str):
        """Extract text content from a URL."""
        try:
            await self.page.goto(url, wait_until="networkidle")
            # Basic extraction - in a real scenario we'd use a better readability parser
            content = await self.page.evaluate("() => document.body.innerText")
            return content[:5000] # Limit content size
        except Exception as e:
            logger.error(f"Failed to get content from {url}: {e}")
            return ""

    async def search_youtube(self, query: str):
        """Search YouTube and return video links."""
        try:
            await self.page.goto(f"https://www.youtube.com/results?search_query={query}")
            await self.page.wait_for_selector("ytd-video-renderer")
            videos = await self.page.query_selector_all("ytd-video-renderer")
            data = []
            for v in videos[:3]:
                link_elem = await v.query_selector("#video-title")
                title = await link_elem.inner_text()
                href = await link_elem.get_attribute("href")
                data.append({"title": title, "link": f"https://www.youtube.com{href}"})
            return data
        except Exception as e:
            logger.error(f"YouTube search failed: {e}")
            return []
