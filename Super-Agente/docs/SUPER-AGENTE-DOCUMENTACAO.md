# SUPER AGENTE - Documentação Completa

## Visão Geral

Este documento detalha todos os agentes, skills e ferramentas instalados no Super Agente para ajudá-lo em diversas áreas: codificação, criação de sites, bots de mensagem, organização pessoal, software para negócios, leis, desenvolvimento pessoal (físico, emocional e espiritual), planejamento e criação de novos projetos.

---

## 1. ANTIGRAVITY KIT

**Localização:** `Super-Agente/antigravity-kit/`

**Descrição:** Kit completo com 20 agentes especializados, 37 skills de domínio específico e 11 workflows (slash commands).

### 1.1 AGENTES (20)

| Agente | Descrição |
|--------|-----------|
| **backend-specialist** | Especialista em desenvolvimento backend, APIs, servers, databases |
| **frontend-specialist** | Especialista em interfaces de usuário, CSS, frameworks frontend |
| **security-auditor** | Auditor de segurança, análise de vulnerabilidades, best practices |
| **debugger** | Diagnóstico e resolução de bugs sistemática |
| **code-archaeologist** | Análise de código legado, documentação, compreensão de sistemas antigos |
| **database-architect** | Design de banco de dados, schemas, otimização |
| **devops-engineer** | Pipeline CI/CD, deployment, infraestrutura |
| **documentation-writer** | Criação de documentação técnica |
| **explorer-agent** | Exploração de códigobases, descoberta de padrões |
| **game-developer** | Desenvolvimento de jogos |
| **mobile-developer** | Desenvolvimento mobile (iOS, Android) |
| **orchestrator** | Coordenação de múltiplos agentes |
| **penetration-tester** | Testes de penetração, ethical hacking |
| **performance-optimizer** | Otimização de performance, profiling |
| **product-manager** | Gestão de produto, roadmap, priorização |
| **product-owner** | Ownership de produto, backlog management |
| **project-planner** | Planejamento de projetos, tarefas |
| **qa-automation-engineer** | Automação de testes QA |
| **seo-specialist** | Otimização para motores de busca |
| **test-engineer** | Engenharia de testes |

### 1.2 SKILLS (37)

| Skill | Descrição |
|-------|-----------|
| **api-patterns** | Padrões de design de APIs REST/GraphQL |
| **app-builder** | Construção de aplicações completas |
| **architecture** | Princípios de arquitetura de software |
| **bash-linux** | Comandos bash e administração Linux |
| **behavioral-modes** | Modos de comportamento do agente |
| **brainstorming** | Técnicas de brainstorming |
| **clean-code** | Princípios de código limpo |
| **code-review-checklist** | Checklist para code reviews |
| **database-design** | Design de banco de dados |
| **deployment-procedures** | Procedimentos de deployment |
| **documentation-templates** | Templates de documentação |
| **frontend-design** | Design de interfaces frontend |
| **game-development** | Desenvolvimento de jogos |
| **geo-fundamentals** | Fundamentos de geolocalização |
| **i18n-localization** | Internacionalização e localização |
| **intelligent-routing** | Roteamento inteligente |
| **lint-and-validate** | Linting e validação de código |
| **mcp-builder** | Construção de servidores MCP |
| **mobile-design** | Design de interfaces mobile |
| **nextjs-react-expert** | Expertise em Next.js e React |
| **nodejs-best-practices** | Melhores práticas Node.js |
| **parallel-agents** | Coordenação de agentes paralelos |
| **performance-profiling** | Profiling de performance |
| **plan-writing** | Escrita de planos de projeto |
| **powershell-windows** | PowerShell para Windows |
| **python-patterns** | Padrões de programação Python |
| **red-team-tactics** | Táticas de red team |
| **rust-pro** | Programação em Rust |
| **seo-fundamentals** | Fundamentos de SEO |
| **server-management** | Gestão de servidores |
| **systematic-debugging** | Debugging sistemático |
| **tailwind-patterns** | Padrões Tailwind CSS |
| **tdd-workflow** | Workflow Test-Driven Development |
| **testing-patterns** | Padrões de testes |
| **vulnerability-scanner** | Scanner de vulnerabilidades |
| **webapp-testing** | Testes de aplicações web |
| **web-design-guidelines** | Guidelines de design web |

### 1.3 WORKFLOWS (11)

