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
  .\loadtest\run.ps1 -Perfil normal -BaseUrl https://tcgmaster.chilecentral.cloudapp.azure.com -Remoto -Ssh azureuser@tcgmaster.chilecentral.cloudapp.azure.com -Reiniciar

.NOTES
  Con -Ssh (sitio desplegado), además:
    - -Reiniciar ejecuta el reinicio de datos de prueba EN EL SERVIDOR;
    - abre un túnel SSH a /metrics (puerto local 18000, no choca con el Docker local);
    - corre loadtest/tools/remote_stats.sh en la VM y trae host.csv (CPU con
      %steal, memoria, disco, red) y containers.csv (docker stats por contenedor);
    - guarda pg_stat_statements.csv del servidor.
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
  [switch]$SinImagenes,        # no descargar imágenes de /media
  [string]$Ssh,                # usuario@host del servidor (solo con -Remoto): reinicio, túnel y recursos remotos
  [string]$SshKey = "$HOME\.ssh\tcgmaster.pem",
  [string]$RemoteDir = "~/tcgmaster",
  [string]$Etiqueta            # sufijo opcional del nombre de la carpeta de resultados
)

# "Continue": en PowerShell 5.1, con "Stop" cualquier línea que docker/k6 escriban
# en stderr (sus logs normales) se trata como error fatal y corta la prueba.
$ErrorActionPreference = "Continue"
$K6Image = "grafana/k6:0.54.0"
$Root = Split-Path -Parent $PSScriptRoot
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Name = if ($Etiqueta) { "$Perfil-$Etiqueta-$Stamp" } else { "$Perfil-$Stamp" }
$Results = Join-Path $PSScriptRoot "results\$Name"
New-Item -ItemType Directory -Force $Results | Out-Null

# --- Servidor remoto por SSH -------------------------------------------------
$SshArgs = @()
$RemoteCompose = "docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$RemoteStats = "/tmp/tcg-loadtest/$Name"
$Tunnel = $null
if ($Ssh) {
  if (-not $Remoto) { Write-Error "-Ssh se usa junto con -Remoto"; exit 2 }
  $SshArgs = @("-i", $SshKey, "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30")
  # Túnel a /metrics en un puerto local propio (8000 puede estar ocupado por el Docker local).
  if (-not $PSBoundParameters.ContainsKey("MetricsUrl")) { $MetricsUrl = "http://127.0.0.1:18000/metrics" }
}
function Invoke-Remote([string]$Command) {
  # Ejecuta un comando en la VM dentro del directorio del proyecto.
  & ssh @SshArgs $Ssh "cd $RemoteDir && $Command" 2>&1 | ForEach-Object { "$_" }
}

# Desde el contenedor de k6, "localhost" es el propio contenedor: se usa el host de Docker.
$ContainerUrl = $BaseUrl -replace "://(localhost|127\.0\.0\.1)", "://host.docker.internal"

