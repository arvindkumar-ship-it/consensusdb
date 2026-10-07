import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from abtest.experiment import ExperimentManager, TrafficSplitter
from abtest.stats import welch


def test_splitter_is_sticky_and_roughly_even():
    s = TrafficSplitter("exp", 50)
    assert all(s.bucket(f"k{i}") == s.bucket(f"k{i}") for i in range(100))
    n = sum(s.bucket(f"k{i}") == "treatment" for i in range(10000))
    assert 4700 < n < 5300


def test_splitter_extremes():
    assert all(TrafficSplitter("e", 0).bucket(str(i)) == "control" for i in range(200))
    assert all(TrafficSplitter("e", 100).bucket(str(i)) == "treatment" for i in range(200))


def test_welch_detects_real_difference():
    rnd = random.Random(1)
    a = [rnd.gauss(50, 5) for _ in range(200)]
    b = [rnd.gauss(40, 5) for _ in range(200)]
    r = welch(a, b)
    assert r["significant"] and r["improvement_pct"] > 15


def test_welch_no_difference():
    rnd = random.Random(2)
    a = [rnd.gauss(50, 5) for _ in range(200)]
    b = [rnd.gauss(50, 5) for _ in range(200)]
    assert welch(a, b)["significant"] is False


def test_welch_small_sample_and_zero_variance():
    assert welch([1] * 5, [2] * 5)["significant"] is None
    assert welch([1.0] * 40, [1.0] * 40)["significant"] is False


def test_manager_flow():
    m = ExperimentManager()
    m.start("idx", 50)
    for i in range(400):
        bk = m.assign(f"q{i}")["idx"]
        m.record("idx", bk, 10.0 + (i % 7) if bk == "control" else 5.0 + (i % 7), ok=(i % 50 != 0))
    r = m.report("idx")
    assert r["significant"] and r["improvement_pct"] > 30 and r["error_rate_control"] > 0
    m.stop("idx")
    assert "error" in m.report("idx")
