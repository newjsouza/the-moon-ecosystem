"""
OptimizerAgent — requests retry with structured feedback when score < threshold.
Subscribes to evaluation.result topic on MessageBus.
Enforces max_retries to prevent infinite loops.
Reference: anthropics/claude-cookbooks/patterns/agents/evaluator_optimizer.ipynb
"""
import asyncio
import logging
from core.observability import observe_agent
from core.agent_base import AgentBase, TaskResult
from core.evaluation_criteria import EvaluationCriteria
from agents.llm import LLMRouter


@observe_agent
class OptimizerAgent(AgentBase):
    """
    Receives failed evaluations and orchestrates retry with feedback.
    Anti-loop protection: tracks retry counts per task_id.
    """

    AGENT_ID = "optimizer"

    def __init__(self):
        super().__init__()
        self.criteria = EvaluationCriteria()
        self.llm = LLMRouter()
        self._retry_counts: dict[str, int] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Process a failed evaluation and generate improved output.
        kwargs:
            evaluation (dict): full evaluation result from EvaluatorAgent
            original_output (str): the output that failed evaluation
            task_id (str): unique identifier for retry tracking
        """
        start = asyncio.get_event_loop().time()
        try:
            evaluation = kwargs.get("evaluation", {})
            original_output = kwargs.get("original_output", "")
            task_id = kwargs.get("task_id", task[:50])

            domain = evaluation.get("domain", "general")
            original_task = evaluation.get("original_task", task)
            feedback = evaluation.get("feedback", "Improve the response.")
            score = evaluation.get("score", 0.0)
            agent_id = evaluation.get("agent_id", "unknown")

            max_retries = self.criteria.get_max_retries(domain)
            current_retries = self._retry_counts.get(task_id, 0)

            if current_retries >= max_retries:
                self.logger.warning(
                    f"Max retries ({max_retries}) reached for task_id='{task_id}' "
                    f"[{agent_id}|{domain}] — accepting current output"
                )
                self._retry_counts.pop(task_id, None)
                return TaskResult(
                    success=True,
                    data={
                        "action": "accepted_after_max_retries",
                        "retries_used": current_retries,
                        "final_score": score,
                        "domain": domain,
                    },
                    execution_time=asyncio.get_event_loop().time() - start
                )

            self._retry_counts[task_id] = current_retries + 1
            self.logger.info(
                f"Optimizing [{agent_id}|{domain}] "
                f"attempt {current_retries + 1}/{max_retries} "
                f"score={score:.2f} feedback='{feedback}'"
            )

            improved = await self._generate_improved(
                original_task=original_task,
                original_output=original_output,
                feedback=feedback,
                domain=domain
            )

            # Publish improved output back to MessageBus for re-evaluation
            try:
                await self.bus.publish(
                    sender=self.AGENT_ID,
                    topic="optimizer.result",
                    payload={
                        "improved_output": improved,
                        "task_id": task_id,
                        "retry_number": current_retries + 1,
                        "domain": domain,
                        "agent_id": agent_id,
                        "original_task": original_task,
                    },
                    target=agent_id
                )
            except Exception as e:
                self.logger.warning(f"Failed to publish optimizer result: {e}")

            return TaskResult(
                success=True,
                data={
                    "action": "retry_generated",
                    "improved_output": improved,
                    "retry_number": current_retries + 1,
                    "domain": domain,
                    "feedback_applied": feedback,
                },
                execution_time=asyncio.get_event_loop().time() - start
            )

        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _generate_improved(self, original_task: str, original_output: str,
                                   feedback: str, domain: str) -> str:
        """Generate improved output using LLM with evaluation feedback."""
        prompt = f"""You are an AI agent in The Moon ecosystem improving your previous output.

Original task:
{original_task}

Your previous output (which needs improvement):
{original_output[:1500]}

Quality evaluator feedback:
{feedback}

Domain: {domain}

Instructions:
- Address the specific feedback provided
- Maintain the same format and intent as the original
- Improve quality without changing the core meaning
- Be concise and direct

Improved output:"""

        try:
            improved = await self.llm.complete(prompt, task_type="optimization", actor="optimizer_agent")
            return improved.strip()
        except Exception as e:
            self.logger.error(f"LLM improvement failed: {e}")
            return original_output

    def reset_retries(self, task_id: str) -> None:
        """Manually reset retry counter for a task_id."""
        self._retry_counts.pop(task_id, None)

    def get_retry_count(self, task_id: str) -> int:
        """Get current retry count for a task_id."""
        return self._retry_counts.get(task_id, 0)