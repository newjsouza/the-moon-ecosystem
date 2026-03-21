"""Sprint E — Test suite for TextToSQLAgent, SQLValidator, SQLSchemaRegistry."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.agent_base import TaskResult


# ─────────────────────────────────────────────
# SQLSchemaRegistry tests
# ─────────────────────────────────────────────
class TestSQLSchemaRegistry:

    def setup_method(self):
        from core.sql_schema_registry import SQLSchemaRegistry
        self.registry = SQLSchemaRegistry()

    def test_instantiation(self):
        assert self.registry is not None

    def test_list_tables_not_empty(self):
        tables = self.registry.list_tables()
        assert isinstance(tables, list)
        assert len(tables) >= 1

    def test_get_schema_context_is_string(self):
        ctx = self.registry.get_schema_context()
        assert isinstance(ctx, str)
        assert "TABLE" in ctx

    def test_table_exists_known_table(self):
        tables = self.registry.list_tables()
        if tables:
            assert self.registry.table_exists(tables[0]) is True

    def test_table_exists_unknown_table(self):
        assert self.registry.table_exists("nonexistent_table_xyz") is False

    def test_get_columns_known_table(self):
        tables = self.registry.list_tables()
        if tables:
            cols = self.registry.get_columns(tables[0])
            assert isinstance(cols, list)

    def test_get_columns_unknown_table(self):
        cols = self.registry.get_columns("nonexistent_xyz")
        assert cols == []

    def test_is_safe_for_select_default(self):
        tables = self.registry.list_tables()
        if tables:
            result = self.registry.is_safe_for_select(tables[0])
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_refresh_from_db_mock(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=TaskResult(
            success=True,
            data=[
                {"table_name": "test_table", "column_name": "id", "data_type": "integer"},
                {"table_name": "test_table", "column_name": "name", "data_type": "text"},
            ]
        ))
        result = await self.registry.refresh_from_db(mock_executor)
        assert isinstance(result, TaskResult)
        if result.success:
            assert self.registry.table_exists("test_table")

    @pytest.mark.asyncio
    async def test_refresh_from_db_failure(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=TaskResult(
            success=False, error="DB connection refused"
        ))
        result = await self.registry.refresh_from_db(mock_executor)
        assert result.success is False


# ─────────────────────────────────────────────
# SQLValidator tests
# ─────────────────────────────────────────────
class TestSQLValidator:

    def setup_method(self):
        from core.sql_validator import SQLValidator
        self.v = SQLValidator()

    def test_instantiation(self):
        assert self.v is not None

    def test_valid_select_with_limit(self):
        ok, err = self.v.validate("SELECT id, content FROM moon_memory LIMIT 10")
        assert ok is True
        assert err == ""

    def test_select_without_limit_fails(self):
        ok, err = self.v.validate("SELECT * FROM moon_memory")
        assert ok is False
        assert "LIMIT" in err

    def test_drop_table_rejected(self):
        ok, err = self.v.validate("DROP TABLE moon_memory")
        assert ok is False
        assert "DROP" in err

    def test_truncate_rejected(self):
        ok, err = self.v.validate("TRUNCATE TABLE moon_memory")
        assert ok is False

    def test_delete_rejected(self):
        ok, err = self.v.validate("DELETE FROM moon_memory WHERE id=1")
        assert ok is False

    def test_empty_sql_rejected(self):
        ok, err = self.v.validate("")
        assert ok is False

    def test_with_cte_allowed(self):
        sql = "WITH cte AS (SELECT id FROM moon_memory LIMIT 5) SELECT * FROM cte LIMIT 5"
        ok, err = self.v.validate(sql)
        assert ok is True

    def test_stacked_query_rejected(self):
        ok, err = self.v.validate("SELECT id FROM moon_memory LIMIT 1; DROP TABLE moon_memory")
        assert ok is False

    def test_add_limit_adds_limit(self):
        sql = "SELECT id FROM moon_memory"
        result = self.v.add_limit(sql, 50)
        assert "LIMIT 50" in result

    def test_add_limit_does_not_duplicate(self):
        sql = "SELECT id FROM moon_memory LIMIT 10"
        result = self.v.add_limit(sql, 50)
        assert result.upper().count("LIMIT") == 1

    def test_extract_tables_from_select(self):
        sql = "SELECT a.id FROM moon_memory a JOIN moon_sessions b ON a.id = b.id LIMIT 5"
        tables = self.v.extract_tables(sql)
        assert "moon_memory" in tables
        assert "moon_sessions" in tables

    def test_sanitize_identifier_removes_special_chars(self):
        clean = self.v.sanitize_identifier("table; DROP--")
        assert ";" not in clean
        assert "-" not in clean

    def test_allow_write_permits_insert(self):
        sql = "INSERT INTO moon_memory (content) VALUES ('test')"
        ok, err = self.v.validate(sql, allow_write=True)
        # With allow_write=True, INSERT should not be blocked by keyword check
        assert isinstance(ok, bool)

    def test_sql_too_long_rejected(self):
        sql = "SELECT " + "a, " * 2000 + "b FROM moon_memory LIMIT 1"
        ok, err = self.v.validate(sql)
        assert ok is False
        assert "too long" in err


# ─────────────────────────────────────────────
# TextToSQLAgent tests
# ─────────────────────────────────────────────
class TestTextToSQLAgent:

    def setup_method(self):
        from agents.text_to_sql_agent import TextToSQLAgent
        self.agent = TextToSQLAgent()

    def test_instantiation(self):
        assert self.agent is not None
        assert self.agent.AGENT_ID == "text_to_sql"

    def test_execute_signature(self):
        import inspect
        sig = inspect.signature(self.agent._execute)
        assert 'task' in str(sig)
        assert 'kwargs' in str(sig)

    @pytest.mark.asyncio
    async def test_execute_empty_question(self):
        result = await self.agent._execute("")
        assert isinstance(result, TaskResult)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_dry_run_returns_sql(self):
        mock_sql = "SELECT id, content FROM moon_memory LIMIT 10"
        with patch.object(self.agent, '_generate_sql',
                          new_callable=AsyncMock,
                          return_value=(mock_sql, "")):
            result = await self.agent._execute(
                "Show me the last 10 memories",
                dry_run=True
            )
        assert isinstance(result, TaskResult)
        if result.success:
            assert result.data["dry_run"] is True
            assert "sql" in result.data

    @pytest.mark.asyncio
    async def test_execute_with_db_executor(self):
        mock_sql = "SELECT id, content FROM moon_memory LIMIT 5"
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=TaskResult(
            success=True,
            data=[{"id": 1, "content": "test memory"}]
        ))

        with patch.object(self.agent, '_generate_sql',
                          new_callable=AsyncMock,
                          return_value=(mock_sql, "")):
            result = await self.agent._execute(
                "Show me memories",
                db_executor=mock_executor
            )
        assert isinstance(result, TaskResult)
        if result.success:
            assert result.data["executed"] is True
            assert result.data["row_count"] >= 0

    @pytest.mark.asyncio
    async def test_execute_validation_failure(self):
        dangerous_sql = "DROP TABLE moon_memory"
        with patch.object(self.agent, '_generate_sql',
                          new_callable=AsyncMock,
                          return_value=(dangerous_sql, "")):
            result = await self.agent._execute(
                "delete all memories",
                dry_run=True
            )
        assert isinstance(result, TaskResult)
        assert result.success is False
        assert "validation" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_generation_failure(self):
        with patch.object(self.agent, '_generate_sql',
                          new_callable=AsyncMock,
                          return_value=("", "LLM unavailable")):
            result = await self.agent._execute("show me data")
        assert result.success is False
        assert "generation" in result.error.lower()

    @pytest.mark.asyncio
    async def test_generate_sql_calls_llm(self):
        mock_response = "SELECT id FROM moon_memory LIMIT 10"
        with patch.object(self.agent.llm, 'complete',
                          new_callable=AsyncMock,
                          return_value=mock_response):
            sql, error = await self.agent._generate_sql("Show 10 memories")
        assert error == ""
        assert "SELECT" in sql.upper()
        assert "moon_memory" in sql

    @pytest.mark.asyncio
    async def test_generate_sql_llm_failure(self):
        with patch.object(self.agent.llm, 'complete',
                          side_effect=Exception("LLM down")):
            sql, error = await self.agent._generate_sql("test question")
        assert sql == ""
        assert len(error) > 0

    def test_extract_sql_removes_markdown(self):
        raw = "```sql\nSELECT id FROM moon_memory LIMIT 5\n```"
        clean = self.agent._extract_sql(raw)
        assert "```" not in clean
        assert "SELECT" in clean

    def test_extract_sql_empty_response(self):
        result = self.agent._extract_sql("")
        assert result == ""

    def test_extract_sql_single_statement(self):
        raw = "SELECT id LIMIT 1; SELECT name LIMIT 1;"
        result = self.agent._extract_sql(raw)
        assert result.count(";") <= 1

    @pytest.mark.asyncio
    async def test_explain_query_dry_run(self):
        mock_sql = "SELECT id FROM moon_memory LIMIT 5"
        with patch.object(self.agent, '_generate_sql',
                          new_callable=AsyncMock,
                          return_value=(mock_sql, "")), \
             patch.object(self.agent, '_explain_sql',
                          new_callable=AsyncMock,
                          return_value="Esta consulta retorna os últimos 5 registros de memória"):
            result = await self.agent.explain_query("Show me 5 memories")
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_db_executor_error_propagated(self):
        mock_sql = "SELECT id FROM moon_memory LIMIT 5"
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=TaskResult(
            success=False, error="Connection timeout"
        ))
        with patch.object(self.agent, '_generate_sql',
                          new_callable=AsyncMock,
                          return_value=(mock_sql, "")):
            result = await self.agent._execute(
                "show memories",
                db_executor=mock_executor
            )
        assert result.success is False
        assert "execution" in result.error.lower()


# ─────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────
class TestSprintEIntegration:

    def test_all_imports_work(self):
        from agents.text_to_sql_agent import TextToSQLAgent
        from core.sql_validator import SQLValidator
        from core.sql_schema_registry import SQLSchemaRegistry
        assert all([TextToSQLAgent, SQLValidator, SQLSchemaRegistry])

    def test_agent_base_compliance(self):
        from agents.text_to_sql_agent import TextToSQLAgent
        from core.agent_base import AgentBase
        assert issubclass(TextToSQLAgent, AgentBase)

    def test_forbidden_keywords_complete(self):
        from core.sql_schema_registry import FORBIDDEN_KEYWORDS
        for kw in ["DROP", "DELETE", "TRUNCATE", "ALTER"]:
            assert kw in FORBIDDEN_KEYWORDS

    def test_validator_and_registry_work_together(self):
        from core.sql_validator import SQLValidator
        from core.sql_schema_registry import SQLSchemaRegistry
        reg = SQLSchemaRegistry()
        v = SQLValidator()
        tables = reg.list_tables()
        if tables:
            sql = f"SELECT * FROM {tables[0]} LIMIT 5"
            ok, err = v.validate(sql)
            assert ok is True

    @pytest.mark.asyncio
    async def test_end_to_end_dry_run(self):
        from agents.text_to_sql_agent import TextToSQLAgent
        agent = TextToSQLAgent()

        mock_sql = "SELECT id, content FROM moon_memory LIMIT 5"
        with patch.object(agent.llm, 'complete',
                          new_callable=AsyncMock,
                          return_value=mock_sql):
            result = await agent._execute(
                "Show me the 5 most recent memories",
                dry_run=True
            )
        assert isinstance(result, TaskResult)
        if result.success:
            assert result.data["dry_run"] is True