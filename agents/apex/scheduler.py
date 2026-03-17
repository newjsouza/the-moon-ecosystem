"""
agents/apex/scheduler.py
Script standalone para testar/executar o ApexOracle manualmente.
Uso:
  python3 agents/apex/scheduler.py --morning   # força ciclo matinal agora
  python3 agents/apex/scheduler.py --loop      # inicia loop autônomo
  python3 agents/apex/scheduler.py --status    # mostra contexto do dia
"""
import asyncio
import argparse
import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv()

from agents.apex.oracle import ApexOracle, DailyContextStore
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

async def main():
    parser = argparse.ArgumentParser(description="APEX Oracle CLI")
    parser.add_argument("--morning", action="store_true", help="Executa ciclo matinal agora")
    parser.add_argument("--loop",    action="store_true", help="Inicia loop autônomo")
    parser.add_argument("--status",  action="store_true", help="Mostra contexto do dia")
    args = parser.parse_args()

    oracle = ApexOracle()

    if args.morning:
        print("▶️ Executando ciclo matinal...")
        await oracle.run_morning_cycle()
        print("✅ Concluído.")

    elif args.loop:
        print("▶️ Iniciando loop autônomo (Ctrl+C para parar)...")
        try:
            await oracle.run_autonomous_loop()
        except KeyboardInterrupt:
            print("\n⏹️ Loop encerrado.")

    elif args.status:
        ctx = DailyContextStore()
        data = ctx._context
        date = data.get("date", "—")
        analyses = data.get("analyses", [])
        print(f"\n📅 Data: {date}")
        print(f"⚽ Análises do dia: {len(analyses)}")
        for a in analyses:
            summary = next(
                (m for m in data.get("matches_summary", []) if m["match_id"] == a["match_id"]),
                {}
            )
            pre45 = "✅" if summary.get("pre45_sent") else "⏳"
            print(f"  {pre45} {a['teams']} — {a['kickoff_local']}")
        if not analyses:
            print("  (nenhuma análise registrada — execute --morning primeiro)")
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main())
