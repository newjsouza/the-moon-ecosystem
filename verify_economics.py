import asyncio
import os
import sys
import logging
from datetime import datetime

# Ajusta path para importar do core e agents
sys.path.append(os.getcwd())

from core.message_bus import MessageBus
from agents.economic_sentinel import EconomicSentinel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VerifyEconomics")

async def run_verification():
    logger.info("Starting EconomicSentinel Verification...")
    
    # 1. Setup MessageBus
    bus = MessageBus()
    
    # 2. Setup Agent
    agent = EconomicSentinel()
    agent.message_bus = bus
    
    # 3. Initialize
    logger.info("Step 1: Initialization")
    init_success = await agent.initialize()
    if not init_success:
        logger.error("Initialization failed!")
        return
    
    # 4. Test Single Cycle
    logger.info("Step 2: Execution Cycle")
    try:
        await agent.execute_cycle()
        logger.info("Cycle executed successfully.")
    except Exception as e:
        logger.error(f"Cycle execution failed: {e}")
        return

    # 5. Check Report
    logger.info("Step 3: Report Verification")
    reports_dir = "data/economics/reports/"
    files = os.listdir(reports_dir)
    if files:
        logger.info(f"Report found: {files[0]}")
    else:
        logger.error("No reports generated!")
        return

    logger.info("Verification COMPLETED SUCCESSFULY ✅")

if __name__ == "__main__":
    asyncio.run(run_verification())
