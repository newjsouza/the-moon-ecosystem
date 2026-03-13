"""
tests/test_core.py
Integration and unit tests for core modules.
"""
import pytest
import asyncio
from core.config import Config
from core.agent_base import AgentBase, TaskResult
from core.message_bus import MessageBus
from core.state_manager import StateManager
from core.orchestrator import Orchestrator

class DummyAgent(AgentBase):
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        if task == "fail":
            raise Exception("Intentional failure")
        return TaskResult(success=True, data={"task": task})

@pytest.fixture
def clean_singletons():
    Config._instance = None
    MessageBus._instance = None
    StateManager._instance = None

@pytest.mark.asyncio
async def test_config_singleton(clean_singletons):
    c1 = Config()
    c2 = Config()
    assert c1 is c2
    assert c1.get("system.name") == "The Moon AI"
    
    c1.set("system.test", True)
    assert c2.get("system.test") is True

@pytest.mark.asyncio
async def test_agent_execution():
    agent = DummyAgent()
    res = await agent.execute("test task")
    assert res.success is True
    assert res.data["task"] == "test task"
    assert agent.stats["execution_count"] == 1
    assert agent.stats["success_count"] == 1
    
    res_fail = await agent.execute("fail")
    assert res_fail.success is False
    assert agent.stats["error_count"] == 1

@pytest.mark.asyncio
async def test_message_bus(clean_singletons):
    bus = MessageBus()
    received = []
    
    def cb(msg):
        received.append(msg.payload)
        
    bus.subscribe("test_topic", cb)
    await bus.publish("test", "test_topic", {"key": "value"})
    
    assert len(received) == 1
    assert received[0]["key"] == "value"

@pytest.mark.asyncio
async def test_state_manager(clean_singletons):
    sm = StateManager()
    sm.set_context("test_key", "test_value", ttl=10)
    assert sm.get_context("test_key") == "test_value"
    
    sm.set_memory("perm", "value")
    assert sm.get_memory("perm") == "value"
