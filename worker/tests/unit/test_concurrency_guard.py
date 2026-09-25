import pytest

from tests import concurrency


@pytest.mark.parametrize("cpu_count", [None, 1, 2, 3])
def test_small_or_unknown_cpu_count_logs_without_bound(monkeypatch, capsys, cpu_count):
    monkeypatch.setattr(concurrency.os, "cpu_count", lambda: cpu_count)
    concurrency.assert_wall_time_budget(wall=10, median=1)
    output = capsys.readouterr().out
    assert f"cpu_count={cpu_count}" in output
    assert "wall=10.000000s" in output and "median=1.000000s" in output
    assert "enforce_2x_bound=False" in output


@pytest.mark.parametrize("cpu_count", [4, 8])
@pytest.mark.parametrize("wall", [2, 2.1])
def test_at_least_four_cpus_enforce_strict_bound(monkeypatch, cpu_count, wall):
    monkeypatch.setattr(concurrency.os, "cpu_count", lambda: cpu_count)
    with pytest.raises(AssertionError):
        concurrency.assert_wall_time_budget(wall=wall, median=1)


@pytest.mark.parametrize("cpu_count", [4, 8])
def test_at_least_four_cpus_allow_below_bound(monkeypatch, capsys, cpu_count):
    monkeypatch.setattr(concurrency.os, "cpu_count", lambda: cpu_count)
    concurrency.assert_wall_time_budget(wall=1.999, median=1)
    assert "enforce_2x_bound=True" in capsys.readouterr().out
