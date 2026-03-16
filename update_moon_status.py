"""
update_moon_status.py — Gera MOON_STATUS.md para Perplexity Space
"""
from pathlib import Path
from datetime import datetime
import subprocess
import json


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return r.stdout.strip()


def generate_status():
    git_log = run("git log --oneline -5")
    git_remote = run("git remote get-url origin 2>/dev/null")
    python_version = run("python3 --version")
    node_version = run("node --version 2>/dev/null") or "N/A"
    tests_result = run("python3 -m pytest tests/ --ignore=tests/pending/ --tb=no -q 2>&1 | tail -3")

    try:
        reg = json.loads(Path("skills/cli_harnesses/installed_harnesses.json").read_text())
        installed = [h["name"] for h in reg["harnesses"] if h.get("installed")]
        skipped = [h["name"] for h in reg["harnesses"] if h.get("skipped")]
    except Exception:
        installed, skipped = [], []

    try:
        gen_dir = Path("skills/cli_harnesses/generated")
        generated_count = len(list(gen_dir.glob("*.py"))) if gen_dir.exists() else 0
    except Exception:
        generated_count = 0

    agents_files = list(Path("agents").rglob("*.py"))
    core_files = list(Path("core").rglob("*.py"))

    installed_row = "".join(f"| cli-anything-{h} | ✅ Instalado |\n" for h in installed) if installed else "| (nenhum) | - |\n"
    skipped_row = "".join(f"| cli-anything-{h} | ❌ Skip (sudo) |\n" for h in skipped) if skipped else ""

    status_content = f"""# 🌕 The Moon Ecosystem — Status

> Atualizado automaticamente via AutoSyncService

**Última atualização:** {datetime.now().strftime("%Y-%m-%d %H:%M")} (UTC-3)
**GitHub:** {git_remote}
**Python:** {python_version} | **Node:** {node_version}

---

## 🏗️ Arquitetura

| Camada | Arquivos |
|---|---|
| `agents/` | {len(agents_files)} arquivos Python |
| `core/` | {len(core_files)} arquivos Python |
| `skills/` | github, gmail, sports, supabase, voice, moon_browse, cli_harnesses |
| `tests/` | suite pytest |

## 🤖 Agentes Principais

- **ArchitectAgent** — roteamento central com DOMAIN_AGENT_MAP (20+ domínios)
- **SkillAlchemist** — auto-discovery de skills via GitHub/PyPI/HuggingFace
- **NexusIntelligence** — pesquisa e análise
- **OmniChannelStrategist** — estratégia multicanal
- **MoonCLIAgent** ✅ — executa e gera CLI harnesses (6 ações)
- **Moon-Stack** — browser, plan, qa, review, ship
- **Blog agents** — writer, manager, publisher, direct_writer
- **WatchDog** — monitoramento + sync periódico 30min

## 🔌 Integrações Ativas

```
LLMRouter: Groq (llama-3.3-70b) → Gemini → OpenRouter
APIs: Football-Data, GitHub, Telegram, Gmail
CLI: LibreOffice, Mermaid, {', '.join(installed) if installed else 'ver registry'}
```

## 🛠️ CLI-Anything Stack

| Harness | Status |
|---|---|
{installed_row}{skipped_row}

**Harnesses gerados (Opção A):** {generated_count}
**Exports em disco:** `data/blog_exports/`

## 🔄 Auto-Sync GitHub

- **AutoSyncService**: `core/services/auto_sync.py`
- **Orchestrator hook**: `_post_execution_sync()` após cada execução
- **Watchdog periódico**: sync a cada 30 minutos
- **Manual**: `python3 moon_sync.py "mensagem"`

## 🧪 Testes

```
{tests_result}
```

## 📋 Commits Recentes

```
{git_log}
```

## ⚠️ Pendências Abertas

- OBS Studio harness (requer `sudo apt install obs-studio`)
- ffmpeg, pandoc, imagemagick não disponíveis no sistema
- Harness generate do MoonCLIAgent requer prompt tuning

---

## 🚀 Comandos de Referência

```bash
# Estado do sistema
python3 moon_sync.py --status
python3 -m pytest tests/ --ignore=tests/pending/ --tb=no -q | tail -5

# Usar CLI Agent
python3 -c "import asyncio; from agents.moon_cli_agent import MoonCLIAgent; asyncio.run(MoonCLIAgent()._execute('list'))"

# Blog export
python3 -c "from skills.cli_harnesses.blog_cli_exporter import BlogCLIExporter; print(BlogCLIExporter().capabilities())"

# Sync manual
python3 moon_sync.py "feat: descrição do que foi implementado"
```

## 🧠 Para o Perplexity Space

**Protocolo de início de sessão:**
```bash
python3 moon_sync.py --status
python3 -m pytest tests/ --ignore=tests/pending/ --tb=no -q | tail -5
tail -20 MOON_CODEX.md
git log --oneline -5
```
Cole os 4 outputs acima no Space para retomar com contexto completo.

**Assinaturas críticas (sempre usar estas):**
```python
async def _execute(self, task: str, **kwargs) -> TaskResult
TaskResult(success, data=None, error=None, execution_time=0.0)
await bus.publish(sender, topic, payload, target=None)
await llm.complete(prompt, task_type="general", **kwargs)
```
"""

    status_path = Path("MOON_STATUS.md")
    status_path.write_text(status_content, encoding="utf-8")
    lines = len(status_content.splitlines())
    print(f"✅ MOON_STATUS.md criado: {lines} linhas")
    print(f"   Path: {status_path.resolve()}")
    return status_path


if __name__ == "__main__":
    generate_status()