Push-Location $Root
try {
  if ($Reiniciar -and -not $Remoto) {
    Write-Host "Reiniciando datos de prueba, stock y estadísticas SQL..." -ForegroundColor Cyan
    docker compose exec -T api python scripts/reset_load_test.py --estadisticas | Out-Host
  }
  if ($Ssh) {
    if ($Reiniciar) {
      Write-Host "Reiniciando datos de prueba en el servidor..." -ForegroundColor Cyan
      Invoke-Remote "$RemoteCompose exec -T api python scripts/reset_load_test.py --estadisticas" | Out-Host
    }
    Write-Host "Iniciando recolector de recursos en el servidor y túnel a /metrics..." -ForegroundColor Cyan
    & ssh @SshArgs $Ssh "mkdir -p $RemoteStats" | Out-Null
    & scp @SshArgs "$PSScriptRoot\tools\remote_stats.sh" "${Ssh}:$RemoteStats/remote_stats.sh" | Out-Null
    & ssh @SshArgs $Ssh "nohup bash $RemoteStats/remote_stats.sh $RemoteStats 5 > $RemoteStats/collector.log 2>&1 < /dev/null &" | Out-Null
    $localPort = ([uri]$MetricsUrl).Port
    # Start-Process no agrega comillas: la ruta de la llave puede tener espacios.
    $Tunnel = Start-Process -FilePath "ssh" -PassThru -WindowStyle Hidden -ArgumentList @(
      "-i", "`"$SshKey`"", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30",
      "-N", "-o", "ExitOnForwardFailure=yes", "-L", "${localPort}:127.0.0.1:8000", $Ssh)
    Start-Sleep -Seconds 3
    if ($Tunnel.HasExited) { Write-Warning "El túnel SSH a /metrics no se abrió: server-metrics.csv quedará vacío." }
  }

  $vmInfo = ""
  if ($Ssh) { $vmInfo = (& ssh @SshArgs $Ssh "echo `$(nproc) vCPU, `$(free -m | awk '/Mem:/{print `$2}') MB RAM, `$(uname -r)") -join " " }
  @(
    "perfil=$Perfil", "sitio=$BaseUrl", "fecha=$(Get-Date -Format s)", "rate=$Rate", "duration=$Duration",
    "ramp=$Ramp", "max_vus=$MaxVus", "think=$Think", "imagenes=$(-not $SinImagenes)", "k6=$K6Image",
    "servidor=$vmInfo", "generador=$env:COMPUTERNAME $((Get-CimInstance Win32_Processor | Select-Object -First 1).Name)"
  ) | Set-Content -Encoding utf8 (Join-Path $Results "parametros.txt")

  # Recolector de métricas del servidor en segundo plano (se detiene con un archivo "stop").
  # -MetricsUrl "" lo desactiva (p. ej. navegadores corriendo junto a otro perfil).
  $StopFile = Join-Path $Results ".stop"
  $Scraper = $null
  $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
  if ($Python -and $MetricsUrl) {
    $scraperArgs = @("`"$PSScriptRoot\tools\scrape_metrics.py`"", "--url", $MetricsUrl, "--out", "`"$Results\server-metrics.csv`"", "--interval", "5", "--stop-file", "`"$StopFile`"")
    if (-not $Remoto) { $scraperArgs += "--docker" }
    $Scraper = Start-Process -FilePath $Python -ArgumentList $scraperArgs -PassThru -WindowStyle Hidden
  } elseif (-not $Python) {
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
  if ($Tunnel -and -not $Tunnel.HasExited) { $Tunnel | Stop-Process -Force }
  if ($Ssh) {
    Write-Host "Trayendo recursos y SQL del servidor..." -ForegroundColor Cyan
    & ssh @SshArgs $Ssh "touch $RemoteStats/.stop; sleep 12" | Out-Null
    & scp @SshArgs "${Ssh}:$RemoteStats/host.csv" "${Ssh}:$RemoteStats/containers.csv" "$Results" | Out-Null
    $sqlRemote = "COPY (SELECT calls, round(total_exec_time::numeric, 1) AS total_ms, round(mean_exec_time::numeric, 2) AS promedio_ms, round(max_exec_time::numeric, 2) AS max_ms, rows, shared_blks_hit, shared_blks_read, left(regexp_replace(query, '\s+', ' ', 'g'), 300) AS consulta FROM pg_stat_statements WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database()) ORDER BY total_exec_time DESC LIMIT 25) TO STDOUT WITH CSV HEADER"
    # El SQL viaja por stdin para no pelear con las comillas de PowerShell/ssh/bash.
    $sqlRemote | & ssh @SshArgs $Ssh "cd $RemoteDir && $RemoteCompose exec -T db psql -q -U tcgmaster -d tcgmaster -f -" |
      Set-Content -Encoding utf8 (Join-Path $Results "pg_stat_statements.csv")
    & ssh @SshArgs $Ssh "rm -rf $RemoteStats" | Out-Null
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
