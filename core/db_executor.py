"""
core/db_executor.py
Executor SQL direto via psycopg2.
Permite ao sistema executar DDL (CREATE TABLE, CREATE INDEX,
CREATE FUNCTION) de forma autônoma, sem interface web.
Usa DATABASE_URL do .env.
"""
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def execute_sql_file(sql: str, label: str = "sql") -> dict:
    """
    Executa bloco SQL arbitrário via psycopg2.
    Retorna dict com success, rows_affected, error.
    """
    try:
        import psycopg2
    except ImportError:
        return {"success": False, "error": "psycopg2 não instalado: pip install psycopg2-binary"}

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        return {"success": False, "error": "DATABASE_URL não configurada no .env"}

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(sql)
        logger.info("SQL executado com sucesso: %s", label)
        rowcount = cursor.rowcount if cursor.rowcount != -1 else 0
        cursor.close()
        conn.close()
        return {"success": True, "rows_affected": rowcount, "label": label}
    except Exception as e:
        logger.error("Erro ao executar SQL '%s': %s", label, e)
        return {"success": False, "error": str(e), "label": label}


def execute_statements(statements: list[tuple[str, str]]) -> list[dict]:
    """
    Executa lista de (sql, label) em sequência.
    Para na primeira falha crítica.
    """
    results = []
    for sql, label in statements:
        result = execute_sql_file(sql, label)
        results.append(result)
        if not result["success"] and "already exists" not in result.get("error", ""):
            logger.error("Falha crítica em '%s': %s", label, result["error"])
            break
    return results
