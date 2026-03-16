# 🌕 Moon-Stack Implementation Guide — Fases Restantes

## Status Atual (✅ = Completo, ⏳ = Pendente)

- ✅ FASE 1: Moon Browser Daemon (skills/moon_browse/, core/browser_bridge.py, agents/moon_browser_agent.py)
- ✅ FASE 2: Moon Plan Agent (agents/moon_plan_agent.py)
- ⏳ FASE 3: Moon Review Agent (AST + LLM)
- ⏳ FASE 4: Moon QA Agent (QA visual via browser)
- ⏳ FASE 5: Moon Ship Agent (pipeline de release)
- ⏳ FASE 6: Integração ao ecossistema
- ⏳ FASE 7: Cookie import para Linux
- ⏳ FASE 8: Atualização do MOON_CODEX.md
- ⏳ FASE 9: Validação end-to-end

---

## 📝 Instruções para Completar

### FASE 3: Moon Review Agent

Criar `agents/moon_review_agent.py` com:

```python
"""
agents/moon_review_agent.py
Moon Review Agent — Revisão paranóica de código (AST + LLM)

Pipeline:
  1. Obtém diff: git diff main --unified=5 -- "*.py"
  2. Análise AST (determinística):
     - async sem await
     - variáveis não inicializadas
     - imports não utilizados
     - funções > 50 linhas
     - strings com modelos proibidos (gpt-4, claude)
  3. Análise LLM (semântica):
     - Race conditions
     - Trust boundaries
     - N+1 em loops
     - Error handling faltando
  4. Gera JSON em data/reviews/{timestamp}_review.json
  5. Publica em "review.completed" e "watchdog.alert" (se crítico)
"""
```

**Estrutura básica:**
```python
from core.agent_base import AgentBase, AgentPriority, TaskResult
from agents.llm import LLMRouter
import ast
import subprocess

REVIEW_PROMPT = """Você é um engenheiro sênior fazendo code review paranóico..."""

class MoonReviewAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.name = "MoonReviewAgent"
        self.priority = AgentPriority.NORMAL
        self.description = "Paranoid code review agent (AST + LLM)"
    
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        # 1. Obter diff
        # 2. Análise AST
        # 3. Análise LLM
        # 4. Gerar relatório JSON
        # 5. Publicar na MessageBus
        pass
    
    def _analyze_ast(self, code: str) -> list:
        # Detecta problemas com módulo ast
        pass
```

---

### FASE 4: Moon QA Agent

Criar `agents/moon_qa_agent.py`:

```python
"""
agents/moon_qa_agent.py
Moon QA Agent — QA visual autônomo via browser

Pipeline:
  1. git diff --name-only → identifica rotas afetadas
  2. Verifica apps rodando (portas 3000, 8080, etc.)
  3. Para cada app online:
     - goto(url)
     - screenshot()
     - console()
     - snapshot()
     - Navega por links internos
  4. Análise visual via LLM (Gemini multimodal se disponível)
  5. Gera JSON em data/qa_reports/{timestamp}_qa_report.json
  6. Publica em "qa.report_generated" e "nexus.event"
"""
```

**Depende de:** MoonBrowserAgent

---

### FASE 5: Moon Ship Agent

Criar `agents/moon_ship_agent.py`:

```python
"""
agents/moon_ship_agent.py
Moon Ship Agent — Pipeline completo de release

Pipeline:
  1. Pre-flight check:
     - git status --porcelain (mudanças não commitadas?)
     - pytest tests/ -x -q (testes passam?)
  2. Review automático (MoonReviewAgent)
     - Se health_score < 70, aguarda confirmação
  3. Sync com main (git fetch + rebase)
  4. Gera changelog entry via LLM
  5. Push e PR (GithubAgent)
  6. Notifica (MessageBus + Telegram se configurado)
"""
```

**Depende de:** MoonReviewAgent, GithubAgent

---

### FASE 6: Integração

**6A — Registrar no ArchitectAgent:**
Editar `agents/architect.py` e adicionar mapeamento:
```python
"plan" | "ceo" | "produto" → MoonPlanAgent (mode:ceo)
"eng" | "arquitetura" → MoonPlanAgent (mode:eng)
"review" | "code review" → MoonReviewAgent
"qa" | "teste" → MoonQAAgent
"ship" | "deploy" → MoonShipAgent
"browse" | "navegar" → MoonBrowserAgent
```

**6B — Registrar no AutonomousLoop:**
Editar `core/autonomous_loop.py` e adicionar MoonQAAgent como tarefa periódica (6h).

**6C — Registrar no SkillAlchemist:**
Editar `agents/skill_alchemist.py` e adicionar keywords: "playwright", "browser-use", "browserbase".

