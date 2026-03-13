# CLAUDE.md - Projeto Jarvis/Super-Agente

> Documento vivo de especificação. Atualizado continuamente.
> Este arquivo é lido pelo agente de IA antes de cada interação.

---

## 1. Visão Geral do Projeto

**Nome:** Jarvis / Super-Agente  
**Stack:** Python, Supabase, LLMs (Groq, OpenAI, Anthropic)  
**Tipo:** Ecossistema de agentes de IA para automação e produtividade  
**Objetivo:** Assistente pessoal com múltiplas capacidades de IA

---

## 2. Estrutura de Diretórios

```
The Moon/
├── .github/workflows/              # CI/CD (GitHub Actions)
│   └── ci.yml                     # Pipeline de integração contínua
├── ai-jail/                       # Sandbox para agentes de IA
│   ├── ai_jail.py                # Implementação do jail
│   └── README.md                  # Documentação
├── tests/                         # Testes (TDD)
│   ├── unit/                     # Testes unitários
│   ├── integration/              # Testes de integração
│   ├── fixtures/                 # Fixtures pytest
│   └── conftest.py              # Configuração pytest
├── docs/                          # Documentação do projeto
│   ├── docker-installation-guide.md
│   ├── obsidian-setup-guide.md
│   └── system_enhancements.md
├── infrastructure/                # Infraestrutura Docker
│   ├── docker-compose.yml
│   ├── .env
│   ├── .env.example
│   └── install-docker.sh
├── Super-Agente/                  # Agentes e ferramentas principais
│   ├── antigravity-kit/           # Kit com 20+ agentes especializados
│   │   ├── .agent/                # Configurações de agentes
│   │   │   ├── ARCHITECTURE.md
│   │   │   └── workflows/
│   │   └── CHANGELOG.md
│   ├── docs/
│   │   └── SUPER-AGENTE-DOCUMENT│   ├── groq-models/               # Modelos Groq
│   │   ├──ACAO.md
 groq_llm.py
│   │   └── README.md
│   ├── mcp-servers/               # MCP Servers (Playwright)
│   │   └── playwright-mcp/
│   └── skills/                    # Skills do agente
│       ├── anthropics-skills/
│       └── interface-design/
├── requirements.txt               # Dependências Python
├── requirements-dev.txt           # Dependências de desenvolvimento
├── pyproject.toml                # Configuração pytest + coverage
├── tdd.py                        # CLI para workflow TDD
├── install_docker.sh              # Script de instalação
└── CLAUDE.md                      # Este arquivo
```

---

## 3. Stack Tecnológico

### Linguagens
- **Python 3.11+** - Linguagem principal
- **JavaScript/TypeScript** - MCP servers e extensões

### Frameworks & Bibliotecas
- **Supabase** - Backend as a Service (PostgreSQL + Auth + Realtime)
- **Groq** - LLM Inference
- **Anthropic (Claude)** - LLM
- **OpenAI** - LLM
- **Playwright** - Automação de navegador
- **Docker** - Containerização
- **n8n** - Automação de workflows (futuro)

### Infraestrutura Local
- **Supabase local** - PostgreSQL na porta 54321
- **Redis** - Cache na porta 6379
- **Ollama** - LLMs offline na porta 11434
- **OpenWebUI** - Interface web na porta 8080

---

## 4. Variáveis de Ambiente

```env
# Supabase
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=<sua-chave>
SUPABASE_SERVICE_KEY=<sua-chave>

# LLMs
GROQ_API_KEY=<sua-chave>
OPENAI_API_KEY=<sua-chave>
ANTHROPIC_API_KEY=<sua-chave>

# Discord (futuro)
DISCORD_BOT_TOKEN=<seu-token>

# OpenWebUI
OPENWEBUI_API_KEY=<sua-chave>
```

---

## 5. Common Hurdles (Problemas Comuns)

### 5.1 Docker
- **Problema:** Docker Desktop não inicia no Windows WSL2
- **Solução:** Verificar se WSL2 está instalado: `wsl --update`

