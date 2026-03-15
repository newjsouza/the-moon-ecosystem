import asyncio
from core.workspace.manager import WorkspaceManager
from core.workspace.network import AgentNetwork
from core.message_bus import MessageBus

async def simulate_activity():
    print("🚀 Iniciando Simulação de Atividade para o Monitor...")
    bus = MessageBus()
    manager = WorkspaceManager()
    
    # Create some rooms
    rooms = [
        ("Analista Esportivo", "João"),
        ("Pesquisador", "Ana"),
        ("Arquiteto", "Bruno"),
        ("Financeiro", "Clara")
    ]
    
    room_instances = []
    for skill, leader in rooms:
        room = await manager.create_room(skill, leader)
        room_instances.append(room)
        print(f"✅ Sala {skill} ativa.")

    network = AgentNetwork(bus)
    
    # Simulation loop
    for i in range(10):
        # 1. Broadcast random alert
        print(f"--- Ciclo {i+1} ---")
        await network.send_data("Simulador", f"Alerta Global #{i+1}: Sincronização de dados em andamento.")
        await asyncio.sleep(2)
        
        # 2. Direct message between specific rooms
        await network.send_data("analista_esportivo", f"Relatório financeiro #{i+1} processado.", "financeiro")
        await asyncio.sleep(1)
        
        await network.send_data("pesquisador", "Novas APIs detectadas.", "arquiteto")
        await asyncio.sleep(2)

    print("✨ Simulação concluída.")

if __name__ == "__main__":
    asyncio.run(simulate_activity())
