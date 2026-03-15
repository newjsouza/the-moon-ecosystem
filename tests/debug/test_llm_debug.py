import asyncio
import sys
import os

# Ensure the project root is in path
sys.path.append(os.getcwd())

from agents.llm import LlmAgent

async def test():
    print("Instantiating LlmAgent...")
    agent = LlmAgent()
    print(f"Agent instantiated: {agent}")
    print(f"Has logger? {hasattr(agent, 'logger')}")
    if hasattr(agent, 'logger'):
        print(f"Logger value: {agent.logger}")
        agent.logger.info("Test logger info")
    else:
        print("CRITICAL: Logger attribute is MISSING!")

if __name__ == "__main__":
    asyncio.run(test())
