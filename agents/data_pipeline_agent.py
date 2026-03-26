"""
agents/data_pipeline_agent.py
DataPipelineAgent — Abelha Processadora da Colmeia.
ETL e análise de dados in-process via DuckDB + pandas.
Processa outputs do DeepWebResearchAgent, gera relatórios,
estatísticas e insights. Armazena resultados no MemoryAgent.
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from core.agent_base import AgentBase, TaskResult
from core.message_bus import MessageBus
from agents.llm import LLMRouter

logger = logging.getLogger(__name__)

_DATA_DIR = Path("data/pipeline")
_DATA_DIR.mkdir(parents=True, exist_ok=True)


class DataPipelineAgent(AgentBase):
    """
    Abelha Processadora da Colmeia.
    ETL e análise de dados in-process via DuckDB + pandas.
    Processa outputs do DeepWebResearchAgent, gera relatórios,
    estatísticas e insights. Armazena resultados no MemoryAgent.
    Subscreve pipeline.process | Publica pipeline.result.
    """

    def __init__(self, bus: MessageBus, llm: LLMRouter):
        super().__init__()
        self.name = "DataPipelineAgent"
        self.description = "ETL e análise de dados com DuckDB + pandas"
        self._bus = bus
        self._llm = llm
        self._db_path = _DATA_DIR / "moon_pipeline.db"
        self._conn: duckdb.DuckDBPyConnection | None = None

    async def start(self) -> None:
        """Inicia o agente e conecta ao DuckDB."""
        loop = asyncio.get_event_loop()
        self._conn = await loop.run_in_executor(
            None, lambda: duckdb.connect(str(self._db_path))
        )
        await self._setup_schema()
        self._bus.subscribe("pipeline.process", self._on_pipeline_request_wrapper)
        asyncio.create_task(self._heartbeat_loop())
        logger.info("DataPipelineAgent iniciado — db: %s", self._db_path)

    async def _setup_schema(self) -> None:
        """Configura schema do banco de dados."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._create_tables)

    def _create_tables(self) -> None:
        """Cria tabelas necessárias."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS research_results (
                id          INTEGER PRIMARY KEY,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source      VARCHAR,
                query       VARCHAR,
                title       VARCHAR,
                url         VARCHAR,
                description VARCHAR,
                stars       INTEGER,
                downloads   INTEGER,
                language    VARCHAR,
                tags        VARCHAR,
                published   VARCHAR
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id      VARCHAR PRIMARY KEY,
                started_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                input_type  VARCHAR,
                rows_in     INTEGER,
                rows_out    INTEGER,
                status      VARCHAR
            )
        """)

    # ─────────────────────────────────────────────
    # INGESTÃO
    # ─────────────────────────────────────────────

    async def ingest_research(self, payload: dict) -> int:
        """Ingere resultado do DeepWebResearchAgent na tabela research_results."""
        results = payload.get("results", [])
        query = payload.get("query", "")
        if not results:
            return 0
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._insert_results(results, query)
        )

    def _insert_results(self, results: list[dict], query: str) -> int:
        """Insere resultados no banco."""
        rows = []
        for r in results:
            rows.append({
                "source":      r.get("source", ""),
                "query":       query,
                "title":       r.get("title", "")[:500],
                "url":         r.get("url", "")[:500],
                "description": r.get("description", "")[:1000],
                "stars":       r.get("stars"),
                "downloads":   r.get("downloads"),
                "language":    r.get("language", ""),
                "tags":        json.dumps(r.get("tags", r.get("topics", []))),
                "published":   r.get("published", r.get("updated_at", "")),
            })
        df = pd.DataFrame(rows)
        self._conn.execute(
            "INSERT INTO research_results SELECT nextval('seq_research') ,"
            " CURRENT_TIMESTAMP, * FROM df"
        )
        return len(rows)

    async def ingest_json(self, data: list[dict], table_name: str) -> int:
        """Ingere lista de dicts em tabela DuckDB dinâmica."""
        if not data:
            return 0
        loop = asyncio.get_event_loop()
        df = pd.DataFrame(data)
        count = await loop.run_in_executor(
            None,
            lambda: self._conn.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df"
            ) and len(df)
        )
        return len(df)

    # ─────────────────────────────────────────────
    # ANÁLISE / SQL
    # ─────────────────────────────────────────────

    async def run_query(self, sql: str) -> list[dict]:
        """Executa query SQL e retorna resultados como lista de dicts."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._conn.execute(sql).df().to_dict(orient="records")
        )
        return result

    async def summarize_research(self, query_filter: str | None = None) -> dict:
        """Gera estatísticas sobre os resultados de pesquisa armazenados."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._compute_summary(query_filter)
        )

    def _compute_summary(self, query_filter: str | None) -> dict:
        """Computa estatísticas resumidas."""
        where = f"WHERE query = '{query_filter}'" if query_filter else ""
        total = self._conn.execute(
            f"SELECT COUNT(*) as n FROM research_results {where}"
        ).fetchone()[0]
        by_source = self._conn.execute(
            f"SELECT source, COUNT(*) as count FROM research_results {where} "
            "GROUP BY source ORDER BY count DESC"
        ).df().to_dict(orient="records")
        
        # Top GitHub
        github_where = f"WHERE source = 'github' AND query = '{query_filter}'" if query_filter else "WHERE source = 'github'"
        top_github = self._conn.execute(
            f"SELECT title, stars, url FROM research_results "
            f"{github_where} "
            "ORDER BY stars DESC NULLS LAST LIMIT 5"
        ).df().to_dict(orient="records")
        
        # Top HuggingFace
        hf_where = f"WHERE source = 'huggingface' AND query = '{query_filter}'" if query_filter else "WHERE source = 'huggingface'"
        top_hf = self._conn.execute(
            f"SELECT title, downloads, url FROM research_results "
            f"{hf_where} "
            "ORDER BY downloads DESC NULLS LAST LIMIT 5"
        ).df().to_dict(orient="records")
        
        return {
            "total_results": total,
            "by_source": by_source,
            "top_github": top_github,
            "top_huggingface": top_hf,
        }

    # ─────────────────────────────────────────────
    # EXPORTAÇÃO
    # ─────────────────────────────────────────────

    async def export_csv(
        self, table_name: str = "research_results", filename: str | None = None
    ) -> str:
        """Exporta tabela para CSV."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = filename or f"{table_name}_{ts}.csv"
        out_path = _DATA_DIR / fname
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._conn.execute(
                f"COPY {table_name} TO '{out_path}' (HEADER, DELIMITER ',')"
            )
        )
        logger.info("CSV exportado: %s", out_path)
        return str(out_path)

    async def export_json(
        self, table_name: str = "research_results", filename: str | None = None
    ) -> str:
        """Exporta tabela para JSON."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = filename or f"{table_name}_{ts}.json"
        out_path = _DATA_DIR / fname
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(
            None,
            lambda: self._conn.execute(
                f"SELECT * FROM {table_name}"
            ).df().to_dict(orient="records")
        )
        # Converter Timestamp para string
        for row in rows:
            for key, val in row.items():
                if hasattr(val, 'isoformat'):
                    row[key] = val.isoformat()
        out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
        logger.info("JSON exportado: %s", out_path)
        return str(out_path)

    # ─────────────────────────────────────────────
    # INSIGHTS VIA LLM
    # ─────────────────────────────────────────────

    async def generate_insights(self, summary: dict, query: str) -> str:
        """Gera insights via LLM a partir do resumo dos dados."""
        lines = [f"Total de resultados: {summary['total_results']}"]
        for s in summary["by_source"]:
            lines.append(f"  {s['source']}: {s['count']} itens")
        if summary["top_github"]:
            lines.append("Top GitHub:")
            for r in summary["top_github"]:
                stars = r.get('stars', 0)
                lines.append(f"  ⭐{stars} — {r['title']}")
        if summary["top_huggingface"]:
            lines.append("Top HuggingFace:")
            for r in summary["top_huggingface"]:
                downloads = r.get('downloads', 0)
                lines.append(f"  ⬇{downloads} — {r['title']}")
        stats_text = "\n".join(lines)
        prompt = (
            f"Você é analista do projeto The Moon Ecosystem.\n"
            f"Analise os dados de pesquisa sobre '{query}':\n\n"
            f"{stats_text}\n\n"
            f"Gere insights concisos (máx 150 palavras) sobre:\n"
            f"1. Padrões identificados nos dados\n"
            f"2. Oportunidades para o projeto\n"
            f"3. Próximos passos recomendados\n"
            f"Responda em português."
        )
        try:
            return await self._llm.complete(prompt, task_type="analysis", actor="data_pipeline_agent")
        except Exception as e:
            logger.warning("LLM insights falhou: %s", e)
            return stats_text

    # ─────────────────────────────────────────────
    # MESSAGEBUS HANDLERS
    # ─────────────────────────────────────────────

    def _on_pipeline_request_wrapper(self, message: Any) -> None:
        """Wrapper para receber mensagens do MessageBus."""
        sender = getattr(message, "sender", "unknown")
        payload = getattr(message, "payload", {})
        asyncio.create_task(self._on_pipeline_request(sender, payload))

    async def _on_pipeline_request(self, sender: str, payload: dict) -> None:
        """Handler para tópico pipeline.process."""
        pipeline_type = payload.get("type", "research")
        run_id = f"run_{int(time.time())}"
        logger.info("Pipeline iniciado: type=%s run_id=%s de=%s",
                    pipeline_type, run_id, sender)
        result = await self._execute(
            "process",
            type=pipeline_type,
            data=payload.get("data", {}),
            query=payload.get("query", ""),
            export=payload.get("export", False),
        )
        await self._bus.publish(
            "DataPipelineAgent",
            "pipeline.result",
            {"run_id": run_id, "success": result.success,
             "data": result.data, "error": result.error},
            target=sender,
        )

    async def _heartbeat_loop(self) -> None:
        """Loop de heartbeat a cada 60 segundos."""
        while True:
            await asyncio.sleep(60)
            await self._bus.publish(
                "DataPipelineAgent",
                "hive.heartbeat",
                {"status": "alive",
                 "db_path": str(self._db_path),
                 "timestamp": datetime.now(timezone.utc).isoformat()},
            )

    # ─────────────────────────────────────────────
    # _execute — interface AgentBase
    # ─────────────────────────────────────────────

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """Executa tarefas de pipeline de dados."""
        start = time.time()
        try:
            if task == "process":
                pipeline_type = kwargs.get("type", "research")
                data = kwargs.get("data", {})
                query = kwargs.get("query", "")
                do_export = kwargs.get("export", False)

                if pipeline_type == "research":
                    rows = await self.ingest_research(data)
                    summary = await self.summarize_research(query or None)
                    insights = await self.generate_insights(summary, query)
                    out = {"rows_ingested": rows, "summary": summary,
                           "insights": insights}
                    if do_export:
                        out["csv_path"] = await self.export_csv()
                    await self._bus.publish(
                        "DataPipelineAgent", "memory.store",
                        {"content": f"Pipeline insights ({query}):\n{insights}",
                         "topic": "pipeline",
                         "metadata": {"query": query, "rows": rows}},
                    )
                    return TaskResult(success=True, data=out,
                                      execution_time=time.time() - start)

                if pipeline_type == "json":
                    table = kwargs.get("table_name", "imported_data")
                    rows = await self.ingest_json(data if isinstance(data, list) else [data], table)
                    return TaskResult(success=True,
                                      data={"rows_ingested": rows, "table": table},
                                      execution_time=time.time() - start)

                return TaskResult(success=False,
                                  error=f"Tipo de pipeline desconhecido: {pipeline_type}",
                                  execution_time=time.time() - start)

            if task == "query":
                sql = kwargs.get("sql", "")
                if not sql:
                    return TaskResult(success=False, error="Parâmetro 'sql' obrigatório",
                                      execution_time=time.time() - start)
                rows = await self.run_query(sql)
                return TaskResult(success=True,
                                  data={"rows": rows, "count": len(rows)},
                                  execution_time=time.time() - start)

            if task == "summarize":
                summary = await self.summarize_research(kwargs.get("query_filter"))
                return TaskResult(success=True, data=summary,
                                  execution_time=time.time() - start)

            if task == "export_csv":
                path = await self.export_csv(
                    kwargs.get("table", "research_results"),
                    kwargs.get("filename"),
                )
                return TaskResult(success=True, data={"path": path},
                                  execution_time=time.time() - start)

            if task == "export_json":
                path = await self.export_json(
                    kwargs.get("table", "research_results"),
                    kwargs.get("filename"),
                )
                return TaskResult(success=True, data={"path": path},
                                  execution_time=time.time() - start)

            if task == "status":
                tables = await self.run_query(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                )
                return TaskResult(
                    success=True,
                    data={"db_path": str(self._db_path),
                          "tables": [t["table_name"] for t in tables]},
                    execution_time=time.time() - start,
                )

            return TaskResult(success=False, error=f"Task desconhecida: {task}",
                              execution_time=time.time() - start)

        except Exception as e:
            logger.exception("DataPipelineAgent._execute falhou: task=%s", task)
            return TaskResult(success=False, error=str(e),
                              execution_time=time.time() - start)

    async def close(self) -> None:
        """Fecha conexão com o banco de dados."""
        if self._conn:
            self._conn.close()
            logger.info("DataPipelineAgent — conexão DuckDB fechada")
