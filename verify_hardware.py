import asyncio
import os
from agents.hardware_synergy_bridge import HardwareSynergyBridge

async def verify_agent():
    print("🔍 Iniciando Verificação do HardwareSynergyBridge...")
    
    # Mocking dependencies
    class MockLLM:
        async def create(self, **kwargs):
            class MockChoice:
                message = type('obj', (object,), {'content': 'Teste de transcrição OK'})
            return type('obj', (object,), {'choices': [MockChoice()]})
            
    agent = HardwareSynergyBridge(groq_client=MockLLM())
    
    try:
        print("🛠️ Inicializando agente...")
        await agent.initialize()
        
        print("📊 Checando status do hardware...")
        status = await agent.execute("status")
        print(f"   Status: {status.data}")
        
        if status.data.get('overlay_available'):
            print("✅ Overlay GTK3: Disponível")
        else:
            print("⚠️ Overlay GTK3: INDISPONÍVEL (Esperado se sem X11/Wayland)")
            
        print("🔊 Testando volume...")
        vol_res = await agent.execute("volume", action="get")
        print(f"   Volume atual: {vol_res.data.get('volume')}")
        
        print("🎤 Testando lista de dispositivos...")
        dev_res = await agent.execute("list_devices")
        print(f"   Dispositivos encontrados: {len(dev_res.data.get('devices', []))}")
        
        print("✅ Verificação básica concluída com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro durante verificação: {e}")
    finally:
        await agent.shutdown()

if __name__ == "__main__":
    asyncio.run(verify_agent())
