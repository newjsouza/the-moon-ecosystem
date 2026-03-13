# 🛠️ Preferências Técnicas — Johnathan Souza

## Stack Principal
- **Linguagem:** Python 3.10+ (type hints, async/await, docstrings)
- **Containerização:** Docker (15+ serviços no compose)
- **Bancos de Dados:** SQLite (local), Supabase/PostgreSQL (cloud), Google Drive
- **Automação:** Playwright (browser), PyAutoGUI (desktop)
- **APIs/Frameworks:** Telegram Bot, Discord.py, Flask, FastAPI

## LLMs e Providers Preferidos

| Tarefa | Modelo Preferido | Provider |
|--------|------------------|----------|
| Código | Qwen3-32B, Qwen2.5-Coder | Groq, Ollama |
| Raciocínio | Llama-3.3-70B, DeepSeek-R1 | Groq, OpenRouter |
| Tarefas Rápidas | Llama-3.1-8B | Groq |
| Tarefas Leves | Gemma2-9B | Groq |
| Uso Geral | Mixtral-8x7B | Groq |
| Multimodal | Gemini 2.0 Flash | Google |
| Local/Desktop | Qwen2.5-Coder-7B | Ollama |

## Providers (ordem de preferência)
1. **Groq** — Principal (rápido, 14.400 req/dia free)
2. **OpenRouter** — Fallback (200 req/dia free)
3. **GitHub Models** — Premium free
4. **Google Gemini** — Multimodal
5. **Ollama** — Local (ilimitado, privacidade total)

## Infraestrutura
- **VPS:** Oracle Cloud Always Free (preferida), AWS
- **Local-first:** Prefere rodar localmente quando possível
- **Free Tier:** Sempre prioriza soluções gratuitas

## Estilo de Codificação
- **Type Hints:** Sempre em funções e métodos
- **Async/Await:** Preferência por código assíncrono
- **Docstrings:** Documentação detalhada
- **Logging:** structlog ou logging padrão
- **Config via .env:** Credenciais nunca hardcoded
- **Singleton Pattern:** Comum em serviços
- **Error Handling:** Try/except com logging e retorno seguro
- **Substituição Completa:** Prefere substituições de arquivos completos

## Ferramentas de Desenvolvimento
- **IDE:** VS Code com extensão Qwen Code
- **Terminal:** Linux (Zorin OS/Ubuntu), bash/zsh
- **Browser Automation:** Chromium via Playwright
- **Knowledge Base:** Obsidian Vault
- **Versionamento:** Git com commits frequentes
