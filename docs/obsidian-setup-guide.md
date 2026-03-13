# 📚 Guia de Configuração - Obsidian como Second Brain do Projeto

## Visão Geral
O Obsidian funcionará como interface visual para o **Protocol Synapse**, permitindo navegação, busca e edição do histórico de contexto e memória do projeto.

## Estrutura do Projeto

```
/home/johnathan/Área de trabalho/The Moon/
├── Super-Agente/
│   ├── agents/
│   ├── antigravity-kit/
│   │   └── .agent/         # Agente principal
│   │       ├── .shared/
│   │       ├── scripts/
│   │       ├── skills/
│   │       └── ARCHITECTURE.md
│   ├── docs/
│   ├── groq-models/
│   ├── mcp-servers/
│   └── skills/
├── infrastructure/          # Docker configs
└── docs/                   # Documentação do sistema
```

---

## Instalação

### Linux (via AppImage ou pacote)
```bash
# Método 1: AppImage (recomendado)
cd ~/Downloads
wget https://github.com/obsidianmd/obsidian-releases/releases/download/v1.5.3/Obsidian-1.5.3.AppImage
chmod +x Obsidian-1.5.3.AppImage
./Obsidian-1.5.3.AppImage

# Método 2: Via pacote .deb (Ubuntu/Debian)
sudo apt install obsidian
```

### Windows
1. Baixar em: https://obsidian.md/download
2. Instalador padrão

---

## Configuração do Vault

### Criar Vault como Symlink (Recomendado)
Esta opção permite que o Obsidian acesse diretamente os arquivos do projeto sem duplicação.

```bash
# Definir variáveis
PROJECT_ROOT="/home/johnathan/Área de trabalho/The Moon"
OBSIDIAN_VAULT="$HOME/Obsidian/The-Moon-Vault"

# Criar diretórios
mkdir -p "$OBSIDIAN_VAULT"

# Criar symlinks para diretórios importantes do projeto
ln -sf "$PROJECT_ROOT/Super-Agente/antigravity-kit/.agent" "$OBSIDIAN_VAULT/agent"
ln -sf "$PROJECT_ROOT/Super-Agente/antigravity-kit/.agent/skills" "$OBSIDIAN_VAULT/skills"
ln -sf "$PROJECT_ROOT/Super-Agente/antigravity-kit/.agent/scripts" "$OBSIDIAN_VAULT/scripts"
ln -sf "$PROJECT_ROOT/Super-Agente/docs" "$OBSIDIAN_VAULT/docs-projeto"
ln -sf "$PROJECT_ROOT/docs" "$OBSIDIAN_VAULT/docs-sistema"
ln -sf "$PROJECT_ROOT/infrastructure" "$OBSIDIAN_VAULT/infrastructure"

# Estrutura resultante:
# ~/Obsidian/The-Moon-Vault/
# ├── agent/         -> Super-Agente/antigravity-kit/.agent
# ├── skills/       -> Super-Agente/antigravity-kit/.agent/skills
# ├── scripts/      -> Super-Agente/antigravity-kit/.agent/scripts
# ├── docs-projeto/ -> Super-Agente/docs
# ├── docs-sistema/-> docs/
# └── infrastructure/
```

### Abrir diretório diretamente
1. Abrir Obsidian
2. "Open another vault"
3. Selecionar: `/home/johnathan/Área de trabalho/The Moon/`

---

## Plugins Recomendados

### Plugins Principais (Core)
- **Search** - Busca avançada (já incluso)
- **Graph View** - Visualização de grafo de conhecimento
- **Backlinks** - Ver conexões entre notas
- **Daily Notes** - Para logs de atividades

### Plugins Comunitários

| Plugin | Propósito |
|--------|-----------|
| **Dataview** | Queries dinâmicas em YAML/markdown |
| **Omnisearch** | Busca com ML e fuzzy matching |
| **Git** | Backup automático via Git |
| **Templater** | Templates avançados |
| **QuickAdd** | Criação rápida de notas |

---

## Taxonomia Sugerida

```
The Moon/
├── Super-Agente/
│   ├── antigravity-kit/
│   │   └── .agent/
│   │       ├── skills/          # Habilidades do agente
│   │       ├── scripts/         # Scripts de automação
│   │       ├── data/            # Dados e CSVs
│   │       └── ARCHITECTURE.md  # Documentação de arquitetura
│   ├── docs/                    # Documentação do projeto
│   ├── agents/                  # Definições de agentes
│   ├── mcp-servers/             # Servidores MCP
│   └── skills/                  # Skills disponíveis
├── infrastructure/              # Docker, configs
└── docs/                        # Documentação do sistema
```

---

## Queries Dataview Úteis

### Listar skills do agente
```dataview
LIST
FROM "skills"
SORT file.name ASC
```

### Listar scripts disponíveis
```dataview
TABLE file.name, date
FROM "scripts"
SORT date DESC
```

### Buscar por palavra-chave
```dataview
LIST
FROM ""
WHERE contains(file.content, "palavra-chave")
```

---

## Configurações Recomendadas

### Editor
- **Default view for new tabs**: Reading view
- **Spell check**: Desativado (para código)
- **Line width**: 80

### Files & Links
- **New link format**: Relative path
- **Detect all file extensions**: Ativado
- **Use [[Wikilinks]]**: Ativado

---

## Troubleshooting

### Symlinks não funcionam no Windows (WSL)
Usar o caminho direto ou criar link com:
```bash
# No WSL, monta o diretório Windows
ln -sf /mnt/c/Users/.../The-Moon ~/The-Moon
```

### Performance lenta
- Ativar "Excluded files" em Settings > Files & Links
- Usar plugin "Limiter" para limitar arquivos indexados
