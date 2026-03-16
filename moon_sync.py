"""
moon_sync.py — Script de sync manual para uso no terminal.

Uso:
  python3 moon_sync.py                        # sync se houver mudanças
  python3 moon_sync.py "feat: minha feature"  # sync com mensagem custom
  python3 moon_sync.py --status               # ver status sem commitar
  python3 moon_sync.py --force                # forçar commit mesmo sem mudanças
"""

import asyncio
import sys
from pathlib import Path

# Adicionar projeto ao path
sys.path.insert(0, str(Path(__file__).parent))


async def main():
    from core.services.auto_sync import get_auto_sync

    args = sys.argv[1:]
    sync = get_auto_sync()

    # --status: apenas mostrar estado
    if "--status" in args:
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
    message = next((a for a in args if not a.startswith("--")), None)
    force = "--force" in args

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