| Comando | Descrição |
|---------|-----------|
| `/brainstorm` | Explorar opções antes de implementação |
| `/create` | Criar novas features ou apps |
| `/debug` | Debugging sistemático |
| `/deploy` | Fazer deploy de aplicação |
| `/enhance` | Melhorar código existente |
| `/orchestrate` | Coordenação multi-agente |
| `/plan` | Criar breakdown de tarefas |
| `/preview` | Visualizar mudanças localmente |
| `/status` | Verificar status do projeto |
| `/test` | Gerar e executar testes |
| `/ui-ux-pro-max` | Design com 50 estilos |

### Instalação (requer Node.js)

```bash
npm install -g @vudovn/ag-kit
ag-kit init
```

---

## 2. ANTHROPICS SKILLS

**Localização:** `Super-Agente/skills/anthropics-skills/`

**Descrição:** Skills oficiais da Anthropic para manipulação de documentos e tarefas técnicas.

### 2.1 SKILLS DISPONÍVEIS

| Skill | Descrição |
|-------|-----------|
| **algorithmic-art** | Criação de arte algorítmica |
| **brand-guidelines** | Guidelines de marca |
| **canvas-design** | Design de canvas |
| **claude-api** | Uso da API da Anthropic |
| **doc-coauthoring** | Co-autoria de documentos |
| **docx** | Criação e edição de documentos Word |
| **frontend-design** | Design de interfaces frontend |
| **internal-comms** | Comunicações internas |
| **mcp-builder** | Construção de servidores MCP |
| **pdf** | Criação e edição de PDFs |
| **pptx** | Criação de apresentações PowerPoint |
| **skill-creator** | Criação de skills personalizados |
| **slack-gif-creator** | Criação de GIFs para Slack |
| **theme-factory** | Criação de temas |
| **webapp-testing** | Testes de aplicações web |
| **web-artifacts-builder** | Construção de artefatos web |
| **xlsx** | Criação e edição de planilhas Excel |

### Instalação (Claude Code)

```bash
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills
/plugin install example-skills@anthropic-agent-skills
```

---

## 3. FIRECRAWL CLI

**Localização:** Baixado via npm (requer Node.js)

**Descrição:** CLI para web scraping, crawling e automação de navegador.

### 3.1 COMANDOS PRINCIPAIS

| Comando | Descrição |
|---------|-----------|
| `firecrawl scrape <url>` | Extrai conteúdo de uma URL |
| `firecrawl search <query>` | Pesquisa na web |
| `firecrawl map <url>` | Descobre todas URLs de um site |
| `firecrawl crawl <url>` | Crawl completo de website |
| `firecrawl browser` | Sessão de browser na nuvem |
| `firecrawl agent` | Agente de pesquisa web |

### 3.2 OPÇÕES DE SCRAPE

| Opção | Descrição |
|-------|-----------|
| `--format markdown,html,links` | Formato de saída |
| `--only-main-content` | Extrai só conteúdo principal |
| `--wait-for <ms>` | Espera JavaScript renderizar |
| `--screenshot` | Tira screenshot |
| `-o <file>` | Salva em arquivo |

### 3.3 AUTENTICAÇÃO

```bash
firecrawl login --api-key fc-SUA-CHAVE
# ou
export FIRECRAWL_API_KEY=fc-SUA-CHAVE
```

### Instalação (requer Node.js)

```bash
npm install -g firecrawl-cli
# ou
npx -y firecrawl-cli@latest init --all --browser
```

---

## 4. NAPKIN

**Localização:** `Super-Agente/skills/napkin/`

**Descrição:** Skill para memória persistente de erros e aprendizados.

### 4.1 FUNCIONALIDADES

- **Memória persistente**: Mantém um arquivo `.claude/napkin.md` por repositório
- **Curadoria contínua**: Atualiza a cada sessão
- **Registro de erros**: O agente registra seus próprios erros e correções
- **Padrões aprendidos**: Guarda preferências do usuário
- **Melhoria progressiva**: A cada sessão 3-5, o comportamento melhora significativamente

### 4.2 O QUE É REGISTRADO

- Erros do agente (más suposições, abordagens ruins)
- Correções do usuário
- Surpresas do ambiente/repositório
- Preferências do usuário
- O que funcionou bem

### Instalação (Claude Code)

```bash
git clone https://github.com/blader/napkin.git ~/.claude/skills/napkin
```

---

## 5. INTERFACE DESIGN

**Localização:** `Super-Agente/skills/interface-design/`

**Descrição:** Design engineering para Claude Code. Craft, memory e enforcement para UI consistente.

