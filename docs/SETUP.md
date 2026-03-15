# 🛠️ Guia de Setup — The Moon Ecosystem

## Requisitos
- Python 3.10+
- Linux (Zorin OS / Ubuntu-based)
- ffmpeg (`sudo apt install ffmpeg`)
- git, gh (GitHub CLI)

## Instalação
```bash
git clone https://github.com/newjsouza/the-moon-ecosystem
cd the-moon-ecosystem
pip install -r requirements.txt --break-system-packages
```

## Configuração
```bash
cp .env.example .env   # edite com suas credenciais
```

### Variáveis obrigatórias
```
GROQ_API_KEY=            # https://console.groq.com
TELEGRAM_BOT_TOKEN=      # @BotFather no Telegram
TELEGRAM_CHAT_ID=        # use /id no bot após iniciar
GITHUB_TOKEN=            # https://github.com/settings/tokens
GITHUB_REPO=             # formato: owner/repo
```

### Variáveis opcionais
```
ODDS_API_KEY=            # https://the-odds-api.com (free tier)
TWITTER_API_KEY=         # dev.twitter.com
LINKEDIN_ACCESS_TOKEN=   # linkedin.com/developers
INFRA_VPS_MONTHLY=       # custo mensal do VPS em BRL
MOON_ALLOW_ALL_COMMANDS= # 1 para liberar execução remota total
```

## Iniciar
```bash
# Bot standalone (recomendado para teste):
python3 run_bot.py

# Ecossistema completo:
python3 main.py
```
