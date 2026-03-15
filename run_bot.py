#!/usr/bin/env python3
"""
run_bot.py — Launches The Moon with Telegram channel active.

Usage:
    python run_bot.py          # Start with Telegram channel + proactive loop
    python run_bot.py --test   # Send a test message and exit
"""

import asyncio
import sys
import os
import signal
import logging

# Configure logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


async def test_bot():
    """Send a test message and exit."""
    from channels.telegram import TelegramChannel

    ch = TelegramChannel()
    print(f"Token: {ch.token[:20]}..." if ch.token else "NO TOKEN")
    print(f"Chat ID: {ch.chat_id}")

    # Quick test via curl
    success = await ch.send_message(
        "🌙 *The Moon — Teste Rápido*\n\n"
        "Bot está online e funcionando!\n"
        "Envie qualquer mensagem para interagir."
    )
    print(f"Message sent: {success}")


async def main():
    """Start the full system with Telegram channel."""
    from core.orchestrator import Orchestrator
    from channels.telegram import TelegramChannel
    from agents import (
        ArchitectAgent, ProactiveAgent, NewsMonitorAgent, VaultAgent,
        ApiDiscoveryAgent, # DesktopAgent, 
        LlmAgent, ContextAgent,
        CrawlerAgent, ResearcherAgent, TerminalAgent,
        BlogManagerAgent, BlogWriterAgent, BlogPublisherAgent,
        PromptEnhancerAgent, DirectWriterAgent,
        YoutubeManagerAgent, BettingAnalystAgent, EmailAgent,
        FileManagerAgent, OpenCodeAgent, GithubAgent, NexusIntelligence
    )
    from agents.system_agent import SystemAgent

    print("🌙 The Moon — Initializing...")

    orch = Orchestrator()

    # Register core agents
    agents = [
        ArchitectAgent(), ProactiveAgent(), NewsMonitorAgent(), VaultAgent(),
        ApiDiscoveryAgent(), # DesktopAgent(), 
        LlmAgent(groq_client=orch.llm), ContextAgent(),
        CrawlerAgent(), ResearcherAgent(), TerminalAgent(),
        BlogManagerAgent(), BlogWriterAgent(), BlogPublisherAgent(),
        PromptEnhancerAgent(), DirectWriterAgent(),
        YoutubeManagerAgent(), BettingAnalystAgent(), EmailAgent(),
        FileManagerAgent(), OpenCodeAgent(groq_client=orch.llm), 
        GithubAgent(), SystemAgent(), NexusIntelligence()
    ]
    for agent in agents:
        orch.register_agent(agent)

    # Register Telegram channel
    telegram = TelegramChannel()
    orch.register_channel(telegram)

    # Launch KeyVault Service in the background
    from core.services.key_vault import app as kv_app
    import uvicorn
    config = uvicorn.Config(kv_app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())
    print("🚀 KeyVault Service running on http://localhost:8080")

    print(f"✅ Agents: {len(orch._agents)}")
    print(f"✅ Channels: {len(orch.channels)}")
    print("🚀 Starting Orchestrator...")

    # Handle graceful shutdown
    loop = asyncio.get_event_loop()

    def handle_signal():
        print("\n🛑 Shutting down...")
        asyncio.create_task(orch.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    try:
        await orch.start()
        # Keep running
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await orch.stop()
        print("The Moon stopped.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        asyncio.run(test_bot())
    else:
        asyncio.run(main())
