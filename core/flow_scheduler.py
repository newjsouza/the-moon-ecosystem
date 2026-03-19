"""
core/flow_scheduler.py
Scheduler for MoonFlow executions with time-based triggers.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading


@dataclass
class ScheduledJob:
    """Represents a scheduled job for a flow or template."""
    job_id: str
    flow_name: str               # nome de flow OU template
    job_type: str                # "flow" | "template"
    context: Dict[str, Any]      # variáveis/contexto para execução
    schedule_type: str           # "daily" | "interval" | "once"
    time_of_day: str = ""        # "07:30" — para schedule_type="daily"
    interval_minutes: int = 0    # para schedule_type="interval"
    run_at: float = 0.0          # timestamp unix — para schedule_type="once"
    enabled: bool = True
    created_at: float = 0.0
    last_run_at: float = 0.0
    next_run_at: float = 0.0
    run_count: int = 0
    last_run_id: str = ""

    def compute_next_run(self) -> float:
        """Calculate next run time based on schedule type."""
        if self.schedule_type == "daily":
            # Parse hour and minute
            hour, minute = map(int, self.time_of_day.split(":"))
            
            # Get current time
            now = datetime.datetime.now()
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # If the time has already passed today, schedule for tomorrow
            if next_run <= now:
                next_run += datetime.timedelta(days=1)
            
            return next_run.timestamp()
        elif self.schedule_type == "interval":
            # Schedule next run based on interval
            if self.last_run_at > 0:
                return self.last_run_at + (self.interval_minutes * 60)
            else:
                # If never run before, run now + interval
                return time.time() + (self.interval_minutes * 60)
        elif self.schedule_type == "once":
            # For "once" type, don't recalculate, return the fixed time
            return self.run_at
        else:
            # Default fallback
            return time.time()

    def is_due(self) -> bool:
        """Check if the job should run now."""
        return self.enabled and time.time() >= self.next_run_at


class FlowScheduler:
    """Scheduler for MoonFlow executions."""
    
    def __init__(self):
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running = False
        self._orchestrator = None
        self._lock = threading.Lock()

    def set_orchestrator(self, orchestrator) -> None:
        """Set the orchestrator for executing flows."""
        self._orchestrator = orchestrator

    def add_job(self, job: ScheduledJob) -> str:
        """Add a job to the scheduler."""
        with self._lock:
            self._jobs[job.job_id] = job
            return job.job_id

    def remove_job(self, job_id: str) -> bool:
        """Remove a job from the scheduler."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def enable_job(self, job_id: str) -> bool:
        """Enable a job."""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].enabled = True
                return True
            return False

    def disable_job(self, job_id: str) -> bool:
        """Disable a job."""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].enabled = False
                return True
            return False

    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """Get a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, enabled_only: bool = False) -> List[ScheduledJob]:
        """List all jobs or only enabled ones."""
        with self._lock:
            if enabled_only:
                return [job for job in self._jobs.values() if job.enabled]
            return list(self._jobs.values())

    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        with self._lock:
            total = len(self._jobs)
            enabled = sum(1 for job in self._jobs.values() if job.enabled)
            disabled = total - enabled
            total_runs = sum(job.run_count for job in self._jobs.values())
            
            return {
                "total_jobs": total,
                "enabled_jobs": enabled,
                "disabled_jobs": disabled,
                "total_runs": total_runs
            }

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        logger = __import__('logging').getLogger("moon.flow_scheduler")
        logger.info("FlowScheduler started")
        
        while self._running:
            try:
                await self._tick()
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Error in scheduler tick: {e}")
                await asyncio.sleep(30)  # Still sleep to prevent busy loop

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        logger = __import__('logging').getLogger("moon.flow_scheduler")
        logger.info("FlowScheduler stopped")

    async def _tick(self) -> None:
        """Internal tick method to check and run due jobs."""
        for job in self.list_jobs(enabled_only=True):
            if job.is_due():
                await self._run_job(job)

    async def _run_job(self, job: ScheduledJob) -> None:
        """Execute a scheduled job."""
        logger = __import__('logging').getLogger("moon.flow_scheduler")
        
        if not self._orchestrator:
            logger.warning(f"Cannot run job {job.job_id}: orchestrator not set")
            return

        try:
            # Update the next run time before execution
            job.next_run_at = job.compute_next_run()
            
            # Execute the flow/template based on job type
            if job.job_type == "template":
                # Use template registry to get and instantiate template
                template = self._orchestrator.template_registry.get(job.flow_name)
                if not template:
                    logger.error(f"Template '{job.flow_name}' not found for job {job.job_id}")
                    return
                
                flow = template.instantiate(job.context)
                result = await flow.execute(job.context, self._orchestrator)
            else:  # job_type == "flow"
                # Use flow registry to get flow
                flow = self._orchestrator.flow_registry.get(job.flow_name)
                if not flow:
                    logger.error(f"Flow '{job.flow_name}' not found for job {job.job_id}")
                    return
                
                result = await flow.execute(job.context, self._orchestrator)

            # Update job stats
            job.last_run_at = time.time()
            job.run_count += 1
            job.last_run_id = result.run_id
            
            logger.info(f"Job {job.job_id} ({job.flow_name}) executed successfully. Run ID: {result.run_id}")
            
            # For "once" jobs, disable after execution
            if job.schedule_type == "once":
                self.disable_job(job.job_id)
                logger.info(f"Job {job.job_id} was a 'once' job, disabling after execution")
        except Exception as e:
            logger.error(f"Failed to execute job {job.job_id}: {e}")
            # Still update next run time and stats even on failure
            job.next_run_at = job.compute_next_run()

    def load_from_file(self, path: str) -> int:
        """Load jobs from a JSON file."""
        path_obj = Path(path)
        if not path_obj.exists():
            return 0

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            loaded_count = 0
            for job_data in data.get("jobs", []):
                try:
                    job = ScheduledJob(**job_data)
                    # Compute next run time for newly loaded job
                    job.next_run_at = job.compute_next_run()
                    self.add_job(job)
                    loaded_count += 1
                except Exception as e:
                    logger = __import__('logging').getLogger("moon.flow_scheduler")
                    logger.error(f"Failed to load job from data: {e}")
                    continue

            return loaded_count
        except Exception as e:
            logger = __import__('logging').getLogger("moon.flow_scheduler")
            logger.error(f"Failed to load jobs from {path}: {e}")
            return 0

    def save_to_file(self, path: str) -> None:
        """Save jobs to a JSON file."""
        jobs_data = [asdict(job) for job in self.list_jobs()]
        data = {"jobs": jobs_data}
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# Singleton instance
_scheduler = None
_scheduler_lock = threading.Lock()


def get_flow_scheduler() -> FlowScheduler:
    """Get singleton instance of FlowScheduler."""
    global _scheduler

    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = FlowScheduler()

    return _scheduler