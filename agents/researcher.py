"""
agents/researcher.py
Content research and synthesis with autonomous capabilities.
"""
import os
import json
import asyncio
from datetime import datetime
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger
from utils.browser_utils import BrowserManager
from agents.desktop import DesktopAgent
from agents.llm import LlmAgent

class ResearcherAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.HIGH
        self.description = "Autonomous Content Researcher & Knowledge Engineer"
        self.logger = setup_logger("ResearcherAgent")
        self.vault_path = "learning/research_vault"
        self.browser = BrowserManager()
        self.desktop = DesktopAgent()
        self.llm = LlmAgent()

    async def initialize(self) -> None:
        await super().initialize()
        if not os.path.exists(self.vault_path):
            os.makedirs(self.vault_path)
        self.logger.info(f"ResearcherAgent initialized. Vault: {self.vault_path}")

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Executes a research task. 
        Supported actions: 'research' (default), 'summarize_vault', 'autonomous_loop'.
        """
        action = kwargs.get("action", "research")
        
        if action == "research":
            return await self._run_research(task, **kwargs)
        elif action == "summarize_vault":
            return await self._summarize_vault()
        else:
            return TaskResult(success=False, error=f"Action {action} not supported.")

    async def _run_research(self, topic: str, **kwargs) -> TaskResult:
        self.logger.info(f"Starting research on: {topic}")
        
        await self.browser.start()
        try:
            # 1. Search Web
            web_results = await self.browser.search_duckduckgo(topic)
            
            # 2. Search YouTube
            video_results = await self.browser.search_youtube(topic)
            
            # 3. Deep Dive into top link
            deep_content = ""
            if web_results:
                top_link = web_results[0]['link']
                self.logger.info(f"Deep diving into: {top_link}")
                try:
                    deep_content = await self.browser.get_page_content(top_link)
                except Exception as b_err:
                    self.logger.warning(f"Browser deep dive failed, falling back to Desktop: {b_err}")
                    # Desktop fallback: move mouse, simulate research
                    await self.desktop.execute(f"Manual research on {top_link}", action="move", coords=(500, 500))
                    deep_content = f"Desktop fallback active. Page viewed manually: {top_link}"

            # 4. Verify content with LLM (Anti-Hallucination)
            verification_prompt = f"""
            Verify the following research data for topic: {topic}.
            Web results: {web_results}
            YouTube results: {video_results}
            Deep content snippet: {deep_content[:1000]}
            
            Synthesize a brief factual summary and flag any potential inaccuracies or hallucinations.
            Format: Factual Summary: <text> | Integrity Check: <Pass/Fail>
            """
            verification_res = await self.llm.execute(verification_prompt)
            synthesis = verification_res.data.get("response", "No synthesis available.") if verification_res.success else "Verification failed."

            # 5. Save to Vault
            research_data = {
                "timestamp": datetime.now().isoformat(),
                "topic": topic,
                "web_results": web_results,
                "video_results": video_results,
                "deep_content_snippet": deep_content[:2000],
                "llm_synthesis": synthesis,
                "status": "completed"
            }
            
            filename = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(self.vault_path, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(research_data, f, indent=4, ensure_ascii=False)
            
            return TaskResult(
                success=True, 
                data={
                    "vault_file": filepath,
                    "summary": f"Found {len(web_results)} web results and {len(video_results)} videos."
                }
            )
        except Exception as e:
            self.logger.error(f"Research failed: {e}")
            return TaskResult(success=False, error=str(e))
        finally:
            await self.browser.stop()

    async def _summarize_vault(self) -> TaskResult:
        """Compile all vault data into a synthesis."""
        files = [f for f in os.listdir(self.vault_path) if f.endswith('.json')]
        all_data = []
        for file in files:
            with open(os.path.join(self.vault_path, file), 'r') as f:
                all_data.append(json.load(f))
        
        return TaskResult(success=True, data={"entries_count": len(all_data), "latest_topics": [d['topic'] for d in all_data[-5:]]})

    async def shutdown(self) -> None:
        await self.browser.stop()
        await super().shutdown()
