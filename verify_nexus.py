
import asyncio
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.nexus_intelligence import NexusIntelligence
from core.message_bus import MessageBus

async def main():
    print("🧪 Iniciando Verificação do NexusIntelligence...")
    
    bus = MessageBus()
    nexus = NexusIntelligence(message_bus=bus)
    
    await nexus.initialize()
    
    # Injeta eventos simulados
    print("📡 Injetando eventos de teste...")
    await bus.publish("test", "watchdog.alert", {"service": "vault", "error": "timeout"})
    await bus.publish("test", "agent.fail", {"agent": "VaultAgent", "error": "connection"})
    await bus.publish("test", "user.command", {"text": "nexus status"})
    
    # Aguarda processamento
    await asyncio.sleep(2)
    
    # Valida ingestão
    count = len(nexus._stream.get_window())
    print(f"✅ Eventos no stream: {count}")
    
    # Valida análise
    print("🔍 Rodando análise manual...")
    insights = nexus._patterns.analyze(nexus._stream)
    print(f"✅ Insights gerados: {len(insights)}")
    for i in insights:
        print(f"   - [{i.severity}] {i.title}: {i.description}")
        
    # Valida persistência
    print("💾 Testando persistência...")
    await nexus.shutdown()
    
    if os.path.exists("data/nexus/event_stream.json"):
        size = os.path.getsize("data/nexus/event_stream.json")
        print(f"✅ Arquivo de persistência criado ({size} bytes)")
    
    print("\n✨ Verificação concluída com sucesso!")

if __name__ == "__main__":
    asyncio.run(main())
