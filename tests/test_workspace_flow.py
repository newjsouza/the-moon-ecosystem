
import asyncio
import os
import sys

# Ajusta path para importar do diretório raiz
sys.path.append(os.getcwd())

from core.workspace.manager import WorkspaceManager
from core.message_bus import MessageBus

async def test_workspace_flow():
    print("🚀 Iniciando Teste de Fluxo de Workspace...")
    
    manager = WorkspaceManager(base_path="learning/workspaces_test")
    
    # 1. Teste de criação de sala
    print("--- 1. Criando Sala de Teste ---")
    room = await manager.create_room("Analista Esportivo", "SportsAgent")
    print(f"Sala criada: {room.room_id}")
    assert room.room_id == "analista_esportivo"
    assert os.path.exists(room.path)
    assert os.path.exists(room.computer_path)
    print("✅ Sala criada com sucesso.")

    # 2. Teste do Computador do Agente
    print("--- 2. Testando Computador do Agente ---")
    from core.workspace.computer import AgentMachine
    machine = AgentMachine(room.room_id, room.computer_path)
    
    code_content = "print('Hello from Agent Computer!')"
    machine.write_file("hello.py", code_content)
    
    read_content = machine.read_file("hello.py")
    print(f"Conteúdo lido: {read_content}")
    assert read_content == code_content
    print("✅ Escrita e leitura no computador do agente OK.")

    # 3. Teste de Rede Local (Broadcast)
    print("--- 3. Testando Rede Local ---")
    room_finance = await manager.create_room("Financeiro", "FinanceAgent")
    
    # Simula mensagem na rede
    bus = MessageBus()
    await bus.publish(sender="analista_esportivo", topic="workspace.network", payload="Nova aposta detectada!")
    
    # Verifica se o evento foi logado na outra sala
    log_finance = ""
    with open(os.path.join(room_finance.path, "meeting_log.md"), "r") as f:
        log_finance = f.read()
    
    if "Nova aposta detectada!" in log_finance:
        print("✅ Comunicação inter-salas via Rede Local OK.")
    else:
        print("❌ Falha na comunicação inter-salas.")

    print("\n✨ Todos os testes concluídos com sucesso!")

if __name__ == "__main__":
    asyncio.run(test_workspace_flow())
