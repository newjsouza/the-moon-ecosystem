"""
agents/crawler.py
Web crawling using bs4.
"""
from core.agent_base import AgentBase, TaskResult, AgentPriority

try:
    import aiohttp
    from bs4 import BeautifulSoup
except ImportError:
    aiohttp = None
    BeautifulSoup = None

class CrawlerAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.HIGH
        self.description = "Web Crawler"

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        if aiohttp is None or BeautifulSoup is None:
            return TaskResult(success=False, error="Missing crawler dependencies.")
            
        url = kwargs.get("url", "http://example.com")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    text = await resp.text()
                    soup = BeautifulSoup(text, "lxml")
                    title = soup.title.string if soup.title else ""
                    return TaskResult(success=True, data={"url": url, "title": title})
        except Exception as e:
             return TaskResult(success=False, error=str(e))
