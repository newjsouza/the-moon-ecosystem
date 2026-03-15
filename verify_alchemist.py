import asyncio
import os
import sys
import json
from agents.skill_alchemist import SkillAlchemist
from core.orchestrator import Orchestrator

async def verify_alchemist():
    print("🚀 Inciando Verificação SkillAlchemist...")
    
    # 1. Mock Orchestrator
    orchestrator = Orchestrator()
    alchemist = SkillAlchemist(orchestrator=orchestrator)
    
    # 2. Teste de Descoberta (Mock)
    print("\n[1/3] Testando Descoberta...")
    candidates = await alchemist._discover_candidates()
    if len(candidates) > 0:
        print(f"✅ {len(candidates)} candidatos encontrados.")
    else:
        print("❌ Falha na descoberta (verifique conexão ou API).")

    # 3. Teste de Scoring
    print("\n[2/3] Testando Scoring...")
    promising = alchemist._score_candidates(candidates)
    print(f"✅ {len(promising)} candidatos promissores selecionados.")

    # 4. Teste de Transmutação (Manual/Small)
    print("\n[3/3] Testando Transmutação (Sandbox)...")
    if promising:
        test_tool = promising[0]
        success = await alchemist._transmute(test_tool)
        if success:
            print(f"✅ Habilidade {test_tool['name']} sintetizada com sucesso.")
            # Verifica arquivos
            if os.path.exists(f"{alchemist.quarantine}/{test_tool['name']}.py"):
                print(f"✅ Arquivo .py gerado.")
            if os.path.exists(f"{alchemist.quarantine}/{test_tool['name']}_proposal.json"):
                print(f"✅ Proposta JSON gerada.")
        else:
            print("❌ Falha na transmutação.")
    else:
        print("⏭️ Sem candidatos promissores para testar transmutação.")

    print("\n✨ Verificação concluída.")

if __name__ == "__main__":
    asyncio.run(verify_alchemist())
