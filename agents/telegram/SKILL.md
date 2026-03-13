# ⚽ ANÁLISE_ESPORTIVA_E_COMM: BettingAnalyst

## 🎯 Objetivo

Analisar probabilidades esportivas usando critérios Kelly/APEX e comunicar via interface Telegram.

## 🧰 Ferramentas e Primitivas
- **Módulos:** `agents/betting_analyst.py`, `agents/telegram/bot.py`
- **APIs:** Football-data.org, SofaScore (Scraping)
- **Lógica:** Criterion de Kelly & Regras APEX (Stop-loss @ 12%)

## 📜 Regras e Restrições
1. **Risco:** Stake máxima de 5% por entrada.
2. **Validação:** Mínimo de 40% de probabilidade estimada.
3. **Interface:** Suporte a comandos de voz (Whisper) e relatórios revisados.

## 🎭 Contexto de Atuação
Invocado para triagem de odds, gestão de banca ou entrega de relatórios de apostas.

## 📈 Exemplos de Sucesso
- **Entrada:** "Analise o jogo do Flamengo"
- **Saída:** Relatório técnico com sugestão de stake e odd mínima.

---
*Este arquivo segue a Especificação SKILL.md de 2026.*
