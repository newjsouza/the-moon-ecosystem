# 🔐 The Moon — GitHub Secrets Configuration Guide

Este documento explica como configurar os **secrets** necessários para o funcionamento completo do ecossistema The Moon no GitHub Actions.

---

## 📍 Onde Configurar

1. Acesse seu repositório no GitHub
2. Clique em **Settings** (Configurações)
3. No menu lateral esquerdo, clique em **Secrets and variables** → **Actions**
4. Clique em **New repository secret**
5. Preencha o **Name** (nome da variável) e **Value** (valor da chave)
6. Clique em **Add secret**

---

## 🔑 Secrets Obrigatórios

Estes secrets são necessários para funcionalidades críticas do ecossistema:

### 1. `GROQ_API_KEY`
- **Finalidade:** LLM primário para todas as operações de inteligência artificial
- **Modelos:** `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `gemma2-9b-it`
- **Onde obter:** [https://console.groq.com/keys](https://console.groq.com/keys)
- **Custo:** Free tier (2-5 requisições/segundo, 30 req/min)
- **Usado por:** `LlmAgent`, `LLMRouter`, `ArchitectAgent`, `OmniChannelStrategist`

### 2. `TELEGRAM_BOT_TOKEN`
- **Finalidade:** Bot de comunicação do ecossistema via Telegram
- **Onde obter:** Conversar com `@BotFather` no Telegram e criar um novo bot
- **Custo:** Gratuito
- **Usado por:** `TelegramChannel`, `OmniChannelStrategist`, `SportsAnalyzer`

### 3. `GITHUB_TOKEN`
- **Finalidade:** Automação de repositórios (commits, issues, PRs)
- **Escopos necessários:** `repo`, `workflow`
- **Onde gerar:** [GitHub Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens)
- **Custo:** Gratuito
- **Usado por:** `GithubAgent`, `AutonomousDevOpsRefactor`

---

## 🔑 Secrets Opcionais (Fallback)

Estes secrets habilitam funcionalidades de fallback e melhoram a resiliência do sistema:

### 4. `GEMINI_API_KEY`
- **Finalidade:** Fallback secundário quando Groq está indisponível
- **Modelo:** `gemini-2.0-flash`
- **Onde obter:** [https://makersuite.google.com/app/apikey](https://makersuite.google.com/app/apikey)
- **Custo:** Free tier (15 requisições/minuto)
- **Usado por:** `LLMRouter` (fallback automático)

### 5. `OPENROUTER_API_KEY`
- **Finalidade:** Fallback terciário com modelos open-source
- **Modelos:** `meta-llama/llama-3.3-70b-instruct`, `meta-llama/llama-3.1-8b-instruct`
- **Onde obter:** [https://openrouter.ai/keys](https://openrouter.ai/keys)
- **Custo:** Free tier disponível (varia por modelo)
- **Usado por:** `LLMRouter` (fallback automático)

### 6. `ALPHA_VANTAGE_API_KEY`
- **Finalidade:** Dados financeiros para o `EconomicSentinel`
- **Dados:** Ações, Forex, Crypto, Indicadores Técnicos
- **Onde obter:** [https://www.alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key)
- **Custo:** Free tier (5 req/min, 500 req/dia)
- **Usado por:** `EconomicSentinel`, `FinancialEngine`

---

## 📋 Tabela Resumo

| Secret | Obrigatório? | Impacto se Ausente |
|--------|-------------|-------------------|
| `GROQ_API_KEY` | ✅ Sim | Sistema opera em modo degradado (sem LLM) |
| `TELEGRAM_BOT_TOKEN` | ✅ Sim | Canal Telegram indisponível |
| `GITHUB_TOKEN` | ✅ Sim | GithubAgent não funciona |
| `GEMINI_API_KEY` | ⚠️ Opcional | Sem fallback secundário |
| `OPENROUTER_API_KEY` | ⚠️ Opcional | Sem fallback terciário |
| `ALPHA_VANTAGE_API_KEY` | ⚠️ Opcional | EconomicSentinel com dados limitados |

---

## 🧪 Validação Local

### 1. Configurar ambiente local

```bash
# Copie o template
cp .env.example .env

