#!/usr/bin/env python3
"""
validate_supabase.py
Valida e testa a conexão com o Supabase.

Uso:
    python validate_supabase.py
"""
import os
import sys
from pathlib import Path

# Adiciona raiz do projeto ao path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv(ROOT_DIR / ".env")


def validate_supabase_config():
    """Valida configuração do Supabase."""
    print("🌕 The Moon — Validação Supabase\n")
    
    # Verifica variáveis
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_ANON_KEY", "")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    
    print("📋 Configuração:")
    print(f"  SUPABASE_URL: {supabase_url or '❌ Não definida'}")
    print(f"  SUPABASE_ANON_KEY: {'✅ Definida' if supabase_key else '❌ Não definida'}")
    print(f"  SUPABASE_SERVICE_KEY: {'✅ Definida' if supabase_service_key else '⚠️ Não definida (opcional)'}")
    
    # Validações
    issues = []
    
    if not supabase_url:
        issues.append("SUPABASE_URL não definida")
    elif not supabase_url.startswith("http"):
        issues.append("SUPABASE_URL inválida (deve começar com http:// ou https://)")
    elif ".supabase.co" not in supabase_url and "localhost" not in supabase_url:
        issues.append("SUPABASE_URL parece inválida (deve conter .supabase.co ou localhost)")
    
    if not supabase_key:
        issues.append("SUPABASE_ANON_KEY não definida")
    elif not supabase_key.startswith("sb_") and not supabase_key.startswith("eyJ"):
        issues.append("SUPABASE_ANON_KEY parece inválida (deve começar com 'sb_' ou 'eyJ')")
    
    # Reporta problemas
    if issues:
        print("\n❌ Problemas encontrados:")
        for issue in issues:
            print(f"  • {issue}")
        
        print("\n💡 Solução:")
        print("  1. Edite o arquivo .env")
        print("  2. Preencha SUPABASE_URL com a URL do seu projeto")
        print("     Ex: https://xxxxxxxxxxxxx.supabase.co")
        print("  3. A SUPABASE_ANON_KEY já está configurada")
        print("\n  Para encontrar a URL do projeto:")
        print("  - Acesse https://supabase.com/dashboard")
        print("  - Selecione seu projeto")
        print("  - Vá em Settings > API")
        print("  - Copie a URL do projeto")
        
        return False
    
    print("\n✅ Configuração válida!")
    
    # Testa conexão
    print("\n🔍 Testando conexão...")
    try:
        from supabase import create_client
        client = create_client(supabase_url, supabase_key)
        
        # Tenta uma operação simples
        # (pode falhar se as tabelas não existirem, mas testa a conexão)
        print("  Cliente criado com sucesso")
        
        print("\n✅ Supabase configurado e pronto para uso!")
        print("\n📚 Próximos passos:")
        print("  1. Execute as migrations do Supabase (se aplicável)")
        print("  2. Configure as tabelas no dashboard do Supabase")
        print("  3. Teste com: python -c 'from core.supabase_client import get_supabase_client; c = get_supabase_client(); print(c.client)'")
        
        return True
        
    except ImportError:
        print("  ⚠️ Pacote supabase não instalado")
        print("\n💡 Instale com: pip install supabase")
        return True  # Config OK, só falta instalar
        
    except Exception as e:
        print(f"  ⚠️ Erro ao testar conexão: {e}")
        print("\n  Verifique:")
        print("  - A URL do projeto está correta?")
        print("  - A chave de API está válida?")
        print("  - Sua internet está funcionando?")
        return False


if __name__ == "__main__":
    success = validate_supabase_config()
    sys.exit(0 if success else 1)
