#!/usr/bin/env bash
# Ejecuta una prueba de carga de TCGMASTER con k6 (en Docker). Equivalente a run.ps1.
#
# Uso: loadtest/run.sh <perfil> [opciones]
#   perfil: humo | baja | normal | pico | estres | navegadores
#   Variables opcionales: BASE_URL, METRICS_URL, RATE, DURATION, RAMP, MAX_VUS, THINK,
#   ASSETS=false, VUS (navegadores), REINICIAR=1, REMOTO=1
# Ejemplo: REINICIAR=1 loadtest/run.sh normal
#          BASE_URL=https://mi-sitio.example REMOTO=1 loadtest/run.sh pico
set -euo pipefail

PERFIL="${1:-humo}"
K6_IMAGE="grafana/k6:0.54.0"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
BASE_URL="${BASE_URL:-http://localhost:8080}"
METRICS_URL="${METRICS_URL:-http://127.0.0.1:8000/metrics}"
RESULTS="$HERE/results/$PERFIL-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RESULTS"

# En Linux se usa la red del host; en Mac/Windows, host.docker.internal.
NET_ARGS=()
CONTAINER_URL="$BASE_URL"
if [[ "$(uname)" == "Linux" ]]; then NET_ARGS=(--network host); else
  CONTAINER_URL="$(echo "$BASE_URL" | sed -E 's#://(localhost|127\.0\.0\.1)#://host.docker.internal#')"; fi

cd "$ROOT"
if [[ "${REINICIAR:-0}" == "1" && "${REMOTO:-0}" != "1" ]]; then
  docker compose exec -T api python scripts/reset_load_test.py --estadisticas
fi

printf '%s\n' "perfil=$PERFIL" "sitio=$BASE_URL" "fecha=$(date -Iseconds)" "rate=${RATE:-}" \
  "duration=${DURATION:-}" "ramp=${RAMP:-}" "max_vus=${MAX_VUS:-}" "think=${THINK:-}" "k6=$K6_IMAGE" \
  > "$RESULTS/parametros.txt"

STOP="$RESULTS/.stop"
SCRAPER_PID=""
if command -v python3 >/dev/null; then
  DOCKER_FLAG=$([[ "${REMOTO:-0}" == "1" ]] && echo "" || echo "--docker")
  python3 "$HERE/tools/scrape_metrics.py" --url "$METRICS_URL" --out "$RESULTS/server-metrics.csv" \
    --interval 5 --stop-file "$STOP" $DOCKER_FLAG &
  SCRAPER_PID=$!
fi

ENV_ARGS=(-e "BASE_URL=$CONTAINER_URL" -e "PERFIL=$PERFIL" -e RESULTS_DIR=/results
          -e K6_WEB_DASHBOARD=true -e K6_WEB_DASHBOARD_EXPORT=/results/report.html)
for v in RATE DURATION RAMP MAX_VUS THINK ASSETS; do
  if [[ -n "${!v:-}" ]]; then ENV_ARGS+=(-e "$v=${!v}"); fi
done
IMAGE="$K6_IMAGE"; SCRIPT=/scripts/main.js; PORT=5665
if [[ "$PERFIL" == "navegadores" ]]; then
  # Corre junto a otro perfil: usa otro puerto para el dashboard.
  IMAGE="$K6_IMAGE-with-browser"; SCRIPT=/scripts/browser.js; PORT=5666
  ENV_ARGS+=(-e "VUS=${VUS:-2}" -e K6_BROWSER_ARGS=no-sandbox)
fi

set +e
docker run --rm -i -p "$PORT:5665" "${NET_ARGS[@]}" -v "$HERE/k6:/scripts:ro" -v "$RESULTS:/results" \
  "${ENV_ARGS[@]}" "$IMAGE" run "$SCRIPT"
K6_EXIT=$?
set -e

if [[ -n "$SCRAPER_PID" ]]; then touch "$STOP"; wait "$SCRAPER_PID" || true; rm -f "$STOP"; fi

if [[ "${REMOTO:-0}" != "1" ]]; then
  docker compose exec -T db psql -U tcgmaster -d tcgmaster -c "COPY (SELECT calls, round(total_exec_time::numeric,1) AS total_ms, round(mean_exec_time::numeric,2) AS promedio_ms, round(max_exec_time::numeric,2) AS max_ms, rows, shared_blks_hit, shared_blks_read, left(regexp_replace(query,'\s+',' ','g'),300) AS consulta FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) ORDER BY total_exec_time DESC LIMIT 25) TO STDOUT WITH CSV HEADER" \
    > "$RESULTS/pg_stat_statements.csv"
fi

echo "Resultados en: $RESULTS"
exit $K6_EXIT
