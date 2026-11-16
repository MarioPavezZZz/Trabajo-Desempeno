"""Métricas Prometheus de la API y del contenedor.

Funciona con varios workers de Gunicorn usando el modo multiproceso de
prometheus_client: cada worker escribe sus valores en archivos dentro de
`PROMETHEUS_MULTIPROC_DIR` y `/metrics` los agrega al momento de la consulta.
Si la variable no existe (tests, desarrollo con un proceso), se usa el
registro normal en memoria.

Métricas expuestas:
- http_requests_total{method,route,status}
- http_request_duration_seconds{method,route}  (histograma -> p50/p90/p95/p99)
- http_requests_in_progress{method}
- db_pool_connections_in_use
- container_cpu_usage_seconds_total, container_memory_bytes,
  container_memory_limit_bytes, container_cpu_limit_cores  (desde cgroups v2)
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from prometheus_client.registry import Collector

# Buckets pensados para una API web: resolución fina bajo 250 ms (zona normal)
# y suficientes tramos hasta 10 s para ver la degradación bajo estrés.
LATENCY_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.5, 5.0, 10.0,
)  # fmt: skip

REQUESTS = Counter(
    "http_requests_total",
    "Peticiones HTTP atendidas, por método, plantilla de ruta y código de estado.",
    ["method", "route", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Tiempo de respuesta de la API (desde que entra la petición hasta el último byte).",
    ["method", "route"],
    buckets=LATENCY_BUCKETS,
)
IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Peticiones en curso (sumadas entre workers).",
    ["method"],
    multiprocess_mode="livesum",
)
DB_POOL_IN_USE = Gauge(
    "db_pool_connections_in_use",
    "Conexiones del pool de PostgreSQL ocupadas (sumadas entre workers).",
    multiprocess_mode="livesum",
)

CGROUP_ROOT = Path("/sys/fs/cgroup")


class CgroupCollector(Collector):
    """Lee CPU y memoria del contenedor completo desde cgroups v2.

    A diferencia de las métricas por proceso, incluye a todos los workers de
    Gunicorn, que es lo que hay que comparar contra el límite del contenedor.
    """

    def __init__(self, root: Path = CGROUP_ROOT) -> None:
        self.root = root

    def _read(self, name: str) -> str | None:
        try:
            return (self.root / name).read_text().strip()
        except OSError:
            return None

    def collect(self) -> Iterator[Metric]:
        cpu_stat = self._read("cpu.stat")
        if cpu_stat:
            usage = dict(line.split() for line in cpu_stat.splitlines() if " " in line)
            if "usage_usec" in usage:
                c = CounterMetricFamily(
                    "container_cpu_usage_seconds",
                    "CPU consumida por el contenedor (segundos acumulados).",
                )
                c.add_metric([], int(usage["usage_usec"]) / 1_000_000)
                yield c
        cpu_max = self._read("cpu.max")
        if cpu_max and not cpu_max.startswith("max"):
            quota, period = cpu_max.split()
            g = GaugeMetricFamily("container_cpu_limit_cores", "Límite de CPU del contenedor.")
            g.add_metric([], int(quota) / int(period))
            yield g
        mem = self._read("memory.current")
        if mem:
            g = GaugeMetricFamily("container_memory_bytes", "Memoria usada por el contenedor.")
            g.add_metric([], int(mem))
            yield g
        mem_max = self._read("memory.max")
        if mem_max and mem_max != "max":
            g = GaugeMetricFamily("container_memory_limit_bytes", "Límite de memoria.")
            g.add_metric([], int(mem_max))
            yield g


_CGROUP = CgroupCollector()
_cgroup_in_global_registry = False


def render_metrics() -> tuple[bytes, str]:
    """Genera el texto de /metrics (agregando workers si hay modo multiproceso)."""
    global _cgroup_in_global_registry
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        # Registro nuevo en cada consulta, como indica la documentación del modo multiproceso.
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        registry.register(_CGROUP)
    else:
        registry = REGISTRY
        if not _cgroup_in_global_registry:
            registry.register(_CGROUP)
            _cgroup_in_global_registry = True
    return generate_latest(registry), CONTENT_TYPE_LATEST
