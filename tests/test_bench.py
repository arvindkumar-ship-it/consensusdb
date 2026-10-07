from bench.bench import make_jobs, run_phase


def test_phase_counts_errors():
    send = lambda path, body: {"error": "x"} if "7" in body["sql"] else {"ok": True}
    r = run_phase("t", [("/sql", {"sql": f"s{i}"}) for i in range(20)], 4, send)
    assert r["ops"] == 20 and r["errors"] == 2          # s7, s17


def test_jobs_shape():
    j = make_jobs(["a", "b"], 10)
    assert len(j["ins"]) == 20 and len(j["scan"]) == 4 and j["ddl"][0][0] == "/sql"
