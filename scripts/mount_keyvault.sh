#!/bin/bash
# mount_keyvault.sh - Inicia o KeyVault e abre no navegador

PROJECT_ROOT="/home/johnathan/Área de trabalho/The Moon"
cd "$PROJECT_ROOT"

# Matar processos antigos na porta 8080
fuser -k 8080/tcp 2>/dev/null

# Iniciar o serviço em background usando o venv
source .venv/bin/activate
python3 core/services/key_vault.py > /tmp/keyvault.log 2>&1 &

# Esperar o serviço subir
sleep 2

# Abrir no navegador padrão
xdg-open http://localhost:8080
