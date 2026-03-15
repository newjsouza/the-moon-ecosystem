"""
tests/test_system_integration.py
Integration tests for the unified Orchestrator, Channels, and ProactiveAgent.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.agent_base import AgentBase, TaskResult, AgentPriority
from channels.base import ChannelBase


# === Concrete Implementations for Testing ===

class MockAgent(AgentBase):
    """A simple mock agent for testing."""
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        if task == "fail":
            raise Exception("Intentional failure")
        return TaskResult(success=True, data={"task": task, "processed": True})


class MockChannel(ChannelBase):
    """A mock channel that records messages."""
    def __init__(self):
        super().__init__(name="mock")
        self.sent_messages = []
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_message(self, text: str, recipient_id=None, **kwargs) -> bool:
        self.sent_messages.append({"text": text, "recipient": recipient_id})
        return True


# === Channel Tests ===

class TestChannelBase:
    def test_channel_name(self):
        ch = MockChannel()
        assert ch.name == "mock"

    def test_channel_callback_registration(self):
        ch = MockChannel()
        callback = AsyncMock()
        ch.set_callback(callback)
        assert ch.on_message_received is not None

    @pytest.mark.asyncio
    async def test_channel_start_stop(self):
        ch = MockChannel()
        await ch.start()
        assert ch.started is True
        await ch.stop()
        assert ch.stopped is True

    @pytest.mark.asyncio
    async def test_channel_send_message(self):
        ch = MockChannel()
        result = await ch.send_message("Hello!", recipient_id="123")
        assert result is True
        assert len(ch.sent_messages) == 1
        assert ch.sent_messages[0]["text"] == "Hello!"
        assert ch.sent_messages[0]["recipient"] == "123"

    @pytest.mark.asyncio
    async def test_channel_handle_incoming_with_callback(self):
        ch = MockChannel()
        callback = AsyncMock()
        ch.set_callback(callback)
        await ch.handle_incoming("test message", {"source": "mock"})
        callback.assert_awaited_once_with("test message", {"source": "mock"})

    @pytest.mark.asyncio
    async def test_channel_handle_incoming_no_callback(self):
        ch = MockChannel()
        # Should not raise, just log warning
        await ch.handle_incoming("test", {})


# === Orchestrator Tests ===

class TestOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        """Create an orchestrator with mocked verification graph."""
        with patch("core.orchestrator.CodeVerificationGraph"):
            from core.orchestrator import Orchestrator
            orch = Orchestrator()
            return orch

    def test_register_agent(self, orchestrator):
        agent = MockAgent()
        orchestrator.register_agent(agent)
        assert "MockAgent" in orchestrator._agents

    def test_register_channel(self, orchestrator):
        ch = MockChannel()
        orchestrator.register_channel(ch)
        assert len(orchestrator.channels) == 1
        assert ch.on_message_received is not None

    def test_get_status(self, orchestrator):
        agent = MockAgent()
        ch = MockChannel()
        orchestrator.register_agent(agent)
        orchestrator.register_channel(ch)
        status = orchestrator.get_status()
        assert status["agents_online"] == 1
        assert status["channels_online"] == 1
        assert "MockAgent" in status["agents"]
        assert "mock" in status["channels"]

    @pytest.mark.asyncio
    async def test_execute_agent(self, orchestrator):
        agent = MockAgent()
        orchestrator.register_agent(agent)
        result = await orchestrator.execute("test task", agent_name="MockAgent")
        assert result.success is True
        assert result.data["task"] == "test task"

    @pytest.mark.asyncio
    async def test_execute_missing_agent(self, orchestrator):
        result = await orchestrator.execute("task", agent_name="NonExistent")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_handle_channel_message_status(self, orchestrator):
        ch = MockChannel()
        orchestrator.register_channel(ch)
        await orchestrator.handle_channel_message(
            "/status", {"source": "mock", "chat_id": "123"}
        )
        assert len(ch.sent_messages) == 1
        assert "The Moon" in ch.sent_messages[0]["text"]

    @pytest.mark.asyncio
    async def test_broadcast(self, orchestrator):
        ch1 = MockChannel()
        ch2 = MockChannel()
        orchestrator.register_channel(ch1)
        orchestrator.register_channel(ch2)
        await orchestrator.broadcast("Hello everyone!")
        assert len(ch1.sent_messages) == 1
        assert len(ch2.sent_messages) == 1


# === ProactiveAgent Tests ===

class TestProactiveAgent:
    @pytest.mark.asyncio
    async def test_proactive_status(self):
        from agents.proactive import ProactiveAgent
        agent = ProactiveAgent()
        result = await agent.execute("check", action="status")
        assert result.success is True
        assert result.data["scheduled_tasks"] > 0
        assert result.data["active_tasks"] > 0

    @pytest.mark.asyncio
    async def test_proactive_briefing(self):
        from agents.proactive import ProactiveAgent
        agent = ProactiveAgent()
        result = await agent.execute("generate", action="briefing")
        assert result.success is True
        assert "Johnathan" in result.data["briefing"]

    @pytest.mark.asyncio
    async def test_proactive_health(self):
        from agents.proactive import ProactiveAgent
        agent = ProactiveAgent()
        result = await agent.execute("check", action="health")
        assert result.success is True
        assert result.data["status"] == "healthy"
