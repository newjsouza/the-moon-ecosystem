"""
examples/run_blog.py
Demonstration of the Autonomous Blog Ecosystem.
"""
import asyncio
import sys
import os

# Ensure the root project directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from main import MoonSystem
from core.agent_base import AgentPriority

async def run_blog():
    print("--- Starting The Moon: Autonomous Blog Ecosystem ---")
    system = MoonSystem()
    await system.start()
    
    # Lista de temas para o trio de artigos profissionais
    topics = [
        "A nova realidade do livre acesso e gratuidade às ferramentas de inteligência Artificial",
        "Ecossistemas Autônomos: Como agentes de IA estão transformando a gestão de conteúdo digital",
        "A Próxima Fronteira: Impactos da Computação Quântica na Segurança da Informação Global"
    ]
    
    for i, topic in enumerate(topics):
        print(f"\n[{i+1}/{len(topics)}] Iniciando geração do artigo: '{topic}'")
        res = await system.orchestrator.execute(
            task=topic, 
            agent_name="BlogManagerAgent", 
            orchestrator=system.orchestrator
        )
        
        print(f"--- RESULTADO DA PUBLICAÇÃO {i+1} ---")
        print(f"Sucesso: {res.success} - Data: {res.data} - Error: {res.error}")

    print("\nStatus Final dos Agentes:", system.orchestrator.get_status())
    
    print("\n--- Parando ---")
    await system.stop()

if __name__ == "__main__":
    asyncio.run(run_blog())
