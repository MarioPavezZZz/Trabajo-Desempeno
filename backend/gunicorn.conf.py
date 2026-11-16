"""Configuración de Gunicorn (gestor de procesos) con workers Uvicorn (asíncronos).

Parámetros clave para las pruebas de carga, todos por variable de entorno:
- API_WORKERS: procesos worker (regla práctica: 1-2 por núcleo asignado).
- API_TIMEOUT: segundos antes de reiniciar un worker bloqueado.
- API_KEEPALIVE: segundos que se mantiene abierta una conexión ociosa.
"""

import os
import shutil
from pathlib import Path

bind = f"0.0.0.0:{os.getenv('API_PORT', '8000')}"
workers = int(os.getenv("API_WORKERS", "2"))
worker_class = "uvicorn_worker.UvicornWorker"
timeout = int(os.getenv("API_TIMEOUT", "30"))
graceful_timeout = 20
keepalive = int(os.getenv("API_KEEPALIVE", "5"))
accesslog = None  # el log de acceso lo escribe el middleware de la app (JSON)
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()


def on_starting(server) -> None:
    """Limpia los archivos de métricas de una ejecución anterior."""
    path = os.getenv("PROMETHEUS_MULTIPROC_DIR")
    if path:
        shutil.rmtree(path, ignore_errors=True)
        Path(path).mkdir(parents=True, exist_ok=True)


def child_exit(server, worker) -> None:
    """Marca como muertos los archivos del worker que terminó (sus gauges dejan de sumar)."""
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
