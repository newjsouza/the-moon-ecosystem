"""Sprint C — Test suite for EvaluatorAgent and OptimizerAgent."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.agent_base import TaskResult


# ─────────────────────────────────────────────
# EvaluationCriteria tests
# ─────────────────────────────────────────────
class TestEvaluationCriteria:

    def setup_method(self):
        from core.evaluation_criteria import EvaluationCriteria
        self.ec = EvaluationCriteria()

    def test_instantiation(self):
        assert self.ec is not None

    def test_list_domains(self):
        domains = self.ec.list_domains()
        assert "blog" in domains
        assert "telegram" in domains
        assert "code" in domains
        assert "general" in domains

    def test_get_threshold_blog(self):
        assert self.ec.get_threshold("blog") == 0.70

    def test_get_threshold_telegram(self):
        assert self.ec.get_threshold("telegram") == 0.60

    def test_get_threshold_code(self):
        assert self.ec.get_threshold("code") == 0.75

    def test_get_threshold_unknown_domain_falls_back(self):
        threshold = self.ec.get_threshold("nonexistent_domain")
        assert 0.0 <= threshold <= 1.0

    def test_get_max_retries_blog(self):
        assert self.ec.get_max_retries("blog") == 2

    def test_get_max_retries_code(self):
        assert self.ec.get_max_retries("code") == 3

    def test_get_weights_sum_to_one(self):
        for domain in ["blog", "telegram", "code", "general"]:
            weights = self.ec.get_weights(domain)
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.01, \
                f"Weights for '{domain}' sum to {total}, expected 1.0"

    def test_get_criteria_blog_has_seo(self):
        criteria = self.ec.get_criteria("blog")
        assert "seo" in criteria.get("criteria", {})

    def test_get_criteria_telegram_has_brevity(self):
        criteria = self.ec.get_criteria("telegram")
        assert "brevity" in criteria.get("criteria", {})


# ─────────────────────────────────────────────
# EvaluatorAgent tests
# ─────────────────────────────────────────────
class TestEvaluatorAgent:

    def setup_method(self):
        from agents.evaluator import EvaluatorAgent
        self.agent = EvaluatorAgent()

    def test_instantiation(self):
        assert self.agent is not None
        assert self.agent.AGENT_ID == "evaluator"

    def test_execute_signature(self):
        import inspect
        sig = inspect.signature(self.agent._execute)
        assert 'task' in str(sig)
        assert 'kwargs' in str(sig)

    @pytest.mark.asyncio
    async def test_execute_missing_result_data(self):
        result = await self.agent._execute("evaluate")
        assert isinstance(result, TaskResult)
        assert result.success is False
        assert "result_data" in result.error

    @pytest.mark.asyncio
    async def test_execute_returns_task_result(self):
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        self.agent.bus = mock_bus

        with patch.object(self.agent, '_score_with_llm',
                          return_value=(0.80, "Good quality output")):
            result = await self.agent._execute(
                "evaluate",
                result_data="This is a test blog post about AI.",
                domain="blog",
                original_task="Write a blog post about AI",
                agent_id="blog_writer"
            )
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert "score" in result.data
        assert "passed" in result.data
        assert "feedback" in result.data

    @pytest.mark.asyncio
    async def test_evaluate_pass_threshold(self):
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        self.agent.bus = mock_bus

        with patch.object(self.agent, '_score_with_llm',
                          return_value=(0.85, "Excellent quality")):
            result = await self.agent._execute(
                "evaluate",
                result_data="High quality content",
                domain="blog",
                original_task="Write blog post"
            )
        assert result.success is True
        assert result.data["passed"] is True
        assert result.data["score"] == 0.85

    @pytest.mark.asyncio
    async def test_evaluate_fail_threshold(self):
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        self.agent.bus = mock_bus

        with patch.object(self.agent, '_score_with_llm',
                          return_value=(0.40, "Needs significant improvement")):
            result = await self.agent._execute(
                "evaluate",
                result_data="Poor quality content",
                domain="blog",
                original_task="Write blog post"
            )
        assert result.success is True
        assert result.data["passed"] is False
        assert result.data["score"] == 0.40

    @pytest.mark.asyncio
    async def test_evaluate_quick_convenience_method(self):
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        self.agent.bus = mock_bus

        with patch.object(self.agent, '_score_with_llm',
                          return_value=(0.75, "Good")):
            result = await self.agent.evaluate_quick(
                "Some content to evaluate",
                domain="telegram"
            )
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_score_parsing_valid_response(self):
        mock_response = "SCORE: 0.82\nFEEDBACK: Improve the introduction section."
        with patch.object(self.agent.llm, 'complete',
                          new_callable=AsyncMock, return_value=mock_response):
            score, feedback = await self.agent._score_with_llm(
                "test content", "blog", "write a blog post"
            )
        assert score == 0.82
        assert "introduction" in feedback

    @pytest.mark.asyncio
    async def test_score_parsing_llm_failure_uses_default(self):
        with patch.object(self.agent.llm, 'complete',
                          side_effect=Exception("LLM down")):
            score, feedback = await self.agent._score_with_llm(
                "test content", "general", "test task"
            )
        assert score == 0.65
        assert len(feedback) > 0

    @pytest.mark.asyncio
    async def test_score_clamped_between_0_and_1(self):
        mock_response = "SCORE: 1.5\nFEEDBACK: Too high score test"
        with patch.object(self.agent.llm, 'complete',
                          new_callable=AsyncMock, return_value=mock_response):
            score, _ = await self.agent._score_with_llm(
                "content", "general", "task"
            )
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_messagebus_publish_on_failure(self):
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        self.agent.bus = mock_bus

        with patch.object(self.agent, '_score_with_llm',
                          return_value=(0.30, "Very poor quality")):
            await self.agent._execute(
                "evaluate",
                result_data="bad content",
                domain="code",
                agent_id="test_agent"
            )
        mock_bus.publish.assert_called_once()
        call_kwargs = mock_bus.publish.call_args
        assert call_kwargs[1].get("target") == "optimizer" or \
               (call_kwargs[0] and "optimizer" in str(call_kwargs))


# ─────────────────────────────────────────────
# OptimizerAgent tests
# ─────────────────────────────────────────────
class TestOptimizerAgent:

    def setup_method(self):
        from agents.optimizer import OptimizerAgent
        self.agent = OptimizerAgent()

    def test_instantiation(self):
        assert self.agent is not None
        assert self.agent.AGENT_ID == "optimizer"
        assert self.agent._retry_counts == {}

    def test_execute_signature(self):
        import inspect
        sig = inspect.signature(self.agent._execute)
        assert 'task' in str(sig)
        assert 'kwargs' in str(sig)

    def test_get_retry_count_new_task(self):
        assert self.agent.get_retry_count("new_task_id") == 0

    def test_reset_retries(self):
        self.agent._retry_counts["test_id"] = 3
        self.agent.reset_retries("test_id")
        assert self.agent.get_retry_count("test_id") == 0

    @pytest.mark.asyncio
    async def test_execute_generates_retry(self):
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        self.agent.bus = mock_bus

        evaluation = {
            "domain": "blog",
            "score": 0.45,
            "passed": False,
            "feedback": "Improve the conclusion",
            "original_task": "Write a blog post",
            "agent_id": "blog_writer"
        }

        with patch.object(self.agent, '_generate_improved',
                          new_callable=AsyncMock,
                          return_value="Improved blog post content"):
            result = await self.agent._execute(
                "optimize",
                evaluation=evaluation,
                original_task="Write a blog post",
                original_output="Original poor content",
                task_id="task_001"
            )
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert result.data["action"] == "retry_generated"
        assert result.data["retry_number"] == 1

    @pytest.mark.asyncio
    async def test_max_retries_prevents_infinite_loop(self):
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        self.agent.bus = mock_bus

        self.agent._retry_counts["task_max"] = 3  # blog max_retries = 2, general = 3
        evaluation = {
            "domain": "general",
            "score": 0.30,
            "feedback": "Still needs work",
            "original_task": "test",
            "agent_id": "test_agent"
        }

        result = await self.agent._execute(
            "optimize",
            evaluation=evaluation,
            original_output="bad output",
            task_id="task_max"
        )
        assert result.success is True
        assert result.data["action"] == "accepted_after_max_retries"

    @pytest.mark.asyncio
    async def test_retry_count_increments(self):
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        self.agent.bus = mock_bus

        evaluation = {
            "domain": "telegram",
            "score": 0.50,
            "feedback": "Be more concise",
            "original_task": "Answer user question",
            "agent_id": "telegram_bot"
        }

        with patch.object(self.agent, '_generate_improved',
                          new_callable=AsyncMock, return_value="More concise answer"):
            await self.agent._execute(
                "optimize",
                evaluation=evaluation,
                original_output="Very long answer",
                task_id="task_retry"
            )
        assert self.agent.get_retry_count("task_retry") == 1

    @pytest.mark.asyncio
    async def test_generate_improved_llm_failure_returns_original(self):
        with patch.object(self.agent.llm, 'complete',
                          side_effect=Exception("LLM unavailable")):
            result = await self.agent._generate_improved(
                original_task="test task",
                original_output="original content",
                feedback="needs work",
                domain="general"
            )
        assert result == "original content"

    @pytest.mark.asyncio
    async def test_generate_improved_uses_feedback(self):
        improved = "Better content addressing the feedback"
        with patch.object(self.agent.llm, 'complete',
                          new_callable=AsyncMock, return_value=improved):
            result = await self.agent._generate_improved(
                original_task="Write something",
                original_output="bad content",
                feedback="Needs to be more specific",
                domain="blog"
            )
        assert result == improved


# ─────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────
class TestSprintCIntegration:

    def test_evaluator_import(self):
        from agents.evaluator import EvaluatorAgent
        assert EvaluatorAgent is not None

    def test_optimizer_import(self):
        from agents.optimizer import OptimizerAgent
        assert OptimizerAgent is not None

    def test_criteria_import(self):
        from core.evaluation_criteria import EvaluationCriteria
        assert EvaluationCriteria is not None

    def test_evaluation_criteria_yaml_exists(self):
        from pathlib import Path
        assert Path("evaluation_criteria.yaml").exists()

    def test_evaluator_is_agent_base(self):
        from agents.evaluator import EvaluatorAgent
        from core.agent_base import AgentBase
        assert issubclass(EvaluatorAgent, AgentBase)

    def test_optimizer_is_agent_base(self):
        from agents.optimizer import OptimizerAgent
        from core.agent_base import AgentBase
        assert issubclass(OptimizerAgent, AgentBase)

    def test_evaluator_distinct_from_optimizer(self):
        from agents.evaluator import EvaluatorAgent
        from agents.optimizer import OptimizerAgent
        assert EvaluatorAgent.AGENT_ID != OptimizerAgent.AGENT_ID

    @pytest.mark.asyncio
    async def test_full_eval_optimizer_loop(self):
        """Integration: EvaluatorAgent fails → OptimizerAgent improves."""
        from agents.evaluator import EvaluatorAgent
        from agents.optimizer import OptimizerAgent

        evaluator = EvaluatorAgent()
        optimizer = OptimizerAgent()
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        evaluator.bus = mock_bus
        optimizer.bus = mock_bus

        # Step 1: Evaluate — fails
        with patch.object(evaluator, '_score_with_llm',
                          return_value=(0.45, "Needs better structure")):
            eval_result = await evaluator._execute(
                "evaluate",
                result_data="Weak blog post content",
                domain="blog",
                original_task="Write blog post about AI",
                agent_id="blog_writer"
            )

        assert eval_result.success is True
        assert eval_result.data["passed"] is False

        # Step 2: Optimizer improves
        with patch.object(optimizer, '_generate_improved',
                          new_callable=AsyncMock,
                          return_value="Improved blog post with better structure"):
            opt_result = await optimizer._execute(
                "optimize",
                evaluation=eval_result.data,
                original_output="Weak blog post content",
                task_id="integration_test_001"
            )

        assert opt_result.success is True
        assert opt_result.data["action"] == "retry_generated"
        assert "Improved" in opt_result.data["improved_output"]