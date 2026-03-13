#!/bin/bash
set -e

echo "🚀 Instalando Docker no Zorin OS..."

echo "📦 Atualizando sistema..."
sudo apt update && sudo apt upgrade -y

echo "📦 Instalando dependências..."
sudo apt install -y ca-certificates curl gnupg lsb-release

echo "🔑 Adicionando chave GPG do Docker..."
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo "📝 Adicionando repositório Docker..."
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "📦 Instalando Docker..."
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "👤 Adicionando usuário ao grupo docker..."
sudo usermod -aG docker $USER

echo "✅ Docker instalado com sucesso!"
echo "⚠️  Execute os comandos abaixo para ativá-lo sem reiniciar:"
echo "    newgrp docker"
echo "    sudo systemctl enable docker"
echo "    sudo systemctl start docker"
