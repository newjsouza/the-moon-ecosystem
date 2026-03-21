"""
core/supabase_client.py
Cliente Supabase singleton para todo o ecossistema The Moon.

Fornece acesso ao cliente Supabase para:
  - Armazenamento de dados (PostgreSQL)
  - Autenticação
  - Realtime subscriptions
  - Storage (buckets de arquivos)
  - Edge Functions

Uso:
    from core.supabase_client import SupabaseClient
    
    client = SupabaseClient()
    
    # Operações básicas
    response = client.client.table("memories").select("*").execute()
    
    # Ou usar métodos helper
    memories = await client.get_memories(limit=10)
"""
import os
import logging
from typing import Optional, Any, Dict, List
from dotenv import load_dotenv

logger = logging.getLogger("moon.supabase")


class SupabaseClient:
    """
    Singleton client para Supabase.
    
    Atributos:
        client: Cliente Supabase principal
        url: URL do projeto Supabase
        key: Chave de API (anon ou service_role)
    """
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupabaseClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if getattr(self, '_initialized', False):
            return
            
        load_dotenv()
        
        self.url = os.getenv("SUPABASE_URL", "")
        self.key = os.getenv("SUPABASE_ANON_KEY", "")
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        
        self._client = None
        self._initialized = True
        
        if not self.url or not self.key:
            logger.warning(
                "⚠️ Supabase não configurado. Defina SUPABASE_URL e SUPABASE_ANON_KEY no .env"
            )
    
    @property
    def client(self):
        """
        Retorna cliente Supabase lazy-loaded.
        
        Returns:
            Cliente Supabase ou None se não configurado.
        """
        if self._client is None and self.url and self.key:
            try:
                from supabase import create_client
                self._client = create_client(self.url, self.key)
                logger.info("✅ Cliente Supabase inicializado")
            except ImportError:
                logger.error("❌ Pacote supabase não instalado. Execute: pip install supabase")
            except Exception as e:
                logger.error(f"❌ Erro ao criar cliente Supabase: {e}")
        
        return self._client
    
    @property
    def admin_client(self):
        """
        Retorna cliente Supabase com chave de serviço (admin).
        
        Use apenas para operações que requerem privilégios elevados.
        
        Returns:
            Cliente Supabase com service_role key ou None.
        """
        if self.url and self.service_key:
            try:
                from supabase import create_client
                return create_client(self.url, self.service_key)
            except Exception as e:
                logger.error(f"❌ Erro ao criar cliente admin Supabase: {e}")
                return None
        return None
    
    def is_configured(self) -> bool:
        """Verifica se Supabase está configurado."""
        return bool(self.url and self.key)
    
    async def test_connection(self) -> bool:
        """
        Testa conexão com Supabase.
        
        Returns:
            True se conexão bem-sucedida, False caso contrário.
        """
        if not self.client:
            return False
        
        try:
            # Tenta fazer uma query simples
            response = self.client.table("_dummy_table_").select("count").limit(1).execute()
            return True
        except Exception as e:
            # Erro esperado se tabela não existir, mas conexão OK
            if "relation" in str(e).lower() or "does not exist" in str(e).lower():
                logger.debug("✅ Conexão Supabase OK (tabela de teste não existe, mas servidor respondeu)")
                return True
            logger.error(f"❌ Erro de conexão Supabase: {e}")
            return False
    
    # ── Métodos Helper para Operações Comuns ──────────────
    
    async def insert(self, table: str, data: Dict[str, Any]) -> Optional[Any]:
        """
        Insere dados em uma tabela.
        
        Args:
            table: Nome da tabela
            data: Dados para inserir
            
        Returns:
            Dados inseridos ou None se falhar.
        """
        if not self.client:
            logger.error("Supabase client não inicializado")
            return None
        
        try:
            response = self.client.table(table).insert(data).execute()
            return response.data
        except Exception as e:
            logger.error(f"Erro ao inserir em {table}: {e}")
            return None
    
    async def select(
        self,
        table: str,
        columns: str = "*",
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> List[Any]:
        """
        Seleciona dados de uma tabela.
        
        Args:
            table: Nome da tabela
            columns: Colunas para selecionar
            filters: Filtros {campo: valor}
            limit: Limite de resultados
            
        Returns:
            Lista de resultados.
        """
        if not self.client:
            return []
        
        try:
            query = self.client.table(table).select(columns)
            
            if filters:
                for field, value in filters.items():
                    query = query.eq(field, value)
            
            if limit:
                query = query.limit(limit)
            
            response = query.execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Erro ao selecionar de {table}: {e}")
            return []
    
    async def update(
        self,
        table: str,
        data: Dict[str, Any],
        filters: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Atualiza dados em uma tabela.
        
        Args:
            table: Nome da tabela
            data: Dados para atualizar
            filters: Filtros para encontrar registros
            
        Returns:
            Dados atualizados ou None.
        """
        if not self.client:
            return None
        
        try:
            query = self.client.table(table).update(data)
            
            for field, value in filters.items():
                query = query.eq(field, value)
            
            response = query.execute()
            return response.data
        except Exception as e:
            logger.error(f"Erro ao atualizar em {table}: {e}")
            return None
    
    async def delete(self, table: str, filters: Dict[str, Any]) -> bool:
        """
        Deleta dados de uma tabela.
        
        Args:
            table: Nome da tabela
            filters: Filtros para encontrar registros
            
        Returns:
            True se sucesso, False caso contrário.
        """
        if not self.client:
            return False
        
        try:
            query = self.client.table(table).delete()
            
            for field, value in filters.items():
                query = query.eq(field, value)
            
            query.execute()
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar de {table}: {e}")
            return False


# ── Instância Global ──────────────────────────────────────

def get_supabase_client() -> SupabaseClient:
    """
    Retorna instância singleton do cliente Supabase.
    
    Returns:
        SupabaseClient configurado.
    """
    return SupabaseClient()
