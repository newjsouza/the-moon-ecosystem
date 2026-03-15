#!/bin/bash

# fix_chrome_sessions.sh - Resuelve problemas de persistencia de sesión en Google Chrome (Linux/Zorin OS)
# Antigravity AI Solution

CHROME_DESKTOP="/usr/share/applications/google-chrome.desktop"
LOCAL_DESKTOP="$HOME/.local/share/applications/google-chrome.desktop"

echo "🌙 Resolvendo problema de persistência do Chrome..."

if [ ! -f "$CHROME_DESKTOP" ]; then
    echo "❌ Google Chrome não encontrado em $CHROME_DESKTOP"
    exit 1
fi

# Cria diretório local se não existir
mkdir -p "$HOME/.local/share/applications"

# Copia o arquivo .desktop para o diretório do usuário
cp "$CHROME_DESKTOP" "$LOCAL_DESKTOP"

# Altera a linha Exec para incluir --password-store=basic
# Isso instrui o Chrome a usar armazenamento interno simples em vez do Keyring do GNOME
sed -i 's|Exec=/usr/bin/google-chrome-stable|Exec=/usr/bin/google-chrome-stable --password-store=basic|g' "$LOCAL_DESKTOP"

echo "✅ Arquivo de atalho local criado/atualizado: $LOCAL_DESKTOP"
echo "✅ Configuração '--password-store=basic' aplicada."
echo ""
echo "🚀 PRÓXIMOS PASSOS:"
echo "1. Feche todas as janelas do Google Chrome."
echo "2. Abra o Chrome novamente usando o atalho de aplicativos do sistema."
echo "3. Faça o login na sua conta Google."
echo "4. A sessão agora deve permanecer ativa mesmo após reiniciar o PC."
echo ""
echo "💡 NOTA: Se o problema persistir, pode ser necessário deletar os arquivos locais de login corrompidos (Cuidado: isso removerá senhas salvas localmente):"
echo "   rm ~/.local/share/keyrings/*.keyring"
