"""
tests/test_agents.py
Tests for specific agents.
"""
import pytest
from core.agent_base import AgentPriority
from agents.architect import ArchitectAgent
from agents.vault import VaultAgent
from agents.api_discovery import ApiDiscoveryAgent
from agents.llm import LlmAgent

@pytest.mark.asyncio
async def test_architect_agent():
    agent = ArchitectAgent()
    res = await agent.execute("Design new system")
    assert res.success is True
    assert "Design new system" in res.data["plan"]
    assert agent.priority == AgentPriority.CRITICAL

@pytest.mark.asyncio
async def test_vault_agent():
    agent = VaultAgent()
    res_store = await agent.execute("store_key", action="store", key="test_key", value="test_value")
    assert res_store.success is True
    
    res_get = await agent.execute("get_key", action="retrieve", key="test_key")
    assert res_get.success is True
    assert res_get.data["value"] == "test_value"

@pytest.mark.asyncio
async def test_api_discovery_agent():
    agent = ApiDiscoveryAgent()
    res = await agent.execute("check health")
    assert res.success is True
    assert res.data["status"] == "healthy"

@pytest.mark.asyncio
async def test_llm_agent():
    agent = LlmAgent()
    res = await agent.execute("Hello", provider="openai")
    assert res.success is True
    assert "Simulated openai response" in res.data["response"]
