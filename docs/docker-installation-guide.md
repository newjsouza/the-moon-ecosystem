# 🚀 Guia de Instalação - Docker Desktop com WSL2

## Opção Recomendada: Docker Desktop no Windows (com WSL2)

### Pré-requisitos
- Windows 11 (ou Windows 10 Pro 21H2+)
- WSL2 instalado
- Mínimo 4GB RAM disponível para Docker

### Passo 1: Instalar WSL2 (se não instalado)
```powershell
# Executar como Administrador no PowerShell
wsl --install
# Reiniciar o PC
```

### Passo 2: Baixar e Instalar Docker Desktop
1. Baixar: https://www.docker.com/products/docker-desktop/
2. Executar o instalador
3. Durante a instalação, marcar "Use WSL2 instead of Hyper-V"

### Passo 3: Configurar Recursos no .wslconfig
Criar arquivo `C:\Users\<seu_usuario>\.wslconfig`:

```ini
[wsl2]
processors=4
memory=4GB
swap=2GB
localhostForwarding=true

[network]
generateResolvConf=true
```

### Passo 4: Verificar Instalação
```bash
docker --version
docker-compose --version
docker ps
```

---

## Alternativa: Docker no Linux (WSL2/Ubuntu)

Para quem prefere trabalhar diretamente no Linux:

### Instalação Automatizada
```bash
# Criar script de instalação
cat > install-docker.sh << 'EOF'
#!/bin/bash
set -e

echo "🚀 Instalando Docker..."

# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependências
sudo apt install -y ca-certificates curl gnupg lsb-release

# Adicionar repositório Docker
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg --dearmpg | sudo gor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Instalar Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Adicionar usuário ao grupo docker
sudo usermod -aG docker $USER

# Iniciar e habilitar Docker
sudo systemctl enable docker
sudo systemctl start docker

echo "✅ Docker instalado com sucesso!"
echo "⚠️  Execute 'newgrp docker' ou faça logout/login para usar Docker sem sudo"
EOF

chmod +x install-docker.sh
./install-docker.sh
```

### Configuração de Recursos
```bash
# Editar limites de memória (opcional)
sudo nano /etc/docker/daemon.json
```

```json
{
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 64000,
      "Soft": 64000
    }
  },
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

```bash
sudo systemctl restart docker
```

---

## Comandos Essenciais

| Comando | Descrição |
|---------|------------|
| `docker ps` | Listar containers ativos |
| `docker ps -a` | Listar todos os containers |
| `docker start <container>` | Iniciar container |
| `docker stop <container>` | Parar container |
| `docker logs -f <container>` | Ver logs em tempo real |
| `docker-compose up -d` | Iniciar stack com docker-compose |
| `docker-compose down` | Parar stack |
| `docker system prune` | Limpar recursos não utilizados |

## Troubleshooting

### WSL2 não inicia
```powershell
wsl --shutdown
wsl --update
```

### Permissão negada ao usar Docker
```bash
# Adicionar usuário ao grupo
sudo usermod -aG docker $USER
# Ou usar:
newgrp docker
```

### Docker Desktop travando
```powershell
# No PowerShell (Admin)
Restart-Service Docker
```
