#!/bin/bash
echo "====================================="
echo " Instalador do Docker Desktop - The Moon "
echo "====================================="
echo "Adicionando o usuário aos grupos necessários..."
sudo usermod -aG docker $USER
sudo usermod -aG kvm $USER

echo "Baixando o pacote do Docker Desktop..."
wget -O /tmp/docker-desktop.deb "https://desktop.docker.com/linux/main/amd64/docker-desktop-amd64.deb"

echo "Instalando o Docker Desktop (pode demorar alguns minutos)..."
sudo apt-get update
sudo apt-get install -y /tmp/docker-desktop.deb

echo "Limpando arquivos temporários..."
rm /tmp/docker-desktop.deb

echo "Instalação concluída! Recomendamos reiniciar a sessão (fazer logoff e login) para que as permissões de grupo tenham efeito."
