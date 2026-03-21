"""
BlogPipelineAgent — AgentBase wrapper for BlogPipeline.
Allows AutonomousLoop to dispatch blog tasks via LoopTask.
AGENT_ID: 'blog_pipeline'
"""
import asyncio
import logging
from core.agent_base import AgentBase, TaskResult
from core.observability import observe_agent
from blog.pipeline import BlogPipeline


@observe_agent
class BlogPipelineAgent(AgentBase):
    """
    Wraps BlogPipeline as an AgentBase-compliant agent.
    Task routing:
        'write'   → run full pipeline for a topic
        'dry_run' → pipeline without publishing
        'status'  → pipeline health check
    """

    AGENT_ID = "blog_pipeline"

    def __init__(self):
        super().__init__()
        self.pipeline = BlogPipeline()
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute blog pipeline.
        kwargs:
            topic (str): blog post topic — required for 'write' and 'dry_run'
            language (str): post language (default 'pt-BR')
            tags (list): post tags
            notify_telegram (bool): send Telegram notification (default True)
            max_words (int): target word count (default 800)
        """
        start = asyncio.get_event_loop().time()
        cmd = task.lower().strip()

        if cmd in ("write", "dry_run"):
            topic = kwargs.get("topic", "")
            if not topic:
                return TaskResult(
                    success=False,
                    error="'topic' kwarg required for write/dry_run commands"
                )
            is_dry_run = (cmd == "dry_run")
            return await self.pipeline.run(
                topic=topic,
                dry_run=is_dry_run,
                **{k: v for k, v in kwargs.items() if k != "topic"}
            )

        elif cmd == "status":
            return TaskResult(
                success=True,
                data={
                    "pipeline_id": BlogPipeline.PIPELINE_ID,
                    "agent_id": self.AGENT_ID,
                    "status": "ready",
                    "max_eval_retries": BlogPipeline.MAX_EVAL_RETRIES,
                },
                execution_time=asyncio.get_event_loop().time() - start
            )

        else:
            return TaskResult(
                success=False,
                error=f"Unknown command: '{cmd}'. Valid: write, dry_run, status"
            )