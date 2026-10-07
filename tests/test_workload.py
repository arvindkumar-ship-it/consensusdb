import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from workload import sqlinfo
from workload.recorder import WorkloadRecorder
from workload.schema import SchemaTracker


def test_parse_select_where():
    i = sqlinfo.parse("SELECT * FROM users WHERE email = 'a@b.c' AND age > 5")
    assert i["kind"] == "select" and i["table"] == "users"
    assert ("users", "email") in i["where_cols"] and ("users", "age") in i["where_cols"]


def test_parse_join_with_alias():
    i = sqlinfo.parse("SELECT * FROM users u JOIN orders o ON u.id = o.user_id WHERE o.total > 10")
    assert i["tables"] == ["users", "orders"]
    assert ("orders", "users") == ("orders", "users") and ("orders", "users") in [tuple(sorted(j)) for j in i["joins"]]
    assert ("orders", "total") in i["where_cols"]


def test_parse_insert_and_create():
    assert sqlinfo.parse("INSERT INTO t VALUES (1,'x')")["table"] == "t"
    assert sqlinfo.parse("create table Foo (id int)")["table"] == "foo"


def test_normalize_literals():
    assert sqlinfo.normalize("SELECT * FROM t WHERE id = 5") == sqlinfo.normalize("select * from t where id = 99")
    assert sqlinfo.normalize("SELECT * FROM t1 WHERE n='a'") == "select * from t1 where n=?"


def test_schema_tracks_ddl_pk_rows_index():
    s = SchemaTracker()
    s.observe("CREATE TABLE users (id INT PRIMARY KEY, email TEXT, age INT)")
    assert s.columns("users") == ["id", "email", "age"] and s.pk("users") == "id"
    s.observe("INSERT INTO users VALUES (1,'a',3)")
    s.observe("INSERT INTO users VALUES (2,'b',3),(3,'c',4)")
    assert s.rows("users") == 3
    s.observe("CREATE INDEX i ON users (email)")
    assert s.indexed("users") == {"id", "email"}
    s.observe("INSERT INTO users VALUES (9,'z',1)", ok=False)  # fail hui query count nahi hoti
    assert s.rows("users") == 3


def test_schema_default_pk_is_first_col():
    s = SchemaTracker()
    s.observe("CREATE TABLE t (a INT, b TEXT)")
    assert s.pk("t") == "a"


def test_full_scan_detection():
    r = WorkloadRecorder(persist=False)
    r.record("CREATE TABLE users (id INT, email TEXT)", "users", 1)
    assert r.record("SELECT * FROM users WHERE id = 1", "users", 1)["full_scan"] is False
    assert r.record("SELECT * FROM users WHERE email = 'x'", "users", 1)["full_scan"] is True
    assert r.record("SELECT * FROM users", "users", 1)["full_scan"] is True
    assert r.record("INSERT INTO users VALUES (1,'a')", "users", 1)["full_scan"] is False
    r.record("CREATE INDEX i ON users (email)", "users", 1)
    assert r.record("SELECT * FROM users WHERE email = 'x'", "users", 1)["full_scan"] is False


def test_recorder_persists_and_reloads(tmp_path):
    r = WorkloadRecorder(str(tmp_path))
    r.record("CREATE TABLE t (id INT, v TEXT)", "t", 2.0)
    r.record("SELECT * FROM t WHERE v = 'a'", "t", 5.0)
    r.close()
    r2 = WorkloadRecorder(str(tmp_path))
    assert len(r2.snapshot()) == 2 and r2.schema.exists("t")
    r2.close()
