<#
.SYNOPSIS
  Ejecuta una prueba de carga de TCGMASTER con k6 (en Docker) y guarda los resultados.

.DESCRIPTION
  Deja en loadtest/results/<perfil>-<fecha>/:
    report.html            dashboard de k6 (latencia, throughput y errores en el tiempo)
    summary.json/resumen.txt  percentiles avg/med/p90/p95/p99 por endpoint y por grupo
    server-metrics.csv     CPU, memoria, pool de BD, peticiones y latencia del servidor (cada 5 s)
    docker-stats.csv       CPU y memoria de cada contenedor, incluida la BD (solo local)
    pg_stat_statements.csv consultas SQL más costosas de la corrida (solo local)
    parametros.txt         perfil y parámetros usados (para la metodología del informe)
  Mientras corre, el dashboard en vivo está en http://localhost:5665

.EXAMPLE
  .\loadtest\run.ps1 -Perfil humo
  .\loadtest\run.ps1 -Perfil normal -Reiniciar
  .\loadtest\run.ps1 -Perfil estres -BaseUrl https://mi-sitio.example -Remoto
  .\loadtest\run.ps1 -Perfil baja -Rate 2 -Duration 10m -Think 0.5
#>
param(
  [ValidateSet("humo", "baja", "normal", "pico", "estres", "navegadores")]
  [string]$Perfil = "humo",
  [string]$BaseUrl = "http://localhost:8080",
  [string]$MetricsUrl = "http://127.0.0.1:8000/metrics",
  [switch]$Reiniciar,          # reinicia datos de prueba, stock y pg_stat_statements antes de correr
  [switch]$Remoto,             # el sitio no es el Docker local: omite reinicio, docker stats y SQL
  [string]$Rate,               # sesiones nuevas por segundo en la meseta
  [string]$Duration,           # duración de la meseta (p. ej. 10m)
  [string]$Ramp,               # duración del ramp-up (p. ej. 1m)
  [string]$MaxVus,             # máximo de usuarios virtuales
  [string]$Think,              # multiplicador de pausas (1 = realista, 0 = sin pausas)
  [int]$Navegadores = 2,       # solo perfil navegadores: navegadores simultáneos
  [switch]$SinImagenes         # no descargar imágenes de /media
)

# "Continue": en PowerShell 5.1, con "Stop" cualquier línea que docker/k6 escriban
# en stderr (sus logs normales) se trata como error fatal y corta la prueba.
$ErrorActionPreference = "Continue"
$K6Image = "grafana/k6:0.54.0"
$Root = Split-Path -Parent $PSScriptRoot
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Results = Join-Path $PSScriptRoot "results\$Perfil-$Stamp"
New-Item -ItemType Directory -Force $Results | Out-Null

# Desde el contenedor de k6, "localhost" es el propio contenedor: se usa el host de Docker.
$ContainerUrl = $BaseUrl -replace "://(localhost|127\.0\.0\.1)", "://host.docker.internal"

Push-Location $Root
try {
  if ($Reiniciar -and -not $Remoto) {
    Write-Host "Reiniciando datos de prueba, stock y estadísticas SQL..." -ForegroundColor Cyan
    docker compose exec -T api python scripts/reset_load_test.py --estadisticas | Out-Host
  }

  @(
    "perfil=$Perfil", "sitio=$BaseUrl", "fecha=$(Get-Date -Format s)", "rate=$Rate", "duration=$Duration",
    "ramp=$Ramp", "max_vus=$MaxVus", "think=$Think", "imagenes=$(-not $SinImagenes)", "k6=$K6Image"
  ) | Set-Content -Encoding utf8 (Join-Path $Results "parametros.txt")

  # Recolector de métricas del servidor en segundo plano (se detiene con un archivo "stop").
  $StopFile = Join-Path $Results ".stop"
  $Scraper = $null
  $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
  if ($Python) {
    $scraperArgs = @("`"$PSScriptRoot\tools\scrape_metrics.py`"", "--url", $MetricsUrl, "--out", "`"$Results\server-metrics.csv`"", "--interval", "5", "--stop-file", "`"$StopFile`"")
    if (-not $Remoto) { $scraperArgs += "--docker" }
    $Scraper = Start-Process -FilePath $Python -ArgumentList $scraperArgs -PassThru -WindowStyle Hidden
  } else {
    Write-Warning "Python no encontrado: no se registrarán métricas del servidor."
  }

  $envArgs = @("-e", "BASE_URL=$ContainerUrl", "-e", "PERFIL=$Perfil", "-e", "RESULTS_DIR=/results",
               "-e", "K6_WEB_DASHBOARD=true", "-e", "K6_WEB_DASHBOARD_EXPORT=/results/report.html")
  foreach ($pair in @(@("RATE", $Rate), @("DURATION", $Duration), @("RAMP", $Ramp), @("MAX_VUS", $MaxVus), @("THINK", $Think))) {
    if ($pair[1]) { $envArgs += @("-e", "$($pair[0])=$($pair[1])") }
  }
  if ($SinImagenes) { $envArgs += @("-e", "ASSETS=false") }

  $image = $K6Image
  $script = "/scripts/main.js"
  $port = 5665
  if ($Perfil -eq "navegadores") {
    # Corre junto a otro perfil: usa otro puerto para el dashboard.
    $image = "$K6Image-with-browser"
    $script = "/scripts/browser.js"
    $port = 5666
    $envArgs += @("-e", "VUS=$Navegadores", "-e", "K6_BROWSER_ARGS=no-sandbox")
  }

  Write-Host "k6 $Perfil contra $BaseUrl  (dashboard en vivo: http://localhost:$port)" -ForegroundColor Cyan
  # 2>&1 + ForEach: muestra los logs de k6 como texto normal (sin el formato de error de PowerShell).
  docker run --rm -i -p "${port}:5665" `
    -v "${PSScriptRoot}\k6:/scripts:ro" -v "${Results}:/results" `
    @envArgs $image run $script 2>&1 | ForEach-Object { "$_" }
  $k6Exit = $LASTEXITCODE
}
finally {
  if ($Scraper) {
    New-Item -ItemType File -Force $StopFile | Out-Null
    $Scraper | Wait-Process -Timeout 40 -ErrorAction SilentlyContinue
    if (-not $Scraper.HasExited) { $Scraper | Stop-Process -Force }
    Remove-Item $StopFile -ErrorAction SilentlyContinue
  }
  Pop-Location
}

if (-not $Remoto) {
  # Las 25 consultas SQL con más tiempo total en la corrida.
  $sql = "COPY (SELECT calls, round(total_exec_time::numeric, 1) AS total_ms, round(mean_exec_time::numeric, 2) AS promedio_ms, round(max_exec_time::numeric, 2) AS max_ms, rows, shared_blks_hit, shared_blks_read, left(regexp_replace(query, '\s+', ' ', 'g'), 300) AS consulta FROM pg_stat_statements WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database()) ORDER BY total_exec_time DESC LIMIT 25) TO STDOUT WITH CSV HEADER"
  Push-Location $Root
  docker compose exec -T db psql -U tcgmaster -d tcgmaster -c $sql | Set-Content -Encoding utf8 (Join-Path $Results "pg_stat_statements.csv")
  Pop-Location
}

Write-Host ""
Write-Host "Resultados en: $Results" -ForegroundColor Green
if ($k6Exit -eq 99) { Write-Host "Algún umbral no se cumplió (ver resumen)." -ForegroundColor Yellow }
elseif ($k6Exit -ne 0) { Write-Host "k6 terminó con código $k6Exit." -ForegroundColor Yellow }
exit $k6Exit
