#!/usr/bin/env bash
# Deploy / actualización de TCGMASTER en el servidor (se puede ejecutar cuantas veces se quiera).
#
#   bash ~/tcgmaster/scripts/deploy.sh
#
# 1. Descarga la última versión desde GitHub.
# 2. La primera vez crea .env desde .env.production.example con secretos aleatorios.
# 3. Construye las imágenes, aplica migraciones y carga el catálogo si la base está vacía.
# 4. Levanta todo (Caddy + Nginx + API + PostgreSQL) y verifica /health por HTTPS.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

echo "==> Código"
git pull --ff-only

if [ ! -f .env ]; then
  echo "==> Creando .env de producción con secretos nuevos"
  cp .env.production.example .env
  sed -i "s/^POSTGRES_PASSWORD=GENERAR_CLAVE_BD$/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
  sed -i "s/^JWT_SECRET=GENERAR_JWT$/JWT_SECRET=$(openssl rand -hex 32)/" .env
  chmod 600 .env
fi
if grep -q 'GENERAR_' .env; then
  echo "ERROR: .env todavía tiene valores GENERAR_*" >&2
  exit 1
fi
SITE_DOMAIN="$(grep '^SITE_DOMAIN=' .env | cut -d= -f2)"

echo "==> Imágenes"
"${COMPOSE[@]}" build

echo "==> Base de datos y migraciones"
"${COMPOSE[@]}" up -d db
"${COMPOSE[@]}" run --rm api alembic upgrade head

PRODUCTS="$("${COMPOSE[@]}" exec -T db psql -U tcgmaster -d tcgmaster -tAc 'SELECT count(*) FROM products' || echo 0)"
if [ "${PRODUCTS// /}" = "0" ]; then
  if [ -f data/cache/normalized.json ]; then
    echo "==> Cargando catálogo (sin red, desde data/cache/normalized.json)"
    "${COMPOSE[@]}" run --rm api python scripts/seed_catalog.py load
  else
    echo "==> Sin data/cache/normalized.json: descargando desde las APIs públicas (unos minutos)"
    "${COMPOSE[@]}" run --rm api python scripts/seed_catalog.py all
  fi
fi

echo "==> Servicios"
"${COMPOSE[@]}" up -d
"${COMPOSE[@]}" ps

echo "==> Verificación"
for i in $(seq 1 30); do
  if curl -fsS "https://$SITE_DOMAIN/health" >/dev/null 2>&1; then
    echo "OK: https://$SITE_DOMAIN/health -> $(curl -fsS "https://$SITE_DOMAIN/health")"
    exit 0
  fi
  sleep 5
done
echo "ADVERTENCIA: /health no respondió por HTTPS. Revisa: ${COMPOSE[*]} logs caddy api" >&2
exit 1
