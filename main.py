"""
main.py
The Moon System Entry Point
"""
import asyncio
from core.orchestrator import Orchestrator
from core.agent_base import AgentPriority
from core.config import Config
from agents import (
    ArchitectAgent, ProactiveAgent, NewsMonitorAgent, VaultAgent,
    ApiDiscoveryAgent, DesktopAgent, LlmAgent, ContextAgent,
    CrawlerAgent, ResearcherAgent, TerminalAgent,
    BlogManagerAgent, BlogWriterAgent, BlogPublisherAgent,
    PromptEnhancerAgent, DirectWriterAgent, GithubAgent,
    YoutubeManagerAgent, BettingAnalystAgent, EmailAgent,
    FileManagerAgent, OpenCodeAgent, WatchdogAgent,
    OmniChannelStrategist, AutonomousDevOpsRefactor, SkillAlchemist,
    NexusIntelligence
)
from agents.economic_sentinel import EconomicSentinel
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

class MoonSystem:
    def __init__(self, config_path=None):
        self.config = Config()
        if config_path:
            import os
            os.environ["MOON_CONFIG_PATH"] = config_path
            
        self.orchestrator = Orchestrator()
        
    def register_agents(self) -> None:
        self.orchestrator.register_agent(ArchitectAgent())
        self.orchestrator.register_agent(ProactiveAgent())
        self.orchestrator.register_agent(NewsMonitorAgent())
        self.orchestrator.register_agent(VaultAgent())
        self.orchestrator.register_agent(ApiDiscoveryAgent())
        self.orchestrator.register_agent(DesktopAgent())
        self.orchestrator.register_agent(LlmAgent(groq_client=self.orchestrator.llm))
        self.orchestrator.register_agent(ContextAgent())
        self.orchestrator.register_agent(CrawlerAgent())
        self.orchestrator.register_agent(ResearcherAgent())
        self.orchestrator.register_agent(TerminalAgent())
        self.orchestrator.register_agent(BlogManagerAgent())
        self.orchestrator.register_agent(BlogWriterAgent())
        self.orchestrator.register_agent(BlogPublisherAgent())
        self.orchestrator.register_agent(PromptEnhancerAgent())
        self.orchestrator.register_agent(DirectWriterAgent())
        self.orchestrator.register_agent(YoutubeManagerAgent())
        self.orchestrator.register_agent(BettingAnalystAgent())
        self.orchestrator.register_agent(EmailAgent())
        self.orchestrator.register_agent(FileManagerAgent())
        self.orchestrator.register_agent(GithubAgent())
        self.orchestrator.register_agent(OpenCodeAgent(groq_client=self.orchestrator.llm))
        self.orchestrator.register_agent(WatchdogAgent(message_bus=self.orchestrator.message_bus))
        
        # ── OmniChannelStrategist ──────────────────────────────
        self.orchestrator.register_agent(OmniChannelStrategist(
            message_bus=self.orchestrator.message_bus
        ))
        from agents.system_agent import SystemAgent
        from agents.hardware_synergy_bridge import HardwareSynergyBridge
        self.orchestrator.register_agent(SystemAgent())
        self.orchestrator.register_agent(HardwareSynergyBridge(
            groq_client=self.orchestrator.llm,
            message_bus=self.orchestrator.message_bus,
            orchestrator=self.orchestrator
        ))
        self.orchestrator.register_agent(AutonomousDevOpsRefactor(
            groq_client=self.orchestrator.llm,
            message_bus=self.orchestrator.message_bus,
            github_agent=self.orchestrator.get_agent("GithubAgent")
        ))
        self.orchestrator.register_agent(EconomicSentinel())
        self.orchestrator.register_agent(SkillAlchemist(orchestrator=self.orchestrator))
        self.orchestrator.register_agent(NexusIntelligence())
        
        # OpenClaw Architecture: Register Channels
        from channels.telegram import TelegramChannel
        self.orchestrator.register_channel(TelegramChannel())

    async def start(self) -> None:
        self.register_agents()
        await self.orchestrator.start()

    async def stop(self) -> None:
        await self.orchestrator.stop()

    async def execute(self, task: str, agent: str, priority: AgentPriority = AgentPriority.MEDIUM, **kwargs):
        return await self.orchestrator.execute(task, agent_name=agent, priority=priority, **kwargs)

    def get_status(self) -> dict:
        return self.orchestrator.get_status()

def run():
    async def _run():
        system = MoonSystem()
        await system.start()
        print(f"System Status: {system.get_status()}")
        await system.stop()
    asyncio.run(_run())

if __name__ == "__main__":
    run()
