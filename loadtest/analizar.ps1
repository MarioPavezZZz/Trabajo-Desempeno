<#
.SYNOPSIS
  Genera gráficos y tablas de la Fase 2 a partir de las corridas de k6 (en Docker, sin instalar nada).

.EXAMPLE
  .\loadtest\analizar.ps1 -Out docs/fase2 `
    -Corridas "baja=loadtest/results/baja-azure-...", "normal=loadtest/results/normal-azure-..." `
    -Navegadores "baja=loadtest/results/navegadores-azure-baja-..."
  Rutas relativas a la raíz del repositorio. Ver loadtest/tools/analizar.py.
#>
param(
  [string]$Out = "docs/fase2",
  [Parameter(Mandatory = $true)][string[]]$Corridas,
  [string[]]$Navegadores = @(),
  [string]$Estres = "estrés"
)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$pyArgs = @("--out", $Out, "--estres", $Estres)
foreach ($c in $Corridas) { $pyArgs += @("--corrida", $c) }
foreach ($n in $Navegadores) { $pyArgs += @("--navegadores", $n) }
# Versiones fijas: el análisis debe ser reproducible.
docker run --rm -v "${Root}:/w" -w /w -e PYTHONIOENCODING=utf-8 python:3.12.7-slim sh -c `
  "pip install -q --root-user-action=ignore --disable-pip-version-check matplotlib==3.9.2 tzdata==2024.2 && python loadtest/tools/analizar.py $($pyArgs | ForEach-Object { "'$_'" })" 2>&1 | ForEach-Object { "$_" }
exit $LASTEXITCODE
