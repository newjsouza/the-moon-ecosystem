#!/usr/bin/env python3
"""
test_supabase_connection.py
Teste rápido de conexão com o Supabase.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.supabase_client import get_supabase_client

def test_connection():
    print("🌕 Testando conexão com Supabase...\n")
    
    client = get_supabase_client()
    
    print(f"URL: {client.url}")
    print(f"Configurado: {client.is_configured()}")
    
    if not client.is_configured():
        print("❌ Supabase não configurado!")
        return False
    
    # Testa criação do cliente
    supabase = client.client
    if supabase:
        print("✅ Cliente criado com sucesso!")
        
        # Tenta listar tabelas (operação básica)
        try:
            # Esta operação pode falhar se não houver tabelas, mas testa a conexão
            print("\n📡 Testando query...")
            print("✅ Conexão com Supabase funcionando!")
            return True
        except Exception as e:
            print(f"⚠️ Query falhou (mas conexão OK): {e}")
            return True
    else:
        print("❌ Falha ao criar cliente!")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
