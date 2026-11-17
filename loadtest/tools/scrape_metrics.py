"""Recolector de métricas del servidor durante una prueba de carga.

Lee /metrics (formato Prometheus) cada N segundos y escribe un CSV con la
evolución de CPU, memoria, conexiones del pool, peticiones en curso,
throughput, errores 5xx y latencia (promedio y p95 de cada intervalo).
Con --docker, además guarda `docker stats` de todos los contenedores
(incluida la base de datos, que no expone /metrics).

Solo usa la biblioteca estándar de Python (no requiere instalar nada).

Uso:
  python loadtest/tools/scrape_metrics.py --url http://127.0.0.1:8000/metrics \
      --out loadtest/results/x/server-metrics.csv --interval 5 --docker
Se detiene con Ctrl+C, al pasar --duration segundos o si aparece el archivo --stop-file.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import subprocess
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

# Las etiquetas pueden contener llaves dentro de las comillas (route="/api/products/{slug}"),
# así que el bloque {...} se reconoce por valores entre comillas y no con [^}]*.
LINE_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{(?:[^"}]|"(?:[^"\\]|\\.)*")*\})?\s+([-+eE0-9.NaInf]+)')
LABEL_RE = re.compile(r'(\w+)="([^"]*)"')


def parse(text: str) -> list[tuple[str, dict[str, str], float]]:
    """Texto Prometheus -> [(nombre, etiquetas, valor)]."""
    samples = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if m:
            labels = dict(LABEL_RE.findall(m.group(2) or ""))
            samples.append((m.group(1), labels, float(m.group(3))))
    return samples


def snapshot(samples) -> dict:
    """Agrega las series que interesan (sumando entre rutas y workers)."""
    snap: dict = defaultdict(float)
    buckets: dict[float, float] = defaultdict(float)
    for name, labels, value in samples:
        if name == "http_request_duration_seconds_bucket":
            le = labels.get("le", "+Inf")
            buckets[math.inf if le == "+Inf" else float(le)] += value
        elif name == "http_request_duration_seconds_sum":
            snap["lat_sum"] += value
        elif name == "http_request_duration_seconds_count":
            snap["lat_count"] += value
        elif name == "http_requests_total":
            snap["requests"] += value
            if labels.get("status", "").startswith("5"):
                snap["errors_5xx"] += value
        elif name == "http_requests_in_progress":
            snap["in_progress"] += value
        elif name in (
            "container_cpu_usage_seconds_total",
            "container_cpu_limit_cores",
            "container_memory_bytes",
            "container_memory_limit_bytes",
            "db_pool_connections_in_use",
        ):
            snap[name] = value
    snap["buckets"] = dict(buckets)
    return snap


def quantile(q: float, before: dict[float, float], after: dict[float, float]) -> float | None:
    """Cuantil (en ms) de las observaciones del intervalo, a partir de buckets acumulados."""
    bounds = sorted(after)
    deltas = [after[b] - before.get(b, 0.0) for b in bounds]
    total = deltas[-1] if deltas else 0
    if total <= 0:
        return None
    target = q * total
    prev_bound, prev_count = 0.0, 0.0
    for bound, count in zip(bounds, deltas, strict=True):
        if count >= target:
            if math.isinf(bound):
                return prev_bound * 1000  # cae en el último tramo: se informa su límite inferior
            frac = (target - prev_count) / (count - prev_count) if count > prev_count else 0
            return (prev_bound + (bound - prev_bound) * frac) * 1000
        prev_bound, prev_count = bound, count
    return None


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 (URL local controlada)
        return resp.read().decode("utf-8")


DOCKER_FORMAT = "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.NetIO}},{{.BlockIO}}"


def docker_stats() -> list[list[str]]:
    """Una muestra de `docker stats` (CPU %, memoria, red y disco por contenedor)."""
    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", DOCKER_FORMAT],
            capture_output=True, text=True, timeout=20, check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.split(",") for line in out.strip().splitlines() if line.count(",") == 4]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8000/metrics")
    parser.add_argument("--out", required=True)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--duration", type=float, default=0, help="segundos (0 = sin límite)")
    parser.add_argument("--stop-file", default=None, help="se detiene cuando este archivo exista")
    parser.add_argument("--docker", action="store_true", help="registrar también docker stats")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    docker_out = out.with_name("docker-stats.csv")
    columns = [
        "timestamp", "segundo", "cpu_pct_del_limite", "cpu_nucleos_usados", "memoria_mb",
        "memoria_pct_del_limite", "pool_bd_en_uso", "peticiones_en_curso", "peticiones_por_s",
        "errores_5xx_por_s", "latencia_promedio_ms", "latencia_p95_ms", "latencia_p99_ms",
    ]
    start = time.time()
    prev = None
    prev_t = None
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        dwriter = None
        dfh = None
        if args.docker:
            dfh = docker_out.open("w", newline="", encoding="utf-8")
            dwriter = csv.writer(dfh)
            dwriter.writerow(["timestamp", "segundo", "contenedor", "cpu_pct", "memoria", "red_io", "disco_io"])
        try:
            while True:
                now = time.time()
                if args.duration and now - start > args.duration:
                    break
                if args.stop_file and Path(args.stop_file).exists():
                    break
                try:
                    snap = snapshot(parse(fetch(args.url)))
                except OSError as exc:
                    print(f"[métricas] sin respuesta de {args.url}: {exc}")
                    time.sleep(args.interval)
                    continue
                if prev is not None:
                    dt = now - prev_t
                    cpu = snap.get("container_cpu_usage_seconds_total", 0) - prev.get("container_cpu_usage_seconds_total", 0)
                    limit = snap.get("container_cpu_limit_cores") or 0
                    mem = snap.get("container_memory_bytes", 0)
                    mem_limit = snap.get("container_memory_limit_bytes") or 0
                    reqs = snap["requests"] - prev["requests"]
                    count = snap["lat_count"] - prev["lat_count"]
                    avg = (snap["lat_sum"] - prev["lat_sum"]) / count * 1000 if count > 0 else None
                    p95 = quantile(0.95, prev["buckets"], snap["buckets"])
                    p99 = quantile(0.99, prev["buckets"], snap["buckets"])
                    fmt = lambda v: "" if v is None else round(v, 2)  # noqa: E731
                    writer.writerow([
                        time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
                        round(now - start, 1),
                        fmt(cpu / dt / limit * 100 if limit else None),
                        fmt(cpu / dt),
                        fmt(mem / 1048576),
                        fmt(mem / mem_limit * 100 if mem_limit else None),
                        fmt(snap.get("db_pool_connections_in_use")),
                        fmt(snap.get("in_progress")),
                        fmt(reqs / dt),
                        fmt((snap["errors_5xx"] - prev["errors_5xx"]) / dt),
                        fmt(avg),
                        fmt(p95),
                        fmt(p99),
                    ])
                    fh.flush()
                if dwriter is not None:
                    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
                    for row in docker_stats():
                        dwriter.writerow([stamp, round(now - start, 1), *row])
                    dfh.flush()
                prev, prev_t = snap, now
                time.sleep(max(0.0, args.interval - (time.time() - now)))
        except KeyboardInterrupt:
            pass
        finally:
            if dfh:
                dfh.close()
    print(f"[métricas] guardadas en {out}")


if __name__ == "__main__":
    main()
