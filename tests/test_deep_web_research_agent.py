"""
tests/test_deep_web_research_agent.py
Testes para DeepWebResearchAgent — Abelha Coletora da Colmeia.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agents.deep_web_research_agent import DeepWebResearchAgent, _DEFAULT_SOURCES


@pytest.fixture
def mock_bus():
    """Mock do MessageBus."""
    bus = MagicMock()
    bus.subscribe = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_llm():
    """Mock do LLMRouter."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Síntese gerada pelo LLM em teste.")
    return llm


@pytest.fixture
def agent(mock_bus, mock_llm):
    """Cria um DeepWebResearchAgent com mocks."""
    with patch("agents.deep_web_research_agent.HfApi"):
        with patch("agents.deep_web_research_agent.arxiv.Client"):
            a = DeepWebResearchAgent(bus=mock_bus, llm=mock_llm)
            return a


# ── Instanciação ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_instantiation(agent):
    """Testa instanciação do agente."""
    assert agent.name == "DeepWebResearchAgent"
    assert isinstance(agent._github_headers, dict)
    assert "Accept" in agent._github_headers


@pytest.mark.asyncio
async def test_start_subscribes(agent, mock_bus):
    """Testa que start() subscreve ao tópico research.request."""
    with patch("asyncio.create_task"):
        await agent.start()
    mock_bus.subscribe.assert_called_once_with(
        "research.request", agent._on_research_request_wrapper
    )


# ── GitHub ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_github_success(agent):
    """Testa busca no GitHub com sucesso."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "items": [
            {
                "full_name": "org/cool-repo",
                "html_url": "https://github.com/org/cool-repo",
                "description": "A cool repo",
                "stargazers_count": 1234,
                "language": "Python",
                "topics": ["ai", "llm"],
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]
    }
    with patch("requests.get", return_value=mock_response):
        results = await agent._search_github("llm agents")
    assert len(results) == 1
    assert results[0]["source"] == "github"
    assert results[0]["title"] == "org/cool-repo"
    assert results[0]["stars"] == 1234


@pytest.mark.asyncio
async def test_search_github_network_error_returns_empty(agent):
    """Testa que erro de rede retorna lista vazia."""
    with patch("requests.get", side_effect=Exception("timeout")):
        results = await agent._search_github("any query")
    assert results == []


@pytest.mark.asyncio
async def test_search_github_respects_max_results(agent):
    """Testa que max_results é respeitado."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"items": []}
    with patch("requests.get", return_value=mock_response) as mock_get:
        await agent._search_github("query", max_results=5)
    call_params = mock_get.call_args[1]["params"]
    assert call_params["per_page"] == 5


# ── HuggingFace ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_huggingface_success(agent):
    """Testa busca no HuggingFace com sucesso."""
    mock_model = MagicMock()
    mock_model.modelId = "org/model-name"
    mock_model.pipeline_tag = "text-generation"
    mock_model.downloads = 50000
    mock_model.tags = ["pytorch", "llm"]
    agent._hf_api.list_models = MagicMock(return_value=iter([mock_model]))
    results = await agent._search_huggingface("llm generation")
    assert len(results) == 1
    assert results[0]["source"] == "huggingface"
    assert results[0]["title"] == "org/model-name"
    assert results[0]["downloads"] == 50000


@pytest.mark.asyncio
async def test_search_huggingface_error_returns_empty(agent):
    """Testa que erro retorna lista vazia."""
    agent._hf_api.list_models = MagicMock(side_effect=Exception("API error"))
    results = await agent._search_huggingface("query")
    assert results == []


# ── Arxiv ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_arxiv_success(agent):
    """Testa busca no Arxiv com sucesso."""
    mock_paper = MagicMock()
    mock_paper.title = "Advances in LLM Agents"
    mock_paper.entry_id = "https://arxiv.org/abs/2601.00001"
    mock_paper.summary = "This paper explores..." * 10
    mock_paper.authors = [MagicMock(name="Author One"), MagicMock(name="Author Two")]
    mock_paper.published = MagicMock(isoformat=lambda: "2026-01-01T00:00:00")
    mock_paper.categories = ["cs.AI"]
    agent._arxiv_client.results = MagicMock(return_value=iter([mock_paper]))
    results = await agent._search_arxiv("LLM agents")
    assert len(results) == 1
    assert results[0]["source"] == "arxiv"
    assert results[0]["title"] == "Advances in LLM Agents"


@pytest.mark.asyncio
async def test_search_arxiv_error_returns_empty(agent):
    """Testa que erro retorna lista vazia."""
    agent._arxiv_client.results = MagicMock(side_effect=Exception("network"))
    results = await agent._search_arxiv("query")
    assert results == []


