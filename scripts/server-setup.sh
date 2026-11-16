#!/usr/bin/env bash
# Preparación inicial del servidor Ubuntu (se ejecuta UNA vez, con sudo).
#
#   curl -fsSL https://raw.githubusercontent.com/MarioPavezZZz/Trabajo-Desempeno/main/scripts/server-setup.sh -o setup.sh
#   sudo bash setup.sh
#
# - Docker y Docker Compose desde los paquetes oficiales de Ubuntu.
# - 2 GB de swap: compilar el frontend y PostgreSQL juntos pueden superar la RAM de una VM pequeña.
# - Firewall (ufw): solo SSH, 80 y 443. Ojo: Docker publica puertos por fuera de ufw,
#   por eso los servicios internos se publican solo en 127.0.0.1 (ver .env.production.example).
# - Clona el repositorio en el home del usuario que llamó a sudo.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/MarioPavezZZz/Trabajo-Desempeno.git}"
TARGET_USER="${SUDO_USER:-$USER}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
APP_DIR="$TARGET_HOME/tcgmaster"

echo "==> Paquetes"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y docker.io docker-compose-v2 git ufw curl
systemctl enable --now docker
usermod -aG docker "$TARGET_USER"

echo "==> Swap de 2 GB"
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Firewall"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Repositorio en $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u "$TARGET_USER" git clone "$REPO_URL" "$APP_DIR"
fi
sudo -u "$TARGET_USER" mkdir -p "$APP_DIR/data/cache" "$APP_DIR/data/media"

echo
echo "Listo. Cierra la sesión SSH y vuelve a entrar (para usar docker sin sudo)."
echo "Luego copia los datos del catálogo y ejecuta: bash ~/tcgmaster/scripts/deploy.sh"