### 5.1 FUNCIONALIDADES

- **Craft**: Design principle-based que produz interfaces profissionais
- **Memory**: Salva decisões em `.interface-design/system.md`
- **Consistency**: Cada componente segue os mesmos princípios

### 5.2 DIREÇÕES DE DESIGN

| Direção | Sensação | Melhor Para |
|---------|----------|-------------|
| **Precision & Density** | Tight, technical, monochrome | Developer tools, admin dashboards |
| **Warmth & Approachability** | Generous spacing, soft shadows | Collaborative tools, consumer apps |
| **Sophistication & Trust** | Cool tones, layered depth | Finance, enterprise B2B |
| **Boldness & Clarity** | High contrast, dramatic space | Modern dashboards |
| **Utility & Function** | Muted, functional density | GitHub-style tools |
| **Data & Analysis** | Chart-optimized, numbers-first | Analytics, BI tools |

### 5.3 COMANDOS

| Comando | Descrição |
|---------|-----------|
| `/interface-design:init` | Iniciar com princípios de design |
| `/interface-design:status` | Mostrar sistema atual |
| `/interface-design:audit <path>` | Verificar código contra sistema |
| `/interface-design:extract` | Extrair padrões de código existente |

### Instalação (Claude Code)

```bash
/plugin marketplace add Dammyjay93/interface-design
/plugin menu
# Selecionar interface-design
```

---

## 6. PLAYWRIGHT MCP

**Localização:** `Super-Agente/mcp-servers/playwright-mcp/`

**Descrição:** Servidor MCP para automação de navegador via Playwright.

### 6.1 FERRAMENTAS DISPONÍVEIS

**Automação Core**

| Ferramenta | Descrição |
|------------|-----------|
| `browser_navigate` | Navegar para URL |
| `browser_click` | Clicar em elemento |
| `browser_type` | Digitar em campo |
| `browser_snapshot` | Capturar snapshot de acessibilidade |
| `browser_screenshot` | Tirar screenshot |
| `browser_hover` | Hover em elemento |
| `browser_select_option` | Selecionar opção em dropdown |
| `browser_fill_form` | Preencher formulário |
| `browser_evaluate` | Executar JavaScript |
| `browser_navigate_back` | Voltar no histórico |
| `browser_console_messages` | Obter mensagens do console |
| `browser_network_requests` | Listar requests de rede |

**Gerenciamento de Abas**

| Ferramenta | Descrição |
|------------|-----------|
| `browser_tabs` | Listar, criar, fechar abas |

**Mouse Coordinate-based**

| Ferramenta | Descrição |
|------------|-----------|
| `browser_mouse_click_xy` | Clicar em coordenadas |
| `browser_mouse_move_xy` | Mover mouse para coordenadas |
| `browser_mouse_drag_xy` | Arrastar mouse |
| `browser_mouse_wheel` | Scroll |

### 6.2 CONFIGURAÇÃO

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
```

### 6.3 OPÇÕES AVANÇADAS

| Opção | Descrição |
|-------|-----------|
| `--browser chrome/firefox/webkit` | Browser a usar |
| `--headless` | Executar sem interface |
| `--viewport-size` | Tamanho da janela |
| `--device` | Emular dispositivo |
| `--save-trace` | Salvar trace do Playwright |
| `--storage-state` | Estado inicial do browser |

### Instalação (requer Node.js)

```bash
npm install -g @playwright/mcp
# ou
npx @playwright/mcp@latest
```

---

## RESUMO TOTAL

| Categoria | Quantidade | Detalhes |
|-----------|------------|----------|
| **Agentes** | 20 | Especialistas em backend, frontend, security, QA, etc |
| **Skills Antigravity** | 37 | Domínios específicos (API, database, TDD, etc) |
| **Workflows** | 11 | Slash commands (/brainstorm, /create, /debug, etc) |
| **Skills Anthropics** | 17 | Documentos (PDF, DOCX, XLSX), arte, testing |
| **Ferramentas MCP** | ~30+ | Automação de navegador completa |
| **Skills Memória** | 2 | Napkin + Interface Design |

---

## PRÓXIMOS PASSOS

1. **Instalar Node.js** para ativar todas as funcionalidades
2. **Configurar ambiente** com as chaves de API necessárias
3. **Instalar dependências** dos pacotes npm
4. **Configurar MCP servers** no seu editor/ferramenta

---

*Documento gerado automaticamente em: 2026-03-11*