# ── Síntese ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesize_with_results(agent, mock_llm):
    """Testa síntese com resultados."""
    results = [
        {"source": "github", "title": "repo/a", "description": "desc a"},
        {"source": "arxiv", "title": "Paper B", "description": "desc b"},
    ]
    synthesis = await agent._synthesize("test query", results)
    assert synthesis == "Síntese gerada pelo LLM em teste."
    mock_llm.complete.assert_called_once()


@pytest.mark.asyncio
async def test_synthesize_empty_results(agent):
    """Testa síntese sem resultados."""
    synthesis = await agent._synthesize("query", [])
    assert "Nenhum resultado" in synthesis


@pytest.mark.asyncio
async def test_synthesize_llm_fallback(agent, mock_llm):
    """Testa fallback quando LLM falha."""
    mock_llm.complete = AsyncMock(side_effect=Exception("LLM down"))
    results = [{"source": "github", "title": "repo/x", "description": ""}]
    synthesis = await agent._synthesize("query", results)
    assert "repo/x" in synthesis


# ── Research (orquestrador) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_research_calls_all_sources(agent):
    """Testa que research chama todas as fontes."""
    agent._search_github = AsyncMock(return_value=[{"source": "github", "title": "r1", "description": ""}])
    agent._search_huggingface = AsyncMock(return_value=[{"source": "huggingface", "title": "m1", "description": ""}])
    agent._search_arxiv = AsyncMock(return_value=[{"source": "arxiv", "title": "p1", "description": ""}])
    agent._synthesize = AsyncMock(return_value="síntese")
    result = await agent.research("open source LLM", save_to_memory=False)
    assert result["total_results"] == 3
    assert result["query"] == "open source LLM"
    assert result["synthesis"] == "síntese"


@pytest.mark.asyncio
async def test_research_saves_to_memory(agent, mock_bus):
    """Testa que research salva no memory quando save_to_memory=True."""
    agent._search_github = AsyncMock(return_value=[])
    agent._search_huggingface = AsyncMock(return_value=[])
    agent._search_arxiv = AsyncMock(return_value=[])
    agent._synthesize = AsyncMock(return_value="síntese")
    await agent.research("query", save_to_memory=True)
    mock_bus.publish.assert_called_once()
    call = mock_bus.publish.call_args[0]
    assert call[1] == "memory.store"
    assert "query" in call[2]["content"]


@pytest.mark.asyncio
async def test_research_skips_memory_when_false(agent, mock_bus):
    """Testa que research não salva quando save_to_memory=False."""
    agent._search_github = AsyncMock(return_value=[])
    agent._search_huggingface = AsyncMock(return_value=[])
    agent._search_arxiv = AsyncMock(return_value=[])
    agent._synthesize = AsyncMock(return_value="síntese")
    await agent.research("query", save_to_memory=False)
    mock_bus.publish.assert_not_called()


# ── MessageBus Handler ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_research_request_empty_query_skips(agent, mock_bus):
    """Testa que query vazia não publica resultado."""
    await agent._on_research_request("SchedulerAgent", {"query": ""})
    mock_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_on_research_request_publishes_result(agent, mock_bus):
    """Testa que pesquisa publica resultado."""
    agent.research = AsyncMock(return_value={
        "query": "AI tools", "total_results": 5,
        "synthesis": "test", "results": [], "sources_used": ["github"]
    })
    await agent._on_research_request("SchedulerAgent", {"query": "AI tools"})
    mock_bus.publish.assert_called_once()
    # publish(sender, topic, payload, target=None)
    call_args = mock_bus.publish.call_args
    assert call_args[0][1] == "research.result"  # topic
    assert call_args[1].get("target") == "SchedulerAgent"  # target é keyword arg


# ── _execute ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_unknown_task(agent):
    """Testa task desconhecida."""
    result = await agent._execute("unknown")
    assert result.success is False
    assert "desconhecida" in result.error


@pytest.mark.asyncio
async def test_execute_research_missing_query(agent):
    """Testa research sem query."""
    result = await agent._execute("research")
    assert result.success is False
    assert "query" in result.error


@pytest.mark.asyncio
async def test_execute_search_github(agent):
    """Testa search_github via _execute."""
    agent._search_github = AsyncMock(return_value=[{"source": "github"}])
    result = await agent._execute("search_github", query="python agents")
    assert result.success is True
    assert result.data["count"] == 1


@pytest.mark.asyncio
async def test_execute_search_arxiv(agent):
    """Testa search_arxiv via _execute."""
    agent._search_arxiv = AsyncMock(return_value=[])
    result = await agent._execute("search_arxiv", query="transformers")
    assert result.success is True
    assert result.data["count"] == 0
