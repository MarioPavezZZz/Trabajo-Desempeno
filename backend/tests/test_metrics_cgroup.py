"""Tests del colector de CPU/memoria del contenedor (cgroups v2), sin base de datos."""

from app.core.metrics import CgroupCollector


def test_cgroup_collector_lee_cpu_y_memoria(tmp_path):
    (tmp_path / "cpu.stat").write_text("usage_usec 2500000\nuser_usec 1\n")
    (tmp_path / "cpu.max").write_text("100000 100000\n")
    (tmp_path / "memory.current").write_text("1048576\n")
    (tmp_path / "memory.max").write_text("max\n")
    metrics = {m.name: m.samples[0].value for m in CgroupCollector(tmp_path).collect()}
    assert metrics["container_cpu_usage_seconds"] == 2.5
    assert metrics["container_cpu_limit_cores"] == 1.0
    assert metrics["container_memory_bytes"] == 1048576
    assert "container_memory_limit_bytes" not in metrics  # "max" = sin límite


def test_cgroup_collector_sin_archivos_no_falla(tmp_path):
    assert list(CgroupCollector(tmp_path / "no-existe").collect()) == []
