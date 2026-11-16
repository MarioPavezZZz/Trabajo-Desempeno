# Imagen del backend de TCGMASTER (API + migraciones + script de datos semilla).
# Contexto de build: raíz del repositorio (necesita backend/ y scripts/).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# 1) Dependencias primero: esta capa queda en caché mientras pyproject no cambie.
COPY backend/pyproject.toml ./pyproject.toml
RUN python - <<'EOF'
import subprocess, sys, tomllib
data = tomllib.load(open("pyproject.toml", "rb"))
deps = data["project"]["dependencies"] + data["project"]["optional-dependencies"]["dev"]
subprocess.check_call([sys.executable, "-m", "pip", "install", *deps])
EOF

# 2) Código.
COPY backend/ ./
COPY scripts/ ./scripts/

# Usuario sin privilegios.
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown -R app /data /app
USER app

# Métricas multiproceso: cada worker escribe aquí y /metrics agrega.
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

EXPOSE 8000
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app.main:app"]
