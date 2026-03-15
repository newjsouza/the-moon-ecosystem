"""
Internal test script to verify orchestrator command routing.
"""
import asyncio
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.orchestrator import Orchestrator
from agents import (
    ArchitectAgent, LlmAgent, TerminalAgent, FileManagerAgent
)

async def test_routing():
    orch = Orchestrator()
    orch.register_agent(ArchitectAgent())
    orch.register_agent(LlmAgent())
    orch.register_agent(TerminalAgent())
    orch.register_agent(FileManagerAgent())

    # Mock metadata
    meta = {"source": "test_mock", "chat_id": "123"}

    print("\n--- Test 1: /ls ---")
    res = await orch._route_command("/ls", meta)
    print(res)

    print("\n--- Test 2: /cmd uname -a ---")
    res = await orch._route_command("/cmd uname -a", meta)
    print(res)

    print("\n--- Test 3: /file run_bot.py (partial) ---")
    res = await orch._route_command("/file run_bot.py", meta)
    print(res[:200] + "...")

if __name__ == "__main__":
    asyncio.run(test_routing())