# Edite com suas chaves (nano, vim, ou editor de preferência)
nano .env
```

### 2. Exemplo de `.env` configurado

```bash
# LLM Principal
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Telegram
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHANNEL_ID=@meu_canal

# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_REPO=seu-usuario/the-moon-ecosystem

# Fallbacks (Opcionais)
GEMINI_API_KEY=AIzaxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Dados Financeiros (Opcional)
ALPHA_VANTAGE_API_KEY=xxxxxxxxxxxxxxxx
```

### 3. Rodar testes

```bash
# Testes unitários (NÃO requerem secrets)
pytest tests/ -m "not requires_groq and not requires_telegram and not requires_github" -v

# Testes de integração (requerem secrets configurados no .env)
pytest tests/ -v

# Testes com cobertura
pytest tests/ --cov=agents --cov=core --cov-report=term-missing
```

---

## 🚀 Validação no CI/CD

O GitHub Actions está configurado para:

1. **Sempre rodar:**
   - Lint (Ruff)
   - Security Scan (Bandit)
   - Testes unitários (sem dependência de secrets)
   - Import sanity check
   - Code formatting check
   - MOON_CODEX compliance check

2. **Rodar apenas se secrets configurados:**
   - Testes de integração (requerem `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, etc.)

3. **Exibir guia de configuração:**
   - Se nenhum secret estiver configurado, o CI exibe um guia completo de setup

---

## ⚠️ Segurança

### Boas Práticas

1. **NUNCA** commite arquivos `.env` com chaves reais
2. **SEMPRE** use `.env.example` como template
3. **VERIFIQUE** que `.env` está no `.gitignore`
4. **ROTACIONE** chaves periodicamente (recomendado: 90 dias)
5. **USE** secrets do GitHub ao invés de variáveis de ambiente no repositório

### Verificação de Vazamentos

O CI inclui um job que verifica se arquivos `.env` foram commitados acidentalmente:

```yaml
- name: Verificar ausência de secrets commitados
  run: |
    if git log --all --full-history -- "**/.env" | grep -q commit; then
      echo "❌ ALERTA: arquivo .env encontrado no histórico git"
      exit 1
    fi
    echo "✅ Nenhum secret detectado no histórico"
```

---

## 🆘 Troubleshooting

### CI falhando com "Secret not found"

**Sintoma:** Testes de integração falham com erro de autenticação

**Solução:**
1. Verifique se o secret está configurado em **Settings → Secrets and variables → Actions**
2. Confirme que o nome está **exatamente igual** (case-sensitive)
3. Verifique se o valor não tem espaços extras
4. Para secrets recém-criados, pode ser necessário re-rodar o workflow

### Tests skipped no CI

**Sintoma:** Mensagem "Integration tests skipped: No secrets configured"

**Solução:**
- Isso é **comportamento esperado** se nenhum secret estiver configurado
- Configure pelo menos `GROQ_API_KEY` para habilitar testes de integração
- Veja a seção "Onde Configurar" acima

### Modo degradado ativado localmente

**Sintoma:** Respostas do LLM retornam "[MODO DEGRADADO ATIVO]"

**Solução:**
1. Verifique se `.env` existe na raiz do projeto
2. Confirme que `GROQ_API_KEY` está configurada corretamente
3. Teste a chave manualmente na [console da Groq](https://console.groq.com/)
4. Reinicie a aplicação após alterar `.env`

---

## 📚 Links Úteis

- [GitHub Actions Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Groq Cloud Console](https://console.groq.com/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [GitHub Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [Google Gemini API](https://ai.google.dev/)
- [OpenRouter API](https://openrouter.ai/docs)
- [Alpha Vantage API](https://www.alphavantage.co/documentation/)

---

*Documento atualizado conforme MOON_CODEX — Março 2026*
