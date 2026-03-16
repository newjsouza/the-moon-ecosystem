"""
core/autonomous_loop.py
Manages the background research cycles.
Connected to the Orchestrator for channel broadcasts.

Updated: Moon-Stack QA automático integrado (FASE 6)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.orchestrator import Orchestrator

logger = logging.getLogger("moon.core.autonomous_loop")


class MoonSleepManager:
    """
    The autonomous research engine.
    Runs in the background, researching topics and pushing
    findings through the Orchestrator's channels.
    """

    def __init__(self, orchestrator: Optional["Orchestrator"] = None, topics: Optional[List[str]] = None):
        self.orchestrator = orchestrator
        self.topics = topics or [
            "GitHub open-source AI automation tools",
            "Machine Learning innovation 2026",
            "Autonomous Skill Agents development",
            "Multi-Agent System orchestration frameworks",
            "New AI reasoning techniques (innovation-focused)"
        ]
        self.is_running = False
        self.cycle_count = 0

        # Moon-Stack QA Settings
        self.qa_interval_hours = 6  # QA automático a cada 6 horas
        self._qa_task: Optional[asyncio.Task] = None

    async def start_cycle(self, interval_minutes: int = 60) -> None:
        self.is_running = True
        logger.info(f"Starting autonomous research loop. Interval: {interval_minutes}m")

        # Start QA scheduled loop
        await self._start_qa_loop()

        try:
            while self.is_running:
                self.cycle_count += 1
                logger.info(f"=== Research Cycle #{self.cycle_count} ===")

                findings = []
                for topic in self.topics:
                    if not self.is_running:
                        break

                    logger.info(f"CYCLE: Investigating '{topic}'")

                    # Try to use the ResearcherAgent if orchestrator is available
                    if self.orchestrator and "ResearcherAgent" in self.orchestrator._agents:
                        try:
                            res = await self.orchestrator._agents["ResearcherAgent"].execute(
                                topic, action="research"
                            )
                            if res.success:
                                findings.append(f"✅ {topic}")
                                logger.info(f"CYCLE SUCCESS: {topic}")
                            else:
                                findings.append(f"⚠️ {topic}: {res.error}")
                                logger.error(f"CYCLE ERROR: {topic}: {res.error}")
                        except Exception as e:
                            findings.append(f"❌ {topic}: {e}")
                            logger.error(f"CYCLE EXCEPTION: {topic}: {e}")
                    else:
                        findings.append(f"📋 {topic} (pesquisa pendente)")

                    # Pause between topics
                    await asyncio.sleep(30)

                # Broadcast findings via channels
                if self.orchestrator and findings:
                    now = datetime.now().strftime("%H:%M")
                    report = (
                        f"🔬 *Pesquisa Autônoma — Ciclo #{self.cycle_count}*\n"
                        f"🕐 {now}\n\n" +
                        "\n".join(findings) +
                        f"\n\n_Próximo ciclo em {interval_minutes} minutos._"
                    )
                    await self.orchestrator.broadcast(report)

                logger.info(f"Cycle #{self.cycle_count} complete. Resting for {interval_minutes} minutes...")
                await asyncio.sleep(interval_minutes * 60)

        except asyncio.CancelledError:
            logger.info("Autonomous loop cancelled gracefully.")
        except Exception as e:
            logger.error(f"Autonomous loop crashed: {e}")
        finally:
            self.is_running = False
            self.stop_qa_loop()

    async def _start_qa_loop(self) -> None:
        """Inicia loop de QA automático do Moon-Stack."""
        async def qa_cycle():
            logger.info(f"Moon-Stack QA started (interval: {self.qa_interval_hours}h)")

            while self.is_running:
                await asyncio.sleep(self.qa_interval_hours * 3600)

                if not self.is_running:
                    break

                logger.info("=== Moon-Stack QA Cycle ===")

                try:
                    # Run QA via MoonQAAgent if available
                    if self.orchestrator and "MoonQAAgent" in self.orchestrator._agents:
                        qa_agent = self.orchestrator._agents["MoonQAAgent"]
                        result = await qa_agent.execute("diff-aware")

                        if result.success:
                            health = result.data.get("overall_health", 0)
                            apps = result.data.get("apps_tested", [])

                            # Report via MessageBus
                            from core.message_bus import MessageBus
                            message_bus = MessageBus()
                            await message_bus.publish(
                                sender="AutonomousLoop",
                                topic="qa.scheduled",
                                payload={
                                    "health": health,
                                    "apps_tested": apps,
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )

                            logger.info(f"QA completed: health={health}, apps={apps}")
                        else:
                            logger.warning(f"QA failed: {result.error}")
                    else:
                        logger.debug("MoonQAAgent not available for scheduled QA")

                except Exception as e:
                    logger.error(f"Scheduled QA failed: {e}")

        self._qa_task = asyncio.create_task(qa_cycle(), name="moon.qa.autonomous")

    def stop_qa_loop(self) -> None:
        """Para o loop de QA automático."""
        if self._qa_task and not self._qa_task.done():
            self._qa_task.cancel()
            logger.info("Moon-Stack QA loop stopped.")

    def stop(self) -> None:
        self.is_running = False
        logger.info("Stopping autonomous loop.")
        self.stop_qa_loop()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    manager = MoonSleepManager()
    try:
        loop.run_until_complete(manager.start_cycle(interval_minutes=1))
    except KeyboardInterrupt:
        manager.stop()
