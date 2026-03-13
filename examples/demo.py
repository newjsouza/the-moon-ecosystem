"""
examples/demo.py
Demonstration of The Moon Framework
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import MoonSystem
from core.agent_base import AgentPriority

async def main():
    print("--- Starting The Moon ---")
    system = MoonSystem()
    
    await system.start()
    
    print("\n[1] Basic Analysis with ArchitectAgent")
    res1 = await system.execute("Plan a new AI feature", agent="ArchitectAgent", priority=AgentPriority.HIGH)
    print(f"Success: {res1.success}, Data: {res1.data}")
    
    print("\n[2] Credential Storage with VaultAgent")
    res2 = await system.execute("Store key", agent="VaultAgent", priority=AgentPriority.CRITICAL, action="store", key="api_key", value="sk-1234")
    print(f"Success: {res2.success}, Data: {res2.data}")
    
    print("\n[3] LLM Orchestration")
    res3 = await system.execute("Hello, how are you?", agent="LlmAgent", priority=AgentPriority.MEDIUM, provider="openai")
    print(f"Success: {res3.success}, Data: {res3.data}")

    print("\n[4] Terminal Automation (Safe Command)")
    res4 = await system.execute("echo 'The Moon Ecosystem Terminal Test'", agent="TerminalAgent", priority=AgentPriority.HIGH, command="echo 'The Moon Ecosystem Terminal Test'")
    print(f"Success: {res4.success}, Data: {res4.data}")

    print("\n[5] Terminal Automation (Unsafe Command Blocked)")
    res5 = await system.execute("rm -rf /", agent="TerminalAgent", priority=AgentPriority.HIGH, command="rm -rf /")
    print(f"Success: {res5.success}, Error: {res5.error}")

    print("\nstatus:", system.get_status())
    
    print("\n--- Stopping System ---")
    await system.stop()

if __name__ == "__main__":
    asyncio.run(main())
