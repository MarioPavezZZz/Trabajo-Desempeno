# Deploy — TCGMASTER en Azure for Students

Sitio: **https://tcgmaster.chilecentral.cloudapp.azure.com**

## Infraestructura
| Elemento | Valor |
|---|---|
| Proveedor | Azure for Students (crédito educativo, sin tarjeta) |
| VM | Serie B2 (2 vCPU), Ubuntu, región Chile Central |
| Dominio | Etiqueta DNS gratuita de Azure: `tcgmaster.chilecentral.cloudapp.azure.com` |
| HTTPS | Caddy 2.8 con certificado automático de Let's Encrypt |
| Servicios | Caddy (80/443) → Nginx (estáticos + proxy) → API FastAPI/Gunicorn → PostgreSQL 16 |
| Límites | Iguales al entorno local (API 1 CPU/512 MB, BD 1 CPU/512 MB, Nginx y Caddy 0,5 CPU/128 MB) |

Para el informe, anotar el tamaño exacto de la VM (p. ej. B2s: 2 vCPU, 4 GB)
desde el portal: es parte de la metodología de las pruebas de carga.

## 1. Portal de Azure (una vez)
1. VM → **Redes** → reglas de entrada: permitir TCP **80** y **443** (22 ya existe;
   conviene restringirlo a la IP propia).
2. IP pública → **Configuración** → Etiqueta DNS: `tcgmaster`.

## 2. Preparar el servidor (una vez)
Desde Windows (PowerShell), con la llave descargada al crear la VM:
```powershell
ssh -i $HOME\Downloads\trabajo-desempeno_key.pem azureuser@tcgmaster.chilecentral.cloudapp.azure.com
```
En el servidor:
```bash
curl -fsSL https://raw.githubusercontent.com/MarioPavezZZz/Trabajo-Desempeno/main/scripts/server-setup.sh -o setup.sh
sudo bash setup.sh
exit
```
Instala Docker, agrega 2 GB de swap, activa el firewall (22/80/443) y clona el
repositorio en `~/tcgmaster`.

## 3. Copiar el catálogo (una vez)
Mismo catálogo que en local (mismos productos, precios e ids), sin volver a
consultar las APIs públicas. Desde la raíz del repositorio en Windows:
```powershell
$k = "$HOME\Downloads\trabajo-desempeno_key.pem"; $h = "azureuser@tcgmaster.chilecentral.cloudapp.azure.com"
scp -i $k -r data\media "${h}:~/tcgmaster/data/"
scp -i $k data\cache\normalized.json "${h}:~/tcgmaster/data/cache/"
```

## 4. Deploy y actualizaciones
```bash
ssh -i ... azureuser@tcgmaster.chilecentral.cloudapp.azure.com
bash ~/tcgmaster/scripts/deploy.sh
```
La primera vez crea `~/tcgmaster/.env` desde `.env.production.example` con una
contraseña de BD y un `JWT_SECRET` aleatorios (nunca se suben a Git), carga el
catálogo y verifica `https://…/health`. Las siguientes veces solo actualiza.

## Operación
| Tarea | Comando (en el servidor, dentro de `~/tcgmaster`) |
|---|---|
| Estado | `docker compose -f docker-compose.yml -f docker-compose.prod.yml ps` |
| Logs | `docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api` |
| Reiniciar datos de prueba | `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api python scripts/reset_load_test.py --estadisticas` |
| /metrics desde mi PC | `ssh -i ... -N -L 8000:127.0.0.1:8000 azureuser@…` y abrir http://localhost:8000/metrics |

## Pruebas de carga contra el sitio desplegado
Siempre desde otro equipo (no desde la VM):
```powershell
.\loadtest\run.ps1 -Perfil normal -BaseUrl https://tcgmaster.chilecentral.cloudapp.azure.com -Remoto
```
Con el túnel SSH abierto, `server-metrics.csv` registra CPU y memoria del servidor.
Antes de cada corrida, reiniciar los datos de prueba (comando de la tabla).

## Seguridad
- Solo 22, 80 y 443 abiertos (NSG de Azure + ufw). PostgreSQL, la API directa
  y `/metrics` escuchan solo en `127.0.0.1`.
- Cookies `Secure`, HSTS, `/api/docs` desactivado, secretos solo en el `.env` del servidor.
- Pagos: Webpay Plus en ambiente de **integración** (no mueve dinero real).
