"""
core/autonomous_loop.py
Manages the background research cycles.
"""
import asyncio
import time
from agents.researcher import ResearcherAgent
from utils.logger import setup_logger

logger = setup_logger("AutonomousLoop")

class MoonSleepManager:
    def __init__(self, topics=None):
        self.researcher = ResearcherAgent()
        self.topics = topics or [
            "GitHub open-source AI automation tools",
            "Machine Learning innovation 2026",
            "Autonomous Skill Agents development",
            "Multi-Agent System orchestration frameworks",
            "New AI reasoning techniques (innovation-focused)"
        ]
        self.is_running = False

    async def start_cycle(self, interval_minutes=60):
        self.is_running = True
        logger.info(f"Starting autonomous research loop. Interval: {interval_minutes}m")
        
        try:
            while self.is_running:
                for topic in self.topics:
                    if not self.is_running: break
                    
                    logger.info(f"CYCLE START: Investigating {topic}")
                    res = await self.researcher.execute(topic, action="research")
                    if res.success:
                        logger.info(f"CYCLE SUCCESS: {topic} saved to {res.data.get('vault_file')}")
                    else:
                        logger.error(f"CYCLE ERROR: {topic} failed: {res.error}")
                    
                    # Pause between topics to avoid rate limits/blocks
                    await asyncio.sleep(60) 
                
                logger.info(f"Cycle finished. Resting for {interval_minutes} minutes...")
                await asyncio.sleep(interval_minutes * 60)
        except Exception as e:
            logger.error(f"Autonomous loop crashed: {e}")
        finally:
            self.is_running = False

    def stop(self):
        self.is_running = False
        logger.info("Stopping autonomous loop.")

if __name__ == "__main__":
    # For testing: run one quick cycle
    loop = asyncio.get_event_loop()
    manager = MoonSleepManager()
    try:
        loop.run_until_complete(manager.start_cycle(interval_minutes=0.1))
    except KeyboardInterrupt:
        manager.stop()
