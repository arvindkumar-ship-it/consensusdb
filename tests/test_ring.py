from distributed.ring import Ring

def test_balanced():
    r = Ring(["g1", "g2"])
    c = {"g1": 0, "g2": 0}
    for i in range(1000):
        c[r.get(f"k{i}")] += 1
    assert min(c.values()) > 350

def test_minimal_movement():
    a, b = Ring(["g1", "g2"]), Ring(["g1", "g2", "g3"])
    moved = sum(a.get(f"k{i}") != b.get(f"k{i}") for i in range(1000))
    assert moved < 450