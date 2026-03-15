import asyncio
import os
import json
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

from agents.autonomous_devops_refactor import AutonomousDevOpsRefactor
from core.message_bus import MessageBus

async def test_scan():
    print("🚀 Iniciando Teste do Agente DevOps...")
    
    # Mock settings for testing
    os.environ["GITHUB_TOKEN"] = "mock_token"
    os.environ["GITHUB_REPO"] = "mock/repo"
    
    bus = MessageBus()
    agent = AutonomousDevOpsRefactor(message_bus=bus)
    await agent.initialize()
    
    print("🔍 Executando 'run_scan'...")
    result = await agent.execute("run_scan")
    
    if result.success:
        report_path = result.data.get("report_path")
        summary = result.data.get("summary")
        print(f"✅ Scan concluído com sucesso!")
        print(f"📄 Relatório: {report_path}")
        print(f"📊 Resumo: {summary}")
        
        if report_path and os.path.exists(report_path):
            with open(report_path, 'r') as f:
                report = json.load(f)
                num_issues = len(report.get("issues", []))
                print(f"📈 Total de problemas detectados: {num_issues}")
                
                # Check for critical issues that might have been auto-healed (if any)
                actions = report.get("actions_taken", [])
                if actions:
                    print(f"🛠️ Ações executadas: {actions}")
                    
        return True
    else:
        print(f"❌ Scan falhou: {result.error}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_scan())
    sys.exit(0 if success else 1)
