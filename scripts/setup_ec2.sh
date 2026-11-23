#!/bin/bash
# Instala Docker, docker compose y git en Amazon Linux 2023
set -e
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
echo "Listo. Cierra la sesion SSH y vuelve a entrar para que se aplique el grupo docker."