**6D — Registrar no SemanticMemoryWeaver:**
Editar `agents/semantic_memory_weaver.py` e subscrever em:
- "review.completed"
- "qa.report_generated"

---

### FASE 7: Cookie Import para Linux

Implementar em `agents/moon_browser_agent.py`:

```python
def _import_cookies_linux(self, domain: str) -> list:
    """
    Importa cookies do Chrome/Chromium no Linux via secretstorage.
    
    1. Localiza banco de cookies:
       - ~/.config/google-chrome/Default/Cookies
       - ~/.config/chromium/Default/Cookies
       - ~/.config/brave-browser/Default/Cookies
    2. Copia para /tmp (evita lock)
    3. Descriptografa via GNOME Keyring (secretstorage)
    4. Consulta SQLite para o domínio
    5. Retorna lista compatível com Playwright
    """
    import secretstorage
    import sqlite3
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Cipher import AES
    from Crypto.Hash import SHA1
    
    # Implementação completa conforme especificação
    pass
```

**Dependências:** `pip install secretstorage pycryptodome`

---

### FASE 8: Atualizar MOON_CODEX.md

Adicionar na Seção 5 (Catálogo):
```markdown
| agents/moon_browser_agent.py | Moon Browser: Daemon Playwright + bridge HTTP | ✅ Operante |
| agents/moon_plan_agent.py | Moon Plan: Modos CEO/Eng via LLM | ✅ Operante |
| agents/moon_review_agent.py | Moon Review: Code review (AST + LLM) | ⏳ Em implementação |
| agents/moon_qa_agent.py | Moon QA: QA visual autônomo | ⏳ Em implementação |
| agents/moon_ship_agent.py | Moon Ship: Pipeline de release | ⏳ Em implementação |
| skills/moon_browse/ | Daemon Playwright (TypeScript/Bun) | ✅ Operante |
```

Adicionar na Seção 8 (Enciclopédia):
```markdown
### 📂 Assunto: [Moon-Stack — Integração gstack sem Claude Code]
- **Tópico:** Browser automation, QA visual, modos cognitivos
- **Resumo:** Daemon Playwright do gstack (MIT) + bridge Python + 5 agentes
  (Browser, Plan, Review, QA, Ship). Cookie import via secretstorage.
  100% Groq/Gemini free tier.
- **Data:** 16 Março 2026.
```

---

### FASE 9: Validação End-to-End

Executar script de validação:

```bash
cd "/home/johnathan/Área de trabalho/The Moon"

# 1. Testar daemon
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
bash skills/moon_browse/start_daemon.sh &
sleep 3
cat .gstack/browse.json  # Deve mostrar port e token

# 2. Testar bridge Python
python3 -c "
import asyncio
from core.browser_bridge import BrowserBridge

async def test():
    bridge = BrowserBridge()
    result = await bridge.goto('https://httpbin.org/get')
    print(f'goto: {result}')
    snap = await bridge.snapshot()
    print(f'snapshot: {len(snap)} chars')

asyncio.run(test())
"

# 3. Testar agentes
python3 -m pytest tests/test_moon_browser_agent.py -v

# 4. Teste completo (após todas as fases)
python3 -c "
import asyncio
from agents.moon_browser_agent import MoonBrowserAgent
from agents.moon_plan_agent import MoonPlanAgent

async def test_all():
    browser = MoonBrowserAgent()
    await browser.initialize()
    result = await browser.execute('goto https://example.com')
    print(f'Browser: {result.success}')
    
    plan = MoonPlanAgent()
    await plan.initialize()
    result = await plan.execute('ceo Testar análise estratégica')
    print(f'Plan: {result.success}')

asyncio.run(test_all())
"
```

---

## 🎯 Próximos Passos Imediatos

1. **Executar testes da FASE 1:**
   ```bash
   python3 -m pytest tests/test_moon_browser_agent.py -v
   ```

2. **Testar daemon manualmente:**
   ```bash
   export BUN_INSTALL="$HOME/.bun"
   export PATH="$BUN_INSTALL/bin:$PATH"
   bash skills/moon_browse/start_daemon.sh
   ```

3. **Implementar FASE 3 (Review Agent):**
   - Seguir template acima
   - Criar `tests/test_moon_review_agent.py`

4. **Implementar FASE 4-7** conforme templates

5. **Atualizar MOON_CODEX.md**

6. **Executar validação completa**

---

## 📊 Métricas de Sucesso

- ✅ 11 testes passando (FASE 1)
- ✅ Daemon iniciando e respondendo
- ✅ Bridge Python conectando ao daemon
- ⏳ Review Agent detectando problemas AST
- ⏳ QA Agent navegando e tirando screenshots
- ⏳ Ship Agent criando PRs automaticamente
- ⏳ Cobertura ≥75% em todos os agentes

---

*Documento gerado automaticamente — Moon-Stack Implementation em andamento*
