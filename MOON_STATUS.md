# 🌕 The Moon Ecosystem — Status

> Atualizado automaticamente via AutoSyncService

**Última atualização:** 2026-03-16 15:47 (UTC-3)
**GitHub:** https://github.com/newjsouza/the-moon-ecosystem.git
**Python:** Python 3.12.3 | **Node:** v22.14.0

---

## 🏗️ Arquitetura

| Camada | Arquivos |
|---|---|
| `agents/` | 41 arquivos Python |
| `core/` | 28 arquivos Python |
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
CLI: LibreOffice, Mermaid, libreoffice, mermaid
```

## 🛠️ CLI-Anything Stack

| Harness | Status |
|---|---|
| cli-anything-libreoffice | ✅ Instalado |
| cli-anything-mermaid | ✅ Instalado |
| cli-anything-obs-studio | ❌ Skip (sudo) |
| cli-anything-drawio | ❌ Skip (sudo) |
| cli-anything-kdenlive | ❌ Skip (sudo) |


**Harnesses gerados (Opção A):** 0
**Exports em disco:** `data/blog_exports/`

## 🔄 Auto-Sync GitHub

- **AutoSyncService**: `core/services/auto_sync.py`
- **Orchestrator hook**: `_post_execution_sync()` após cada execução
- **Watchdog periódico**: sync a cada 30 minutos
- **Manual**: `python3 moon_sync.py "mensagem"`

## 🧪 Testes

```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
SKIPPED [1] tests/test_moon_browser_agent.py:328: Requer daemon rodando
```

## 📋 Commits Recentes

```
48bd2f1 feat: GitHub auto-sync implementation — AutoSyncService + Orchestrator hook + Watchdog periodic sync
d9ea9e6 fix(tests): correções para isolamento de ambiente e testes de secrets
94353ab docs(codex): registrar sessão de implementação e auditoria final — 72/72 testes
a624f0f feat: implementação completa — secrets, fallbacks, testes, architect bootstrap
c9c9461 docs: update MOON_CODEX with Sessão Antigravity log + update .gitignore
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
