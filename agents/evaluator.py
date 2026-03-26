"""
EvaluatorAgent — scores TaskResult outputs from all agents.
Subscribes to MessageBus. Non-blocking — never holds the main pipeline.
Emits evaluation.result topic for OptimizerAgent to consume.
Reference: anthropics/claude-cookbooks/patterns/agents/evaluator_optimizer.ipynb
"""
import asyncio
import logging
from core.observability import observe_agent
from core.agent_base import AgentBase, TaskResult
from core.evaluation_criteria import EvaluationCriteria
from agents.llm import LLMRouter


@observe_agent
class EvaluatorAgent(AgentBase):
    """
    Evaluates quality of TaskResult outputs using LLM-based scoring.
    Runs non-blocking after each agent completes.
    Publishes evaluation.result to MessageBus.
    """

    AGENT_ID = "evaluator"

    def __init__(self):
        super().__init__()
        self.criteria = EvaluationCriteria()
        self.llm = LLMRouter()
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Evaluate a TaskResult output.
        kwargs:
            result_data (str|dict): the output to evaluate
            domain (str): criteria domain (blog, telegram, code, general)
            original_task (str): the original task that produced this output
            agent_id (str): which agent produced this result
        """
        start = asyncio.get_event_loop().time()
        try:
            result_data = kwargs.get("result_data", "")
            domain = kwargs.get("domain", "general")
            original_task = kwargs.get("original_task", task)
            agent_id = kwargs.get("agent_id", "unknown")

            if not result_data:
                return TaskResult(
                    success=False,
                    error="result_data is required for evaluation",
                    execution_time=asyncio.get_event_loop().time() - start
                )

            score, feedback = await self._score_with_llm(
                result_data=str(result_data),
                domain=domain,
                original_task=original_task
            )

            threshold = self.criteria.get_threshold(domain)
            passed = score >= threshold

            self.logger.info(
                f"Evaluation [{agent_id}|{domain}]: "
                f"score={score:.2f} threshold={threshold:.2f} "
                f"{'PASS ✅' if passed else 'FAIL ⚠️'}"
            )

            evaluation = {
                "score": score,
                "threshold": threshold,
                "passed": passed,
                "domain": domain,
                "agent_id": agent_id,
                "feedback": feedback,
                "original_task": original_task,
            }

            # Publish to MessageBus for OptimizerAgent
            try:
                await self.bus.publish(
                    sender=self.AGENT_ID,
                    topic="evaluation.result",
                    payload=evaluation,
                    target="optimizer" if not passed else None
                )
            except Exception as e:
                self.logger.warning(f"Failed to publish evaluation to bus: {e}")

            return TaskResult(
                success=True,
                data=evaluation,
                execution_time=asyncio.get_event_loop().time() - start
            )

        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _score_with_llm(self, result_data: str, domain: str,
                               original_task: str) -> tuple[float, str]:
        """Use LLM to score output against domain criteria. Returns (score, feedback)."""
        weights = self.criteria.get_weights(domain)
        criteria_list = "\n".join(
            [f"- {name} (weight {w:.0%})" for name, w in weights.items()]
        )

        prompt = f"""You are a strict quality evaluator for an AI agent system called The Moon.

Task that was given to the agent:
{original_task}

Agent output to evaluate:
{result_data[:2000]}

Evaluation criteria for domain '{domain}':
{criteria_list}

Instructions:
1. Score each criterion from 0.0 to 1.0
2. Calculate weighted average score
3. Provide brief, actionable feedback for improvement

Respond in this exact format:
SCORE: <0.0 to 1.0>
FEEDBACK: <one sentence of actionable feedback>"""

        try:
            response = await self.llm.complete(prompt, task_type="evaluation", actor="evaluator_agent")
            lines = response.strip().split("\n")
            score = 0.65
            feedback = "Evaluation completed."

            for line in lines:
                if line.startswith("SCORE:"):
                    raw = line.replace("SCORE:", "").strip()
                    score = max(0.0, min(1.0, float(raw)))
                elif line.startswith("FEEDBACK:"):
                    feedback = line.replace("FEEDBACK:", "").strip()

            return score, feedback
        except Exception as e:
            self.logger.warning(f"LLM scoring failed: {e} — using default score 0.65")
            return 0.65, f"Scoring unavailable: {str(e)}"

    async def evaluate_quick(self, result_data: str, domain: str = "general",
                              original_task: str = "") -> TaskResult:
        """Convenience method for direct evaluation without MessageBus."""
        return await self._execute(
            task="evaluate",
            result_data=result_data,
            domain=domain,
            original_task=original_task,
            agent_id="direct"
        )