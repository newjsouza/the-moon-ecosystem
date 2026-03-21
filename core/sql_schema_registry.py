"""
SQLSchemaRegistry — stores Supabase schema for Text-to-SQL context.
Auto-refreshes from live DB via DBExecutor.
Provides schema context to LLM prompt for accurate SQL generation.
"""
import logging
import asyncio
from core.agent_base import TaskResult

logger = logging.getLogger(__name__)

# ── Static schema snapshot (from Supabase MCP introspection) ──────────────
# INSTRUCTION: Replace this with real output from STEP 2 MCP query.
# Format: { "table_name": { "columns": [...], "description": "..." } }
STATIC_SCHEMA = {
    "moon_memory": {
        "columns": ["id", "content", "embedding", "metadata", "topic",
                    "created_at", "updated_at"],
        "description": "Long-term semantic memory with pgvector embeddings",
        "safe_for_select": True,
    },
    "moon_sessions": {
        "columns": ["id", "session_id", "user_id", "data", "created_at", "updated_at"],
        "description": "Session storage for user interactions",
        "safe_for_select": True,
    },
    "moon_users": {
        "columns": ["id", "username", "email", "created_at", "updated_at", "preferences"],
        "description": "User account information",
        "safe_for_select": True,
    },
    "moon_tasks": {
        "columns": ["id", "task_name", "description", "created_at", "completed_at", "status", "result"],
        "description": "Task execution logs and results",
        "safe_for_select": True,
    },
    "moon_agents": {
        "columns": ["id", "agent_name", "description", "created_at", "updated_at", "stats"],
        "description": "Registered agent metadata and statistics",
        "safe_for_select": True,
    },
    # Add other tables discovered via MCP in STEP 2
    # "table_name": { "columns": [...], "description": "..." }
}

FORBIDDEN_KEYWORDS = {
    "DROP", "TRUNCATE", "ALTER", "DELETE", "UPDATE",
    "INSERT", "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE"
}

ALLOWED_READONLY = {"SELECT", "WITH", "EXPLAIN"}


class SQLSchemaRegistry:
    """Registry of available tables and columns for Text-to-SQL."""

    def __init__(self):
        self._schema = dict(STATIC_SCHEMA)
        self._refreshed = False
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_schema_context(self) -> str:
        """Build LLM-readable schema context string."""
        lines = ["Available tables in The Moon database (Supabase/PostgreSQL):\n"]
        for table, meta in self._schema.items():
            cols = ", ".join(meta.get("columns", []))
            desc = meta.get("description", "")
            lines.append(f"  TABLE {table}")
            lines.append(f"    Columns: {cols}")
            if desc:
                lines.append(f"    Description: {desc}")
            lines.append("")
        return "\n".join(lines)

    def table_exists(self, table_name: str) -> bool:
        return table_name.lower() in {k.lower() for k in self._schema}

    def get_columns(self, table_name: str) -> list:
        for k, v in self._schema.items():
            if k.lower() == table_name.lower():
                return v.get("columns", [])
        return []

    def is_safe_for_select(self, table_name: str) -> bool:
        for k, v in self._schema.items():
            if k.lower() == table_name.lower():
                return v.get("safe_for_select", True)
        return False

    def list_tables(self) -> list:
        return list(self._schema.keys())

    async def refresh_from_db(self, db_executor) -> TaskResult:
        """Refresh schema from live Supabase via DBExecutor."""
        start = asyncio.get_event_loop().time()
        try:
            sql = """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position;
            """
            result = await db_executor.execute(sql)
            if not result.success:
                return TaskResult(success=False,
                                  error=f"Schema refresh failed: {result.error}")

            new_schema = {}
            for row in (result.data or []):
                tbl = row.get("table_name", "")
                col = row.get("column_name", "")
                if tbl and col:
                    if tbl not in new_schema:
                        new_schema[tbl] = {"columns": [], "safe_for_select": True}
                    new_schema[tbl]["columns"].append(col)

            self._schema.update(new_schema)
            self._refreshed = True
            self.logger.info(f"Schema refreshed: {len(new_schema)} tables found")

            return TaskResult(
                success=True,
                data={"tables": len(new_schema), "refreshed": True},
                execution_time=asyncio.get_event_loop().time() - start
            )
        except Exception as e:
            return TaskResult(success=False, error=str(e))