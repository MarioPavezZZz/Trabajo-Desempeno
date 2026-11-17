"""Análisis de las corridas de carga de TCGMASTER (Fase 2).

Lee las carpetas de `loadtest/results/` indicadas y genera, en una carpeta de
salida (por defecto `docs/fase2/`):

  graficos/<corrida>-serie.png   evolución en el tiempo: carga ofrecida y VUs,
                                 throughput, latencia (cliente y servidor),
                                 errores, CPU (host con %steal y contenedores),
                                 memoria, disco y red.
  graficos/comparacion-latencia.png   p50/p90/p95/p99 por escenario.
  graficos/comparacion-recursos.png   CPU y memoria máximas/promedio por escenario.
  graficos/saturacion.png        curva latencia/errores vs. throughput (corrida de estrés).
  graficos/web-vitals.png        LCP, INP, CLS y TTFB de los navegadores reales por escenario.
  tablas.md                      todas las tablas del informe (generadas, no editar a mano).
  corridas/<corrida>/            copia de los reportes de k6 (HTML/JSON) y CSV, para entregarlos.

Fuentes por corrida:
  summary.json        resumen de k6 (percentiles por endpoint, grupo y escenario).
  report.html         dashboard de k6: contiene la serie de tiempo cada 10 s
                      (eventos "snapshot" comprimidos en gzip+base64).
  server-metrics.csv  /metrics de la API cada 5 s (scrape_metrics.py).
  host.csv / containers.csv  recursos de la VM (remote_stats.sh).

Uso (requiere matplotlib; ver loadtest/analizar.ps1, que lo corre en Docker):
  python loadtest/tools/analizar.py --out docs/fase2 \
      --corrida "baja=loadtest/results/baja-azure-..." \
      --navegadores "baja=loadtest/results/navegadores-azure-baja-..." ...
"""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TZ = ZoneInfo("America/Santiago")

# Paleta sobria y legible en impresión (consistente en todos los gráficos).
C = {
    "p50": "#3B6E8F", "p90": "#7FA7C1", "p95": "#C77B30", "p99": "#9E2B25",
    "srv": "#5B8C5A", "vus": "#888888", "err": "#9E2B25", "rps": "#13241E",
    "user": "#3B6E8F", "system": "#7FA7C1", "iowait": "#C7A43A", "steal": "#9E2B25",
    "api": "#C77B30", "db": "#3B6E8F", "web": "#5B8C5A", "caddy": "#888888",
}
plt.rcParams.update({
    "figure.dpi": 110, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3,
    "axes.spines.top": False, "axes.spines.right": False, "legend.fontsize": 8,
})

TREND_KEYS = ["avg", "med", "p(90)", "p(95)", "p(99)", "max"]


# --------------------------------------------------------------------------- lectura

