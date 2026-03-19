#!/bin/bash
# Moon Dashboard Live — Script de inicialização
# Mata instância anterior se existir
pkill -f "apex_dashboard/api.py" 2>/dev/null || true
sleep 1
# Mudar para o diretório do projeto
cd /home/johnathan/Área\ de\ trabalho/The\ Moon
# Iniciar API em background com log
python3 apex_dashboard/api.py > /tmp/moon_dashboard.log 2>&1 &
API_PID=$!
echo "Moon Dashboard iniciado (PID: $API_PID)"
sleep 2
# Verificar se subiu
if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
    echo "API online: http://localhost:8080"
    xdg-open http://localhost:8080 2>/dev/null || \
    firefox http://localhost:8080 2>/dev/null || \
    chromium-browser http://localhost:8080 2>/dev/null || \
    google-chrome http://localhost:8080 2>/dev/null
else
    echo "Erro: API não respondeu. Ver log: /tmp/moon_dashboard.log"
    cat /tmp/moon_dashboard.log
fi