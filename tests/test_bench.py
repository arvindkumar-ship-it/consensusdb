from bench.bench import make_jobs, run_phase


def test_phase_counts_errors():
    send = lambda path, body: {"error": "x"} if "7" in body["sql"] else {"ok": True}
    r = run_phase("t", [("/sql", {"sql": f"s{i}"}) for i in range(20)], 4, send)
    assert r["ops"] == 20 and r["errors"] == 2          # s7, s17


def test_jobs_shape():
    j = make_jobs(["a", "b"], 10)
    assert len(j["ins"]) == 20 and len(j["scan"]) == 4 and j["ddl"][0][0] == "/sql"


def test_median_run_skips_cold_outlier():
    from bench.compare import median_run
    runs = [{"ops_per_sec": 145.0}, {"ops_per_sec": 1100.0}, {"ops_per_sec": 1090.0}]
    m = median_run(runs)
    assert m["ops_per_sec"] == 1090.0 and m["rounds"] == [145.0, 1100.0, 1090.0]