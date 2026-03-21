"""
moon_sync.py — Script de sync manual para uso no terminal.

Uso:
  python3 moon_sync.py                        # sync se houver mudanças
  python3 moon_sync.py "feat: minha feature"  # sync com mensagem custom
  python3 moon_sync.py --status               # ver status sem commitar
  python3 moon_sync.py --force                # forçar commit mesmo sem mudanças
  python3 moon_sync.py --serve                # iniciar daemon (AutonomousLoop)
  python3 moon_sync.py --health               # exibir relatório de saúde
  python3 moon_sync.py --schedule             # agendar tarefa recorrente
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Adicionar projeto ao path
sys.path.insert(0, str(Path(__file__).parent))


async def cmd_serve():
    """Start The Moon daemon (AutonomousLoop)."""
    from core.env_validator import EnvValidator
    EnvValidator().validate_or_exit()
    from core.daemon import MoonDaemon
    daemon = MoonDaemon()
    await daemon.start()


async def cmd_health():
    """Show system health report."""
    from core.observability.observer import MoonObserver
    obs = MoonObserver.get_instance()
    report = await obs.health_report()
    import json
    print(json.dumps(report, indent=2, default=str))
    obs.print_dashboard()
    MoonObserver.reset_instance()


def cmd_schedule(task_spec: str):
    """Schedule a task: "agent_id:task:priority"."""
    # Format: "agent_id:task_string:priority"
    parts = task_spec.split(':', 2)
    agent_id = parts[0]
    task = parts[1] if len(parts) > 1 else 'run'
    priority = int(parts[2]) if len(parts) > 2 else 5
    from core.loop_task import LoopTask
    import json
    lt = LoopTask(agent_id=agent_id, task=task, priority=priority)
    print(json.dumps(lt.to_dict(), indent=2, default=str))
    print(f"LoopTask created: {lt.task_id}")


async def main():
    parser = argparse.ArgumentParser(description="The Moon Ecosystem CLI")
    parser.add_argument("message", nargs="?", help="Commit message (optional)")
    parser.add_argument("--status", action="store_true", help="Show status without committing")
    parser.add_argument("--force", action="store_true", help="Force commit even without changes")
    parser.add_argument("--serve", action="store_true", help="Start The Moon daemon (AutonomousLoop)")
    parser.add_argument("--health", action="store_true", help="Show system health report")
    parser.add_argument("--schedule", metavar='TASK', help='Schedule a task: "agent_id:task:priority"')
    
    args = parser.parse_args()

    # Handle new commands first
    if args.serve:
        await cmd_serve()
        return
    elif args.health:
        await cmd_health()
        return
    elif args.schedule:
        cmd_schedule(args.schedule)
        return

    # Original sync functionality
    from core.services.auto_sync import get_auto_sync

    sync = get_auto_sync()

    # --status: apenas mostrar estado
    if args.status:
        dirty = sync.is_dirty()
        changed = sync.get_changed_files()
        remote = sync._remote_url
        print(f"Remote: {remote or 'não configurado'}")
        print(f"Dirty: {dirty}")
        print(f"Arquivos modificados ({len(changed)}):")
        for f in changed:
            print(f"  {f}")
        return

    # Mensagem customizada (primeiro arg não-flag)
    message = args.message
    force = args.force

    if force:
        result = await sync.sync_now(message=message)
    else:
        result = await sync.sync_if_dirty(message=message)

    print(f"\n🌕 Moon Auto-Sync")
    print(f"  success:   {result.success}")
    print(f"  committed: {result.committed}")
    print(f"  pushed:    {result.pushed}")
    print(f"  SHA:       {result.commit_sha or 'N/A'}")
    print(f"  message:   {result.message}")
    print(f"  files:     {len(result.files_changed)}")
    if result.files_changed:
        for f in result.files_changed[:10]:
            print(f"    {f}")
        if len(result.files_changed) > 10:
            print(f"    ... +{len(result.files_changed)-10} mais")
    if result.error:
        print(f"  ❌ erro: {result.error}")
    else:
        if result.committed:
            print(f"\n✅ Push realizado com sucesso")
        else:
            print(f"\nℹ️ {result.message}")


if __name__ == "__main__":
    asyncio.run(main())