### 5.2 Supabase Local
- **Problema:** Container não inicia
- **Solução:** Verificar se portas 54321, 54322 estão livres

### 5.3 Groq API
- **Problema:** Rate limiting
- **Solução:** Implementar retry com exponential backoff

### 5.4 Playwright MCP
- **Problema:** Browser não inicia em ambiente headless
- **Solução:** Verificar dependências: `npx playwright install`

### 5.5 Ollama
- **Problema:** Modelos não carregam
- **Solução:** Verificar memória disponível (mínimo 8GB RAM)

---

## 6. Design Patterns

### 6.1 Agent Pattern
- Usar `Orchestrator` para coordenar múltiplos agentes
- Cada agente tem responsabilidade única
- Comunicação via mensagens estruturadas

### 6.2 MCP (Model Context Protocol)
- Servidores MCP para ferramentas externas
- Playwright para automação web
- Futuros: filesystem, git, docker MCPs

### 6.3 RAG (Retrieval Augmented Generation)
- Embeddings para busca semântica
- Qdrant/ChromaDB para vector storage
- Contexto aumentado para respostas

### 6.4 Event-Driven
- Webhooks para eventos externos
- Jobs assíncronos para tarefas longas
- Realtime updates via Supabase

---

## 7. Pipeline de Desenvolvimento

### Ciclo Semanal (Baseado no Método Akita)
1. **Segunda** - Feature development
2. **Terça** - Feature + Tests
3. **Quarta** - CI/CD + Refactoring
4. **Quinta** - Security + Performance
5. **Sexta** - Deploy + Review

### Processo de Feature (TDD)
1. Criar teste: `python tdd.py new nome_feature`
2. Executar teste (ver falhar): `python tdd.py test`
3. Implementar código mínimo
4. Executar teste (ver passar)
5. Refatorar
6. CI: `python tdd.py ci`
7. Commit

### Comandos TDD
| Comando | Descrição |
|---------|-----------|
| `python tdd.py new <nome>` | Criar novo teste |
| `python tdd.py test` | Executar testes |
| `python tdd.py test -w` | Executar em watch mode |
| `python tdd.py cov` | Executar com coverage |
| `python tdd.py lint` | Executar linting |
| `python tdd.py ci` | Executar CI completo |

### AI Jail (Sandbox)
Para executar código gerado por IA com segurança:
```python
from ai_jail import create_safe_jail

with create_safe_jail() as jail:
    result = jail.execute_python(code)
```

---

## 8. Checklist Pós-Implementação

Para cada nova feature:

- [ ] Testes unitários adicionados
- [ ] Testes de integração (se aplicável)
- [ ] Linting passou (`ruff check .`)
- [ ] Type checking passou (`ruff check --select I`)
- [ ] Documentação atualizada
- [ ] Variáveis de ambiente adicionadas ao .env.example
- [ ] Docker Compose atualizado (se necessário)

---

## 9. Quality Assurance

### Testes
- **Frameworks:** pytest
- **Cobertura mínima:** 80%
- **Tipos:** unit, integration, e2e

### Segurança
- **Linting:** ruff
- **Audit:** pip-audit, safety
- **Secrets:** Nunca commitar .env

### CI/CD
- **GitHub Actions** em cada commit
- **Validações:** lint, test, security audit
- **Deploy:** Automático após merge em main

---

## 10. Referências

- [AkitaOnRails - Do Zero à Pós-Produção](https://akitaonrails.com/2026/02/20/do-zero-a-pos-producao-em-1-semana-como-usar-ia-em-projetos-de-verdade-bastidores-do-the-m-akita-chronicles/)
- [CLAUDE.md Original](https://docs.anthropic.com/en/docs/claude-code/claude-md)
- [Super-Agente Documentação](Super-Agente/docs/SUPER-AGENTE-DOCUMENTACAO.md)

---

*Última atualização: 2026-03-11*
*Este documento evolui com o projeto.*
