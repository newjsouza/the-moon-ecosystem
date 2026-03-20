"""
tests/test_data_pipeline_agent.py
Testes para DataPipelineAgent — Abelha Processadora da Colmeia.
"""
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
import duckdb
import pandas as pd
from agents.data_pipeline_agent import DataPipelineAgent, _DATA_DIR


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
    llm.complete = AsyncMock(return_value="Insights gerados em teste.")
    return llm


@pytest.fixture
def agent(mock_bus, mock_llm, tmp_path):
    """Cria um DataPipelineAgent com banco de dados em tmp_path."""
    a = DataPipelineAgent(bus=mock_bus, llm=mock_llm)
    a._db_path = tmp_path / "test_pipeline.db"
    a._conn = duckdb.connect(str(a._db_path))
    a._conn.execute("""
        CREATE TABLE IF NOT EXISTS research_results (
            id INTEGER, ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source VARCHAR, query VARCHAR, title VARCHAR, url VARCHAR,
            description VARCHAR, stars INTEGER, downloads INTEGER,
            language VARCHAR, tags VARCHAR, published VARCHAR
        )
    """)
    a._conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id VARCHAR, started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP, input_type VARCHAR, rows_in INTEGER,
            rows_out INTEGER, status VARCHAR
        )
    """)
    return a


_SAMPLE_RESULTS = [
    {"source": "github", "title": "org/repo-a", "url": "https://github.com/org/repo-a",
     "description": "AI agent framework", "stars": 5000, "language": "Python",
     "topics": ["ai", "agents"], "updated_at": "2026-01-01"},
    {"source": "huggingface", "title": "org/model-b",
     "url": "https://huggingface.co/org/model-b",
     "description": "text-generation", "downloads": 100000, "tags": ["llm"]},
    {"source": "arxiv", "title": "Paper on Agents",
     "url": "https://arxiv.org/abs/0001",
     "description": "We propose...", "published": "2026-01-15"},
]


# ── Instanciação ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_instantiation(agent):
    """Testa instanciação do agente."""
    assert agent.name == "DataPipelineAgent"
    assert agent._conn is not None


# ── Ingestão ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_json_creates_table(agent, tmp_path):
    """Testa ingestão de JSON cria tabela."""
    data = [{"col_a": 1, "col_b": "hello"}, {"col_a": 2, "col_b": "world"}]
    count = await agent.ingest_json(data, "test_table")
    assert count == 2
    rows = agent._conn.execute("SELECT * FROM test_table").fetchall()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_ingest_json_empty_returns_zero(agent):
    """Testa que JSON vazio retorna zero."""
    count = await agent.ingest_json([], "empty_table")
    assert count == 0


# ── Consulta SQL ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_query_select(agent):
    """Testa query SELECT."""
    agent._conn.execute(
        "INSERT INTO research_results VALUES (1, NOW(), 'github', 'test', "
        "'repo/x', 'http://x.com', 'desc', 100, NULL, 'Python', '[]', '2026-01-01')"
    )
    rows = await agent.run_query("SELECT * FROM research_results")
    assert len(rows) == 1
    assert rows[0]["title"] == "repo/x"


@pytest.mark.asyncio
async def test_run_query_aggregation(agent):
    """Testa query de agregação."""
    agent._conn.execute(
        "INSERT INTO research_results VALUES "
        "(1, NOW(), 'github', 'q', 'r1', 'u1', 'd', 10, NULL, 'Py', '[]', ''),"
        "(2, NOW(), 'arxiv', 'q', 'r2', 'u2', 'd', NULL, NULL, '', '[]', '')"
    )
    rows = await agent.run_query(
        "SELECT source, COUNT(*) as n FROM research_results GROUP BY source ORDER BY n DESC"
    )
    assert len(rows) == 2


# ── Resumo ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summarize_empty_db(agent):
    """Testa resumo com banco vazio."""
    summary = await agent.summarize_research()
    assert summary["total_results"] == 0
    assert summary["by_source"] == []
    assert summary["top_github"] == []
    assert summary["top_huggingface"] == []


@pytest.mark.asyncio
async def test_summarize_with_data(agent):
    """Testa resumo com dados."""
    agent._conn.execute(
        "INSERT INTO research_results VALUES "
        "(1, NOW(), 'github', 'llm', 'repo/a', 'u1', 'd', 500, NULL, 'Py', '[]', ''),"
        "(2, NOW(), 'github', 'llm', 'repo/b', 'u2', 'd', 200, NULL, 'Py', '[]', ''),"
        "(3, NOW(), 'huggingface', 'llm', 'org/m', 'u3', 'd', NULL, 99999, '', '[]', '')"
    )
    summary = await agent.summarize_research("llm")
    assert summary["total_results"] == 3
    assert len(summary["by_source"]) == 2
    assert summary["top_github"][0]["stars"] == 500


# ── Exportação ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_csv_creates_file(agent, tmp_path):
    """Testa exportação para CSV."""
    agent._db_path = tmp_path / "test.db"
    agent._conn.execute(
        "INSERT INTO research_results VALUES "
        "(1, NOW(), 'github', 'q', 'r1', 'u1', 'd', 10, NULL, 'Py', '[]', '')"
    )
    with patch("agents.data_pipeline_agent._DATA_DIR", tmp_path):
        path = await agent.export_csv("research_results", "test_export.csv")
    assert Path(path).exists()


@pytest.mark.asyncio
async def test_export_json_creates_file(agent, tmp_path):
    """Testa exportação para JSON."""
    agent._conn.execute(
        "INSERT INTO research_results VALUES "
        "(1, NOW(), 'github', 'q', 'r1', 'u1', 'd', 10, NULL, 'Py', '[]', '')"
    )
    with patch("agents.data_pipeline_agent._DATA_DIR", tmp_path):
        path = await agent.export_json("research_results", "test_export.json")
    assert Path(path).exists()
    data = json.loads(Path(path).read_text())
    assert len(data) == 1


# ── Insights LLM ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_insights_calls_llm(agent, mock_llm):
    """Testa geração de insights chama LLM."""
    summary = {
        "total_results": 5,
        "by_source": [{"source": "github", "count": 3}],
        "top_github": [{"title": "r/a", "stars": 100, "url": "u"}],
        "top_huggingface": [],
    }
    result = await agent.generate_insights(summary, "AI agents")
    assert result == "Insights gerados em teste."
    mock_llm.complete.assert_called_once()


@pytest.mark.asyncio
async def test_generate_insights_llm_fallback(agent, mock_llm):
    """Testa fallback quando LLM falha."""
    mock_llm.complete = AsyncMock(side_effect=Exception("LLM down"))
    summary = {
        "total_results": 2,
        "by_source": [{"source": "github", "count": 2}],
        "top_github": [], "top_huggingface": [],
    }
    result = await agent.generate_insights(summary, "test")
    assert "2" in result


# ── MessageBus ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_on_pipeline_request_publishes_result(agent, mock_bus):
    """Testa que pipeline publica resultado."""
    agent._execute = AsyncMock(return_value=MagicMock(
        success=True, data={"rows_ingested": 3}, error=None
    ))
    await agent._on_pipeline_request(
        "DeepWebResearchAgent",
        {"type": "research", "query": "AI", "data": {"results": [], "query": "AI"}}
    )
    mock_bus.publish.assert_called_once()
    # publish(sender, topic, payload, target=None)
    call_args = mock_bus.publish.call_args
    assert call_args[0][1] == "pipeline.result"  # topic
    assert call_args[1].get("target") == "DeepWebResearchAgent"  # target é keyword arg


# ── _execute tasks ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_unknown_task(agent):
    """Testa task desconhecida."""
    result = await agent._execute("unknown")
    assert result.success is False
    assert "desconhecida" in result.error


@pytest.mark.asyncio
async def test_execute_query_missing_sql(agent):
    """Testa query sem SQL."""
    result = await agent._execute("query")
    assert result.success is False
    assert "sql" in result.error


@pytest.mark.asyncio
async def test_execute_query_valid_sql(agent):
    """Testa query SQL válida."""
    result = await agent._execute(
        "query", sql="SELECT COUNT(*) as total FROM research_results"
    )
    assert result.success is True
    assert result.data["rows"][0]["total"] == 0


@pytest.mark.asyncio
async def test_execute_summarize(agent):
    """Testa summarize."""
    result = await agent._execute("summarize")
    assert result.success is True
    assert "total_results" in result.data


@pytest.mark.asyncio
async def test_execute_status(agent):
    """Testa status."""
    result = await agent._execute("status")
    assert result.success is True
    assert "tables" in result.data
    assert "research_results" in result.data["tables"]


@pytest.mark.asyncio
async def test_execute_process_json(agent):
    """Testa process json."""
    result = await agent._execute(
        "process",
        type="json",
        data=[{"key": "val1"}, {"key": "val2"}],
        table_name="custom_table",
    )
    assert result.success is True
    assert result.data["rows_ingested"] == 2


@pytest.mark.asyncio
async def test_execute_process_unknown_type(agent):
    """Testa tipo de pipeline desconhecido."""
    result = await agent._execute("process", type="invalid_type", data={})
    assert result.success is False
    assert "desconhecido" in result.error
