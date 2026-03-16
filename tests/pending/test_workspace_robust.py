
import os
import shutil
import pytest
import asyncio
from core.workspace.manager import WorkspaceManager
from core.workspace.room import AgentRoom
from core.workspace.computer import AgentMachine
from core.workspace.network import AgentNetwork
from core.message_bus import MessageBus

# Configuração de diretório de teste
TEST_BASE_PATH = "learning/workspaces_robust_test"

@pytest.fixture(scope="function")
def clean_workspace():
    bus = MessageBus()
    bus.reset()
    if os.path.exists(TEST_BASE_PATH):
        shutil.rmtree(TEST_BASE_PATH)
    yield TEST_BASE_PATH
    if os.path.exists(TEST_BASE_PATH):
        shutil.rmtree(TEST_BASE_PATH)
    bus.reset()

@pytest.mark.asyncio
async def test_room_initialization(clean_workspace):
    manager = WorkspaceManager(base_path=clean_workspace)
    room = await manager.create_room("Test Coding", "CoderAgent")
    
    assert room.room_id == "test_coding"
    assert os.path.exists(room.path)
    assert os.path.exists(room.computer_path)
    assert os.path.exists(os.path.join(room.path, "meeting_log.md"))
    
    status = room.get_status()
    assert status["leader"] == "CoderAgent"
    assert status["computer_ready"] is True

@pytest.mark.asyncio
async def test_computer_operations(clean_workspace):
    room_path = os.path.join(clean_workspace, "rooms/test_room")
    os.makedirs(room_path, exist_ok=True)
    comp_path = os.path.join(room_path, "computer")
    
    machine = AgentMachine("test_room", comp_path)
    
    # Test writing and reading
    machine.write_file("logic.py", "def add(a, b): return a + b")
    content = machine.read_file("logic.py")
    assert "def add" in content
    
    # Test subdirectories
    machine.write_file("test_logic.py", "assert add(1, 1) == 2", subdir="tests")
    assert os.path.exists(os.path.join(comp_path, "tests/test_logic.py"))
    
    # Test listing
    files = machine.list_files()
    assert "logic.py" in files["src"]
    assert "test_logic.py" in files["tests"]

@pytest.mark.asyncio
async def test_network_and_manager_integration(clean_workspace):
    manager = WorkspaceManager(base_path=clean_workspace)
    
    room_a = await manager.create_room("Room A", "AgentA")
    room_b = await manager.create_room("Room B", "AgentB")
    
    network = AgentNetwork(manager.message_bus)
    
    # Direct message
    await network.send_data(sender="room_a", data="Hello Room B", target="room_b")
    await asyncio.sleep(0.1) # Aguarda processamento do bus
    
    with open(os.path.join(room_b.path, "meeting_log.md"), "r") as f:
        log_b = f.read()
        assert "Mensagem recebida de room_a: Hello Room B" in log_b
        
    # Broadcast
    await network.send_data(sender="room_a", data="Flash Alert!")
    await asyncio.sleep(0.1)
    
    with open(os.path.join(room_b.path, "meeting_log.md"), "r") as f:
        log_b = f.read()
        assert "Broadcast de room_a: Flash Alert!" in log_b

@pytest.mark.asyncio
async def test_persistence(clean_workspace):
    manager = WorkspaceManager(base_path=clean_workspace)
    await manager.create_room("Persistent Room", "Admin")
    
    # Simula desligamento e reinício
    manager2 = WorkspaceManager(base_path=clean_workspace)
    # Precisamos "re-registrar" ou o manager deve escanear? 
    # Atualmente o manager mantém em self.rooms as criadas em runtime.
    # Vamos adicionar uma funcionalidade de scan no manager.
    
    # Por enquanto, garantimos que os arquivos físicos estão lá
    assert os.path.exists(os.path.join(clean_workspace, "rooms/persistent_room"))

@pytest.mark.asyncio
async def test_error_handling(clean_workspace):
    machine = AgentMachine("error_room", os.path.join(clean_workspace, "error_comp"))
    result = machine.read_file("ghost.txt")
    assert "not found" in result
