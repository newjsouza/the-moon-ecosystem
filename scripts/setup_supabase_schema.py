#!/usr/bin/env python3
"""
scripts/setup_supabase_schema.py
Configura o schema Supabase de forma totalmente autônoma.
Executa via: python3 scripts/setup_supabase_schema.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db_executor import execute_statements, execute_sql_file

SCHEMA_STATEMENTS = [
    (
        "CREATE EXTENSION IF NOT EXISTS vector",
        "extensao_vector"
    ),
    (
        """
        CREATE TABLE IF NOT EXISTS moon_memory (
            id           BIGSERIAL PRIMARY KEY,
            agent_source TEXT        NOT NULL,
            topic        TEXT        NOT NULL,
            content      TEXT        NOT NULL,
            embedding    vector(384),
            metadata     JSONB       DEFAULT '{}',
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "tabela_moon_memory"
    ),
    (
        """
        CREATE INDEX IF NOT EXISTS moon_memory_topic_idx
            ON moon_memory (topic)
        """,
        "index_topic"
    ),
    (
        """
        CREATE INDEX IF NOT EXISTS moon_memory_agent_idx
            ON moon_memory (agent_source)
        """,
        "index_agent"
    ),
    (
        """
        CREATE OR REPLACE FUNCTION moon_memory_search(
            query_embedding vector(384),
            match_count     INT   DEFAULT 5,
            filter_topic    TEXT  DEFAULT NULL,
            min_similarity  FLOAT DEFAULT 0.3
        )
        RETURNS TABLE(
            id           BIGINT,
            agent_source TEXT,
            topic        TEXT,
            content      TEXT,
            metadata     JSONB,
            similarity   FLOAT
        )
        LANGUAGE plpgsql AS $$
        BEGIN
            RETURN QUERY
            SELECT
                m.id,
                m.agent_source,
                m.topic,
                m.content,
                m.metadata,
                1 - (m.embedding <=> query_embedding) AS similarity
            FROM moon_memory m
            WHERE (filter_topic IS NULL OR m.topic = filter_topic)
              AND (1 - (m.embedding <=> query_embedding)) >= min_similarity
            ORDER BY m.embedding <=> query_embedding
            LIMIT match_count;
        END;
        $$
        """,
        "funcao_moon_memory_search"
    ),
]

IVFFLAT_INDEX = (
    """
    CREATE INDEX IF NOT EXISTS moon_memory_embedding_idx
        ON moon_memory USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """,
    "index_ivfflat"
)

VERIFY_SQL = (
    """
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'moon_memory'
    """,
    "verificacao"
)


def main():
    print("🌕 The Moon — Configuração autônoma do Supabase")
    print("=" * 50)

    print("\n[1/3] Criando schema base...")
    results = execute_statements(SCHEMA_STATEMENTS)
    for r in results:
        status = "✅" if r["success"] else "❌"
        print(f"  {status} {r['label']}: {r.get('error', 'ok')}")

    failures = [r for r in results if not r["success"]
                and "already exists" not in r.get("error", "")]
    if failures:
        print("\n❌ Schema base falhou — abortando")
        sys.exit(1)

    print("\n[2/3] Verificando tabela moon_memory...")
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv()
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='moon_memory'"
        )
        exists = cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM moon_memory")
        row_count = cur.fetchone()[0]
        cur.close()
        conn.close()
        print(f"  ✅ moon_memory existe: {exists} | registros: {row_count}")
    except Exception as e:
        print(f"  ❌ Verificação falhou: {e}")
        sys.exit(1)

    if row_count > 0:
        print("\n[3/3] Criando índice ivfflat (tabela tem dados)...")
        result = execute_sql_file(*IVFFLAT_INDEX)
        status = "✅" if result["success"] else "⚠️ "
        print(f"  {status} ivfflat: {result.get('error', 'criado')}")
    else:
        print("\n[3/3] ivfflat: aguardando primeiro INSERT (tabela vazia)")
        print("  → Execute novamente após o MemoryAgent inserir dados")

    print("\n✅ Schema Supabase configurado com sucesso!")
    print("   Próximo passo: python3 -c 'from agents.memory_agent import ...'")


if __name__ == "__main__":
    main()
