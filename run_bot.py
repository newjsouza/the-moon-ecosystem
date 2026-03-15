"""
run_bot.py — Entry point do MoonBot (The Moon Ecosystem).
Inicializa o bot com integração opcional ao Orchestrator.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Garante que o root do projeto está no PYTHONPATH
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

load_dotenv()

def main():
    # Tentativa de integração com o Orchestrator (opcional)
    orchestrator = None
    try:
        from core.orchestrator import Orchestrator
        # Se o Orchestrator já foi inicializado em outro processo,
        # podemos tentar conectar. Caso contrário, o bot roda standalone.
        print("⚡ Tentando conectar ao Orchestrator...")
        # orchestrator = get_running_orchestrator()  # implemente se necessário
    except Exception as e:
        print(f"⚠️  Orchestrator não disponível — bot rodando standalone: {e}")

    from agents.telegram.bot import MoonBot
    bot = MoonBot(orchestrator=orchestrator)
    print("🌙 MoonBot iniciando...")
    bot.run()

if __name__ == "__main__":
    main()