def read_csv(path: Path) -> list[dict]:
    """CSV -> lista de dicts (vacía si el archivo no existe)."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def num(value, default=None):
    """Convierte a float tolerando vacíos y sufijos (%)."""
    try:
        return float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return default


def size_mb(text: str) -> float | None:
    """'162MiB' / '1.2GiB' / '950kB' -> MB."""
    m = re.match(r"\s*([\d.]+)\s*([KMGT]?i?B)", text or "")
    if not m:
        return None
    factor = {"B": 1 / 1048576, "kB": 1 / 1024, "KiB": 1 / 1024, "KB": 1 / 1024, "MB": 1, "MiB": 1,
              "GB": 1024, "GiB": 1024, "TB": 1048576, "TiB": 1048576}.get(m.group(2), 1)
    return float(m.group(1)) * factor


def local_epoch(stamp: str) -> float:
    """Marca ISO sin zona (hora de Chile) -> epoch."""
    return datetime.fromisoformat(stamp).replace(tzinfo=TZ).timestamp()


def k6_timeseries(report: Path) -> tuple[float | None, dict[str, list]]:
    """Serie de tiempo del dashboard de k6 (un punto cada 10 s).

    El HTML exportado guarda un stream de eventos JSON (gzip+base64). Los
    eventos "metric" declaran métricas nuevas; cada "snapshot" es una lista
    posicional (en orden alfabético de las métricas declaradas hasta ese
    momento) con los agregados del período (trend: avg, max, med, min, p90,
    p95, p99; counter: count, rate; rate: rate; gauge: value).
    """
    if not report.exists():
        return None, {}
    html = report.read_text(encoding="utf-8")
    m = re.search(r'<script id="data"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None, {}
    events = [json.loads(line) for line in gzip.decompress(base64.b64decode(m.group(1).strip())).decode().splitlines()]
    names: list[str] = []
    start = None
    series: dict[str, list] = {}
    for ev in events:
        if ev["event"] == "metric":
            names += list(ev["data"].keys())
        elif ev["event"] == "start":
            start = ev["data"][0][0] / 1000
        elif ev["event"] == "snapshot":
            # Cada snapshot sigue el orden ALFABÉTICO de las métricas declaradas hasta ese momento.
            row = dict(zip(sorted(names), ev["data"], strict=False))
            t = row.get("time", [None])[0]
            if t is None:
                continue
            series.setdefault("t", []).append(t / 1000)
            for key, idx, name in (
                ("vus", 0, "vus"), ("rps", 1, "http_reqs"), ("fail", 0, "http_req_failed"),
                ("iter_rate", 1, "iterations"), ("dropped", 0, "dropped_iterations"),
            ):
                vals = row.get(name) or []
                series.setdefault(key, []).append(vals[idx] if len(vals) > idx else None)
            dur = row.get("http_req_duration") or []
            # Orden de agregados trend: avg, max, med, min, p90, p95, p99.
            for key, idx in (("avg", 0), ("max", 1), ("p50", 2), ("p90", 4), ("p95", 5), ("p99", 6)):
                series.setdefault(key, []).append(dur[idx] if len(dur) > idx else None)
    return start, series


def container_series(rows: list[dict]) -> dict[str, dict[str, list]]:
    """containers.csv -> {servicio: {t, cpu, mem}} (cpu en % de 1 núcleo)."""
    out: dict[str, dict[str, list]] = {}
    for r in rows:
        name = re.sub(r"^tcgmaster-|-\d+$", "", r["contenedor"])
        s = out.setdefault(name, {"t": [], "cpu": [], "mem": []})
        s["t"].append(float(r["epoch"]))
        s["cpu"].append(num(r["cpu_pct"], 0.0))
        s["mem"].append(size_mb(r["memoria"].split("/")[0]))
    return out


class Run:
    """Una corrida de k6 con todas sus fuentes alineadas en segundos desde el inicio."""

    def __init__(self, label: str, path: Path, browsers: Path | None = None):
        self.label = label
        self.path = path
        self.browsers = browsers
        self.summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
        self.metrics = self.summary["metrics"]
        self.params = dict(
            line.split("=", 1) for line in (path / "parametros.txt").read_text(encoding="utf-8-sig").splitlines() if "=" in line
        )
        self.start, self.k6 = k6_timeseries(path / "report.html")
        self.server = read_csv(path / "server-metrics.csv")
        self.host = read_csv(path / "host.csv")
        self.containers = container_series(read_csv(path / "containers.csv"))
        if self.start is None:  # sin dashboard: se usa la fecha de parametros.txt
            self.start = local_epoch(self.params["fecha"])
        # scrape_metrics.py omitía las rutas con {parámetros} hasta su corrección (19:35 del 16-11-2026).
        self.server_partial = self.params.get("fecha", "") < "2026-11-16T19:35"
        self.browser_summary = None
        if browsers and (browsers / "summary.json").exists():
            self.browser_summary = json.loads((browsers / "summary.json").read_text(encoding="utf-8"))["metrics"]

    # --- utilidades
    def rel(self, epochs):
        return [e - self.start for e in epochs]

    def trend(self, name: str) -> dict:
        return (self.metrics.get(name) or {}).get("values", {})

    def count(self, name: str) -> float:
        return (self.metrics.get(name) or {}).get("values", {}).get("count", 0)

    @property
    def duration_s(self) -> float:
        return self.summary["state"]["testRunDurationMs"] / 1000

    def host_col(self, col):
        return [num(r[col], 0.0) for r in self.host]

    def host_t(self):
        return self.rel([float(r["epoch"]) for r in self.host])

    def server_t(self):
        return self.rel([local_epoch(r["timestamp"]) for r in self.server])

    def server_col(self, col):
        return [num(r[col]) for r in self.server]


# --------------------------------------------------------------------------- gráficos

def plot_run(run: Run, out: Path) -> None:
    """Panel de 6 gráficos con la evolución de la corrida en el tiempo."""
    fig, ax = plt.subplots(3, 2, figsize=(12, 10), sharex=True)
    fig.suptitle(f"Corrida «{run.label}» — evolución en el tiempo", fontsize=12, fontweight="bold")
    k = run.k6
    kt = run.rel(k.get("t", []))

    # 1. Carga: VUs activos y throughput (cliente y servidor).
    a = ax[0][0]
    if kt:
        a.plot(kt, k["rps"], color=C["rps"], label="peticiones/s (k6)")
    if run.server:
        a.plot(run.server_t(), run.server_col("peticiones_por_s"), color=C["srv"], ls="--", label="peticiones/s API (/metrics)")
    a.set_ylabel("peticiones/s")
    a.set_title("Throughput")
    if kt:
        a2 = a.twinx()
        a2.plot(kt, k["vus"], color=C["vus"], alpha=0.6, label="VUs activos")
        a2.set_ylabel("VUs")
        a2.grid(False)
        a2.legend(loc="upper right")
    a.legend(loc="upper left")

    # 2. Latencia percibida por el cliente.
    a = ax[0][1]
    if kt:
        for key in ("p50", "p90", "p95", "p99"):
            a.plot(kt, k[key], color=C[key], label=f"{key} k6")
    if run.server:
        a.plot(run.server_t(), run.server_col("latencia_p95_ms"), color=C["srv"], ls="--", label="p95 API")
    a.set_ylabel("ms")
    a.set_title("Tiempo de respuesta (ventanas de 10 s)")
    a.set_yscale("symlog", linthresh=100)
    a.legend(ncol=2)

    # 3. Errores.
    a = ax[1][0]
    if kt:
        a.plot(kt, [100 * (v or 0) for v in k["fail"]], color=C["err"], label="% peticiones fallidas (k6)")
    if run.server:
        a.plot(run.server_t(), run.server_col("errores_5xx_por_s"), color=C["p95"], ls="--", label="5xx/s API")
    if kt and any(k.get("dropped") or []):
        a.plot(kt, [v or 0 for v in k["dropped"]], color=C["vus"], ls=":", label="sesiones descartadas por k6")
    a.set_title("Errores")
    a.legend()

    # 4. CPU del host (apilado) y contenedores.
    a = ax[1][1]
    if run.host:
        ht = run.host_t()
        stack = [run.host_col(f"cpu_{c}_pct") for c in ("user", "system", "iowait", "steal")]
        a.stackplot(ht, *stack, colors=[C["user"], C["system"], C["iowait"], C["steal"]], alpha=0.35,
                    labels=["host user", "host system", "host iowait", "host steal"])
    for name in ("api", "db", "web", "caddy"):
        s = run.containers.get(name)
        if s:
            a.plot(run.rel(s["t"]), [v / 2 for v in s["cpu"]], color=C[name], label=f"{name} (% de 2 vCPU)")
    a.set_ylim(0, 100)
    a.set_ylabel("% CPU de la VM")
    a.set_title("CPU (2 vCPU)")
    a.legend(ncol=2, fontsize=7)

    # 5. Memoria.
    a = ax[2][0]
    for name in ("api", "db", "web", "caddy"):
        s = run.containers.get(name)
        if s:
            a.plot(run.rel(s["t"]), s["mem"], color=C[name], label=name)
    if run.server:
        a3 = a.twinx()
        a3.plot(run.server_t(), run.server_col("pool_bd_en_uso"), color=C["vus"], ls=":", label="pool BD en uso")
        a3.set_ylabel("conexiones")
        a3.grid(False)
        a3.legend(loc="lower right")
    a.set_ylabel("MB")
    a.set_title("Memoria por contenedor (límite API y BD: 512 MB)")
    a.legend(ncol=2)
    a.set_xlabel("segundos desde el inicio")

    # 6. Disco y red del host.
    a = ax[2][1]
    if run.host:
        ht = run.host_t()
        a.plot(ht, run.host_col("red_tx_kbs"), color=C["p95"], label="red salida KB/s")
        a.plot(ht, run.host_col("red_rx_kbs"), color=C["p50"], label="red entrada KB/s")
        a.plot(ht, run.host_col("disco_escritura_kbs"), color=C["srv"], label="disco escritura KB/s")
        a.plot(ht, run.host_col("disco_lectura_kbs"), color=C["vus"], label="disco lectura KB/s")
    a.set_title("I/O del host")
    a.set_ylabel("KB/s")
    a.legend()
    a.set_xlabel("segundos desde el inicio")

    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def plot_latency_comparison(runs: list[Run], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    keys = [("med", "p50"), ("p(90)", "p90"), ("p(95)", "p95"), ("p(99)", "p99")]
    width = 0.2
    for i, (key, label) in enumerate(keys):
        vals = [r.trend("http_req_duration").get(key, 0) for r in runs]
        xs = [j + (i - 1.5) * width for j in range(len(runs))]
        bars = ax.bar(xs, vals, width, color=C[label], label=label)
        ax.bar_label(bars, fmt="%.0f", fontsize=7, padding=1)
    ax.set_xticks(range(len(runs)), [r.label for r in runs])
    ax.set_ylabel("ms (todas las peticiones, incluidas imágenes)")
    ax.set_yscale("log")
    ax.set_title("Tiempo de respuesta por escenario (k6)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def plot_resources(runs: list[Run], out: Path) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    width = 0.2
    for i, name in enumerate(("api", "db", "web", "caddy")):
        avgs, maxs = [], []
        for r in runs:
            s = r.containers.get(name, {}).get("cpu", [])
            avgs.append(sum(s) / len(s) if s else 0)
            maxs.append(max(s) if s else 0)
        xs = [j + (i - 1.5) * width for j in range(len(runs))]
        ax[0].bar(xs, maxs, width, color=C[name], alpha=0.35)
        ax[0].bar(xs, avgs, width, color=C[name], label=name)
    ax[0].set_xticks(range(len(runs)), [r.label for r in runs])
    ax[0].set_ylabel("% de 1 núcleo (sólido: promedio; claro: máximo)")
    ax[0].set_title("CPU por contenedor (límite API/BD: 100 %)")
    ax[0].legend()
    for i, name in enumerate(("api", "db")):
        maxs = [max(r.containers.get(name, {}).get("mem", [0]) or [0]) for r in runs]
        xs = [j + (i - 0.5) * 0.35 for j in range(len(runs))]
        bars = ax[1].bar(xs, maxs, 0.35, color=C[name], label=name)
        ax[1].bar_label(bars, fmt="%.0f", fontsize=7)
    ax[1].axhline(512, color=C["err"], ls="--", lw=1, label="límite 512 MB")
    ax[1].set_xticks(range(len(runs)), [r.label for r in runs])
    ax[1].set_ylabel("MB")
    ax[1].set_title("Memoria máxima")
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def saturation(run: Run) -> list[dict]:
    """Ventanas de 10 s de la corrida: throughput, VUs, p95, errores y CPU de la API."""
    k = run.k6
    api = run.containers.get("api", {})
    api_t = run.rel(api.get("t", []))
    rows = []
    for i, t in enumerate(run.rel(k.get("t", []))):
        cpu = [c for tt, c in zip(api_t, api.get("cpu", []), strict=False) if t - 10 <= tt <= t]
        rows.append({
            "t": t, "rps": k["rps"][i] or 0, "vus": k["vus"][i] or 0, "p95": k["p95"][i] or 0,
            "p99": k["p99"][i] or 0, "fail": 100 * (k["fail"][i] or 0),
            "api_cpu": sum(cpu) / len(cpu) if cpu else None,
        })
    return rows


def plot_saturation(run: Run, out: Path) -> dict:
    """Curva de saturación: latencia y errores vs. throughput logrado."""
    rows = [r for r in saturation(run) if r["rps"] > 0]
    if not rows:
        return {}
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.3))
    sc = ax[0].scatter([r["rps"] for r in rows], [r["p95"] for r in rows], c=[r["t"] for r in rows], cmap="viridis", s=18)
    ax[0].set_yscale("log")
    ax[0].axhline(800, color=C["err"], ls="--", lw=1, label="umbral p95 800 ms")
    ax[0].set_xlabel("throughput logrado (peticiones/s)")
    ax[0].set_ylabel("p95 de la ventana (ms)")
    ax[0].set_title("Latencia vs. throughput (color = tiempo)")
    ax[0].legend()
    fig.colorbar(sc, ax=ax[0], label="segundos")
    t = [r["t"] for r in rows]
    ax[1].plot(t, [r["rps"] for r in rows], color=C["rps"], label="peticiones/s")
    ax[1].plot(t, [r["vus"] for r in rows], color=C["vus"], label="VUs activos")
    ax[1].set_xlabel("segundos")
    ax[1].set_title("Throughput, usuarios concurrentes y errores")
    a2 = ax[1].twinx()
    a2.plot(t, [r["fail"] for r in rows], color=C["err"], label="% errores")
    a2.plot(t, [r["api_cpu"] or 0 for r in rows], color=C["api"], ls="--", label="CPU API (% de su límite)")
    a2.set_ylabel("%")
    a2.grid(False)
    ax[1].legend(loc="upper left")
    a2.legend(loc="center left")
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)

    # Punto de degradación: primera ventana con p95 > 800 ms o errores > 1 %.
    knee = next((r for r in rows if r["p95"] > 800 or r["fail"] > 1), None)
    best = max(rows, key=lambda r: r["rps"])
    return {"knee": knee, "max_rps": best, "label": run.label}


def plot_web_vitals(runs: list[Run], out: Path) -> None:
    runs = [r for r in runs if r.browser_summary]
    if not runs:
        return
    vitals = [("lcp", "LCP (ms)", 2500), ("inp", "INP (ms)", 200), ("cls", "CLS", 0.1), ("ttfb", "TTFB (ms)", 800)]
    fig, ax = plt.subplots(1, 4, figsize=(13, 3.6))
    for a, (key, title, good) in zip(ax, vitals, strict=True):
        vals = [(r.browser_summary.get(f"browser_web_vital_{key}") or {}).get("values", {}) for r in runs]
        p75 = [v.get("p(75)", 0) for v in vals]
        p95 = [v.get("p(95)", 0) for v in vals]
        xs = range(len(runs))
        a.bar([x - 0.18 for x in xs], p75, 0.36, color=C["p50"], label="p75")
        a.bar([x + 0.18 for x in xs], p95, 0.36, color=C["p95"], label="p95")
        a.axhline(good, color=C["srv"], ls="--", lw=1, label="umbral «bueno»")
        a.set_xticks(list(xs), [r.label for r in runs])
        a.set_title(title)
    ax[0].legend()
    fig.suptitle("Core Web Vitals medidos por navegadores reales (k6 browser) durante cada escenario")
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- tablas

def fmt(v, d=0):
    if v is None:
        return "—"
    return f"{v:,.{d}f}".replace(",", " ")


def max_of(values):
    vals = [v for v in values if v is not None]
    return max(vals) if vals else None


def avg_of(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def tables(runs: list[Run], sat: dict) -> str:
    md = ["# Tablas de resultados (generadas por loadtest/tools/analizar.py)\n"]

    md.append("## Resumen por escenario (lado cliente, k6)\n")
    md.append("| Escenario | Duración | Peticiones | Throughput medio (req/s) | Throughput máx. 10 s | Sesiones | Promedio | Mediana | p90 | p95 | p99 | Máx. | Errores | Checks | Compras aprob. / rech. | Sin stock (409) |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        d = r.trend("http_req_duration")
        reqs = r.metrics["http_reqs"]["values"]
        md.append(
            f"| {r.label} | {fmt(r.duration_s / 60, 1)} min | {fmt(reqs['count'])} | {fmt(reqs['rate'], 1)} | "
            f"{fmt(max_of(r.k6.get('rps', [])), 1)} | {fmt(r.count('iterations'))} | {fmt(d.get('avg'), 1)} | "
            f"{fmt(d.get('med'), 1)} | {fmt(d.get('p(90)'), 1)} | {fmt(d.get('p(95)'), 1)} | {fmt(d.get('p(99)'), 1)} | "
            f"{fmt(d.get('max'))} | {fmt(100 * r.metrics['http_req_failed']['values']['rate'], 2)} % | "
            f"{fmt(100 * r.metrics['checks']['values']['rate'], 2)} % | "
            f"{fmt(r.count('compras_aprobadas'))} / {fmt(r.count('compras_rechazadas'))} | {fmt(r.count('sin_stock_409'))} |"
        )
    md.append("\nTiempos en ms. «Errores» = respuestas 4xx/5xx o sin respuesta (un 409 por falta de stock no cuenta como error).\n")

    md.append("## Tiempo de respuesta por tipo de operación (p95, ms)\n")
    groups = ["navegacion", "carrito", "checkout"]
    md.append("| Escenario | " + " | ".join(groups) + " | sesión completa (mediana, s) |")
    md.append("|---|" + "---|" * (len(groups) + 1))
    for r in runs:
        cells = [fmt(r.trend(f"http_req_duration{{grupo:{g}}}").get("p(95)"), 1) for g in groups]
        md.append(f"| {r.label} | " + " | ".join(cells) + f" | {fmt((r.trend('duracion_sesion').get('med') or 0) / 1000, 1)} |")

    md.append("\n## Tiempo de respuesta por endpoint (p95 / p99, ms)\n")
    endpoints = sorted({k[len("http_req_duration{name:"):-1] for r in runs for k in r.metrics if k.startswith("http_req_duration{name:")})
    md.append("| Endpoint | " + " | ".join(r.label for r in runs) + " |")
    md.append("|---|" + "---|" * len(runs))
    for ep in endpoints:
        cells = []
        for r in runs:
            v = r.trend(f"http_req_duration{{name:{ep}}}")
            cells.append(f"{fmt(v.get('p(95)'), 1)} / {fmt(v.get('p(99)'), 1)}" if v and v.get("max") else "—")
        md.append(f"| `{ep}` | " + " | ".join(cells) + " |")

    md.append("\n## Recursos del servidor (VM 2 vCPU, 8 GB)\n")
    md.append("| Escenario | CPU host prom. / máx. (%) | %steal máx. | %iowait máx. | Carga (load1) máx. | CPU API prom. / máx. (% de 1 núcleo) | CPU BD prom. / máx. | CPU Nginx máx. | CPU Caddy máx. | Mem. API máx. (MB) | Mem. BD máx. (MB) | Pool BD máx. | Disco escr. máx. (KB/s) | Red salida prom. / máx. (KB/s) |")
    md.append("|---|" + "---|" * 13)
    for r in runs:
        busy = [100 - v for v in r.host_col("cpu_idle_pct")] if r.host else []
        cs = r.containers

        def cpu(name, fn, cs=cs):
            return fn(cs.get(name, {}).get("cpu", []))
        md.append(
            f"| {r.label} | {fmt(avg_of(busy), 1)} / {fmt(max_of(busy), 1)} | {fmt(max_of(r.host_col('cpu_steal_pct')), 1)} | "
            f"{fmt(max_of(r.host_col('cpu_iowait_pct')), 1)} | {fmt(max_of(r.host_col('load1')), 2)} | "
            f"{fmt(cpu('api', avg_of), 1)} / {fmt(cpu('api', max_of), 1)} | {fmt(cpu('db', avg_of), 1)} / {fmt(cpu('db', max_of), 1)} | "
            f"{fmt(cpu('web', max_of), 1)} | {fmt(cpu('caddy', max_of), 1)} | "
            f"{fmt(max_of(cs.get('api', {}).get('mem', [])))} | {fmt(max_of(cs.get('db', {}).get('mem', [])))} | "
            f"{fmt(max_of(r.server_col('pool_bd_en_uso')))} | {fmt(max_of(r.host_col('disco_escritura_kbs')))} | "
            f"{fmt(avg_of(r.host_col('red_tx_kbs')))} / {fmt(max_of(r.host_col('red_tx_kbs')))} |"
        )

    md.append("\n## Lado servidor (/metrics de la API, ventanas de 5 s)\n")
    md.append("Solo peticiones a la API (las imágenes las sirve Nginx). Las corridas anteriores a la "
              "corrección de `scrape_metrics.py` omiten en req/s y latencia las rutas con parámetros "
              "(`{slug}`, `{transaction_id}`); se marcan con *.\n")
    md.append("| Escenario | req/s API prom. / máx. | Latencia API prom. (ms) | p95 API máx. (ms) | p99 API máx. (ms) | Peticiones en curso máx. | 5xx totales aprox. |")
    md.append("|---|---|---|---|---|---|---|")
    for r in runs:
        five = r.server_col("errores_5xx_por_s")
        md.append(
            f"| {r.label}{' *' if r.server_partial else ''} | {fmt(avg_of(r.server_col('peticiones_por_s')), 1)} / {fmt(max_of(r.server_col('peticiones_por_s')), 1)} | "
            f"{fmt(avg_of(r.server_col('latencia_promedio_ms')), 1)} | {fmt(max_of(r.server_col('latencia_p95_ms')), 0)} | "
            f"{fmt(max_of(r.server_col('latencia_p99_ms')), 0)} | {fmt(max_of(r.server_col('peticiones_en_curso')))} | "
            f"{fmt(sum(v or 0 for v in five) * 5)} |"
        )

    if any(r.browser_summary for r in runs):
        md.append("\n## Core Web Vitals (navegadores reales, k6 browser)\n")
        md.append("| Escenario | LCP p75 / p95 (ms) | INP p75 / p95 (ms) | CLS p75 | FCP p75 (ms) | TTFB p75 / p95 (ms) | Páginas recorridas |")
        md.append("|---|---|---|---|---|---|---|")
        for r in runs:
            b = r.browser_summary
            if not b:
                continue

            def v(name, key, b=b):
                return (b.get(f"browser_web_vital_{name}") or {}).get("values", {}).get(key)
            md.append(
                f"| {r.label} | {fmt(v('lcp', 'p(75)'))} / {fmt(v('lcp', 'p(95)'))} | {fmt(v('inp', 'p(75)'))} / {fmt(v('inp', 'p(95)'))} | "
                f"{fmt(v('cls', 'p(75)'), 3)} | {fmt(v('fcp', 'p(75)'))} | {fmt(v('ttfb', 'p(75)'))} / {fmt(v('ttfb', 'p(95)'))} | "
                f"{fmt((b.get('iterations') or {}).get('values', {}).get('count', 0) * 3)} |"
            )
        md.append("\nUmbrales «buenos» de Google (p75): LCP ≤ 2 500 ms, INP ≤ 200 ms, CLS ≤ 0,1.")

    if sat:
        md.append(f"\n## Punto de saturación (corrida «{sat['label']}», ventanas de 10 s)\n")
        knee, best = sat.get("knee"), sat.get("max_rps")
        if best:
            md.append(f"- Throughput máximo sostenido en una ventana: **{fmt(best['rps'], 1)} req/s** "
                      f"(t = {fmt(best['t'])} s, {fmt(best['vus'])} VUs, p95 {fmt(best['p95'])} ms).")
        if knee:
            md.append(f"- Primera ventana degradada (p95 > 800 ms o errores > 1 %): t = {fmt(knee['t'])} s, "
                      f"{fmt(knee['rps'], 1)} req/s, {fmt(knee['vus'])} VUs, p95 {fmt(knee['p95'])} ms, "
                      f"errores {fmt(knee['fail'], 2)} %, CPU API {fmt(knee['api_cpu'], 0)} %.")
        else:
            md.append("- Ninguna ventana superó p95 > 800 ms ni 1 % de errores.")
    return "\n".join(md) + "\n"


# --------------------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--out", default="docs/fase2")
    parser.add_argument("--corrida", action="append", required=True, help="etiqueta=carpeta (en orden de carga)")
    parser.add_argument("--navegadores", action="append", default=[], help="etiqueta=carpeta de la corrida de navegadores paralela")
    parser.add_argument("--estres", default="estrés", help="etiqueta de la corrida de estrés (curva de saturación)")
    args = parser.parse_args()

    out = Path(args.out)
    graf = out / "graficos"
    graf.mkdir(parents=True, exist_ok=True)
    browsers = dict(item.split("=", 1) for item in args.navegadores)
    runs = []
    for item in args.corrida:
        label, folder = item.split("=", 1)
        runs.append(Run(label, Path(folder), Path(browsers[label]) if label in browsers else None))

    for r in runs:
        plot_run(r, graf / f"{r.label}-serie.png")
        dest = out / "corridas" / r.path.name
        dest.mkdir(parents=True, exist_ok=True)
        for f in r.path.iterdir():
            if f.is_file() and not f.name.startswith("."):
                shutil.copy2(f, dest / f.name)
        if r.browsers:
            bdest = out / "corridas" / r.browsers.name
            bdest.mkdir(parents=True, exist_ok=True)
            for f in r.browsers.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    shutil.copy2(f, bdest / f.name)
    plot_latency_comparison(runs, graf / "comparacion-latencia.png")
    plot_resources(runs, graf / "comparacion-recursos.png")
    plot_web_vitals(runs, graf / "web-vitals.png")
    sat = {}
    stress = next((r for r in runs if r.label == args.estres), None)
    if stress:
        sat = plot_saturation(stress, graf / "saturacion.png")
    (out / "tablas.md").write_text(tables(runs, sat), encoding="utf-8")
    print(f"Listo: {out}/tablas.md y {len(list(graf.glob('*.png')))} gráficos en {graf}")


if __name__ == "__main__":
    main()
