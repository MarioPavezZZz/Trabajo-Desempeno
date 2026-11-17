"""Tests del recolector de métricas (solo biblioteca estándar).

    python -m unittest loadtest/tools/test_scrape_metrics.py
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import scrape_metrics as sm  # noqa: E402

TEXTO = """
# HELP http_requests_total Peticiones
# TYPE http_requests_total counter
http_requests_total{method="GET",route="/api/home",status="200"} 10.0
http_requests_total{method="GET",route="/api/products/{slug}",status="200"} 30.0
http_requests_total{method="GET",route="/api/orders/{transaction_id}",status="503"} 2.0
http_request_duration_seconds_bucket{le="0.1",method="GET",route="/api/products/{slug}"} 20.0
http_request_duration_seconds_bucket{le="+Inf",method="GET",route="/api/products/{slug}"} 30.0
http_request_duration_seconds_count{method="GET",route="/api/products/{slug}"} 30.0
http_request_duration_seconds_sum{method="GET",route="/api/products/{slug}"} 1.5
db_pool_connections_in_use 3.0
"""


class ParseTest(unittest.TestCase):
    def test_rutas_con_llaves_en_las_etiquetas(self):
        """Regresión: route="/api/products/{slug}" se ignoraba con la regex [^}]*."""
        names = [(n, labels.get("route")) for n, labels, _ in sm.parse(TEXTO)]
        self.assertIn(("http_requests_total", "/api/products/{slug}"), names)
        self.assertIn(("http_requests_total", "/api/orders/{transaction_id}"), names)

    def test_snapshot_suma_todas_las_rutas_y_cuenta_5xx(self):
        snap = sm.snapshot(sm.parse(TEXTO))
        self.assertEqual(snap["requests"], 42.0)
        self.assertEqual(snap["errors_5xx"], 2.0)
        self.assertEqual(snap["lat_count"], 30.0)
        self.assertEqual(snap["db_pool_connections_in_use"], 3.0)
        self.assertEqual(snap["buckets"], {0.1: 20.0, math.inf: 30.0})

    def test_metrica_sin_etiquetas(self):
        self.assertEqual(sm.parse("up 1"), [("up", {}, 1.0)])

    def test_cuantil_del_intervalo(self):
        antes = {0.1: 10.0, 0.5: 10.0, math.inf: 10.0}
        despues = {0.1: 10.0, 0.5: 20.0, math.inf: 20.0}  # las 10 nuevas cayeron entre 0,1 y 0,5 s
        p50 = sm.quantile(0.5, antes, despues)
        self.assertGreater(p50, 100)
        self.assertLessEqual(p50, 500)
        self.assertIsNone(sm.quantile(0.95, despues, despues))  # sin observaciones nuevas


if __name__ == "__main__":
    unittest.main()
