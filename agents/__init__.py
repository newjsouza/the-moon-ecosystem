from .architect import ArchitectAgent
from .proactive import ProactiveAgent
from .news_monitor import NewsMonitorAgent
from .vault import VaultAgent
from .api_discovery import ApiDiscoveryAgent
# from .desktop import DesktopAgent
from .llm import LlmAgent
from .context import ContextAgent
from .crawler import CrawlerAgent
from .researcher import ResearcherAgent
from .terminal import TerminalAgent
from .blog import BlogManagerAgent, BlogWriterAgent, BlogPublisherAgent, DirectWriterAgent
from .prompt_enhancer import PromptEnhancerAgent
from .system_agent import SystemAgent
from .youtube_manager import YoutubeManagerAgent
from .betting_analyst import BettingAnalystAgent
from .email_agent import EmailAgent
from .file_manager import FileManagerAgent
from .opencode import OpenCodeAgent
from .watchdog import WatchdogAgent
from .omni_channel_strategist import OmniChannelStrategist
from .hardware_synergy_bridge import HardwareSynergyBridge
from .autonomous_devops_refactor import AutonomousDevOpsRefactor

__all__ = [
    'ArchitectAgent',
    'ProactiveAgent',
    'NewsMonitorAgent',
    'VaultAgent',
    'ApiDiscoveryAgent',
#    'DesktopAgent',
    'LlmAgent',
    'ContextAgent',
    'CrawlerAgent',
    'ResearcherAgent',
    'TerminalAgent',
    'BlogManagerAgent',
    'BlogWriterAgent',
    'BlogPublisherAgent',
    'PromptEnhancerAgent',
    'DirectWriterAgent',
    'SystemAgent',
    'YoutubeManagerAgent',
    'BettingAnalystAgent',
    'EmailAgent',
    'FileManagerAgent',
    'OpenCodeAgent',
    'WatchdogAgent',
    'OmniChannelStrategist',
    'HardwareSynergyBridge',
    'AutonomousDevOpsRefactor'
]
