"""
TextToSQLAgent — translates natural language questions into safe SQL queries.
Uses LLMRouter for translation + SQLValidator for safety + DBExecutor for execution.
Integrates with EvaluatorAgent for output quality assurance (Sprint C).
"""
import asyncio
import logging
import re
from core.observability import observe_agent
from core.agent_base import AgentBase, TaskResult
from core.sql_schema_registry import SQLSchemaRegistry
from core.sql_validator import SQLValidator
from agents.llm import LLMRouter


@observe_agent
class TextToSQLAgent(AgentBase):
    """
    Translate natural language → validated SQL → execute → return results.
    Read-only by default. Write operations require explicit allow_write=True.
    """

    AGENT_ID = "text_to_sql"
    MAX_GENERATION_RETRIES = 3

    def __init__(self):
        super().__init__()
        self.schema_registry = SQLSchemaRegistry()
        self.validator = SQLValidator()
        self.llm = LLMRouter()
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Translate and execute a natural language query.
        kwargs:
            question (str): natural language question (overrides task)
            allow_write (bool): allow INSERT/UPDATE (default False)
            max_rows (int): result limit (default 100)
            db_executor: DBExecutor instance for query execution
            dry_run (bool): generate SQL but do not execute (default False)
        """
        start = asyncio.get_event_loop().time()
        try:
            question = kwargs.get("question", task)
            allow_write = kwargs.get("allow_write", False)
            max_rows = kwargs.get("max_rows", 100)
            db_executor = kwargs.get("db_executor", None)
            dry_run = kwargs.get("dry_run", False)

            if not question or not question.strip():
                return TaskResult(success=False,
                                  error="question cannot be empty")

            # Step 1: Generate SQL from natural language
            sql, generation_error = await self._generate_sql(
                question=question,
                allow_write=allow_write
            )
            if generation_error:
                return TaskResult(
                    success=False,
                    error=f"SQL generation failed: {generation_error}",
                    execution_time=asyncio.get_event_loop().time() - start
                )

            # Step 2: Validate SQL
            sql = self.validator.add_limit(sql, max_rows)
            is_valid, validation_error = self.validator.validate(sql, allow_write)
            if not is_valid:
                return TaskResult(
                    success=False,
                    error=f"SQL validation failed: {validation_error}",
                    data={"generated_sql": sql},
                    execution_time=asyncio.get_event_loop().time() - start
                )

            # Step 3: Dry run — return SQL without executing
            if dry_run or db_executor is None:
                self.logger.info(f"Dry run — SQL generated: {sql[:100]}...")
                return TaskResult(
                    success=True,
                    data={
                        "sql": sql,
                        "question": question,
                        "executed": False,
                        "dry_run": True,
                    },
                    execution_time=asyncio.get_event_loop().time() - start
                )

            # Step 4: Execute via DBExecutor
            exec_result = await db_executor.execute(sql)
            if not exec_result.success:
                return TaskResult(
                    success=False,
                    error=f"SQL execution failed: {exec_result.error}",
                    data={"sql": sql},
                    execution_time=asyncio.get_event_loop().time() - start
                )

            rows = exec_result.data or []
            self.logger.info(
                f"TextToSQL: '{question[:60]}' → {len(rows)} rows"
            )

            return TaskResult(
                success=True,
                data={
                    "question": question,
                    "sql": sql,
                    "rows": rows,
                    "row_count": len(rows),
                    "executed": True,
                },
                execution_time=asyncio.get_event_loop().time() - start
            )

        except Exception as e:
            return TaskResult(
                success=False,
                error=str(e),
                execution_time=asyncio.get_event_loop().time() - start
            )

    async def _generate_sql(self, question: str,
                             allow_write: bool = False,
                             attempt: int = 0) -> tuple[str, str]:
        """
        Use LLM to generate SQL from natural language.
        Returns (sql: str, error: str). Empty error = success.
        """
        if attempt >= self.MAX_GENERATION_RETRIES:
            return "", f"Max generation retries ({self.MAX_GENERATION_RETRIES}) reached"

        schema_context = self.schema_registry.get_schema_context()
        write_note = "" if not allow_write else \
            "\nNote: Write operations (INSERT/UPDATE) are allowed for this query."

        prompt = f"""You are a PostgreSQL expert for The Moon AI ecosystem.
Convert the natural language question into a valid PostgreSQL query.

{schema_context}
Rules:
1. Use ONLY tables and columns listed above — never invent names
2. Always include LIMIT (max 100 rows) for SELECT queries
3. Use lowercase table and column names
4. Return ONLY the SQL query — no explanation, no markdown, no backticks
5. Default to read-only SELECT queries{write_note}

Question: {question}

SQL:"""

        try:
            response = await self.llm.complete(prompt, task_type="sql_generation", actor="text_to_sql_agent")
            sql = self._extract_sql(response)
            if not sql:
                return "", "LLM returned empty SQL"
            return sql, ""
        except Exception as e:
            return "", str(e)

    def _extract_sql(self, llm_response: str) -> str:
        """Extract clean SQL from LLM response (remove markdown, backticks)."""
        if not llm_response:
            return ""

        # Remove markdown code blocks
        sql = re.sub(r'```(?:sql)?\s*', '', llm_response, flags=re.IGNORECASE)
        sql = re.sub(r'```', '', sql)

        # Remove leading/trailing whitespace
        sql = sql.strip()

        # Take only first statement (before second semicolon)
        if sql.count(';') > 1:
            sql = sql[:sql.index(';') + 1]

        return sql.strip()

    async def explain_query(self, question: str, **kwargs) -> TaskResult:
        """
        Generate SQL and return explanation without executing.
        Useful for debugging and user transparency.
        """
        result = await self._execute(
            question,
            question=question,
            dry_run=True
        )
        if result.success:
            sql = result.data.get("sql", "")
            explanation = await self._explain_sql(sql, question)
            result.data["explanation"] = explanation
        return result

    async def _explain_sql(self, sql: str, original_question: str) -> str:
        """Generate human-readable explanation of a SQL query."""
        prompt = f"""Explain this SQL query in plain Portuguese (one sentence):
Question asked: {original_question}
SQL: {sql}
Explanation:"""
        try:
            return await self.llm.complete(prompt, task_type="explanation", actor="text_to_sql_agent")
        except Exception:
            return f"Query to answer: {original_question}"