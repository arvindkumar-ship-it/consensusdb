import os
import socket

import pytest

from distributed.mkdb_sm import MkdbSM, DEFAULT_BIN, SqlError

EXE = os.environ.get("MKDB_SERVER", DEFAULT_BIN)
pytestmark = pytest.mark.skipif(not os.path.exists(EXE), reason="mkdb_server.exe build nahi hai")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


CMDS = [
    "CREATE TABLE t (id INT PRIMARY KEY, v TEXT)",
    "INSERT INTO t VALUES (1, 'one')",
    "INSERT INTO t VALUES (2, 'two')",
    "INSERT INTO t VALUES (1, 'dup')",      # duplicate key: SQL error, nigal lena chahiye
]


def test_apply_and_query(tmp_path):
    sm = MkdbSM("tn1", free_port(), data_dir=str(tmp_path))
    try:
        for c in CMDS:
            sm.apply(c)                      # dup wali command raise nahi karni chahiye
        out = sm.query("SELECT * FROM t")
        assert "1 | one" in out and "2 | two" in out
        assert "(2 rows)" in out
    finally:
        sm.close()


def test_sql_error_raised_by_execute(tmp_path):
    sm = MkdbSM("tn2", free_port(), data_dir=str(tmp_path))
    try:
        with pytest.raises(SqlError):
            sm.execute("this is not sql")
        assert sm.execute("CREATE TABLE x (id INT PRIMARY KEY)")   # connection zinda hai
    finally:
        sm.close()


def test_replay_gives_same_state(tmp_path):
    a = MkdbSM("rn", free_port(), data_dir=str(tmp_path))
    try:
        for c in CMDS:
            a.apply(c)
        before = a.query("SELECT * FROM t")
    finally:
        a.close()

    # restart: db wipe hoti hai, log se replay (Raft log yahan CMDS hai)
    b = MkdbSM("rn", free_port(), data_dir=str(tmp_path))
    try:
        for c in CMDS:
            b.apply(c)
        assert b.query("SELECT * FROM t") == before
    finally:
        b.close()
