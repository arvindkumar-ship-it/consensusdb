"""mkdb ko Raft ki state machine banane wala wrapper.

Har Raft node apna alag mkdb_server process chalata hai (127.0.0.1:<port>) aur
apply(cmd) ke through SQL line bhejta hai. Protocol (server_core.cpp):
    client -> "<SQL>\n"
    server -> "$<n>\r\n<payload n bytes>\r\n"   ya   "-ERR <msg>\r\n"

Design:
  * Raft log hi source of truth hai. Start pe mkdb ki db file DELETE hoti hai aur
    log se replay hota hai (RaftNode.last_applied bhi restart pe 0 se shuru hota hai),
    isliye double-apply nahi hota.
  * SQL error (duplicate key waghairah) har replica pe same aata hai, to apply()
    use nigal leta hai. Connection/process ka error OSError ban ke bahar jaata hai.
"""
import os
import socket
import subprocess
import time

DEFAULT_BIN = r"D:\mkdb\build\mkdb_server.exe"
DEFAULT_DLL_DIR = r"D:\msys64\ucrt64\bin"   # libstdc++/libgcc/winpthread DLLs


class SqlError(Exception):
    """mkdb ne -ERR diya. Deterministic hai, har replica pe same aayega."""


class MkdbSM:
    def __init__(self, node_id, port, data_dir="data", host="127.0.0.1",
                 exe=None, dll_dir=None):
        self.node_id, self.port, self.host = node_id, port, host
        self.exe = exe or os.environ.get("MKDB_SERVER", DEFAULT_BIN)
        self.dll_dir = dll_dir or os.environ.get("MKDB_DLL_DIR", DEFAULT_DLL_DIR)
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, f"{node_id}.mkdb")
        self.proc = None
        self.sock = None
        self.rf = None
        self._wipe()
        self._start_server()
        self._connect()

    # ---- process / connection ----
    def _wipe(self):
        for p in (self.db_path, self.db_path + "-journal"):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
            except PermissionError:
                raise OSError(f"{p} locked: purana mkdb_server ({self.node_id}) abhi chal raha hai, "
                              "use band kar")

    def _start_server(self):
        env = os.environ.copy()
        env["PATH"] = self.dll_dir + os.pathsep + env.get("PATH", "")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.logf = open(self.db_path + ".log", "wb")
        self.proc = subprocess.Popen(
            [self.exe, self.db_path, str(self.port), self.host],
            stdout=self.logf, stderr=subprocess.STDOUT,
            env=env, creationflags=flags)

    def _log_tail(self):
        try:
            with open(self.db_path + ".log", "rb") as f:
                return f.read()[-200:].decode(errors="replace").strip()
        except OSError:
            return ""

    def _connect(self, timeout=5.0):
        deadline = time.time() + timeout
        while True:
            try:
                s = socket.create_connection((self.host, self.port), timeout=5)
            except OSError:
                if self.proc and self.proc.poll() is not None:
                    raise OSError(f"mkdb_server band ho gaya (exit {self.proc.returncode}): {self._log_tail()}")
                if time.time() > deadline:
                    raise
                time.sleep(0.05)
                continue
            time.sleep(0.3)   # bind fail hua to process turant mar jaata hai; kisi aur ke listener se mat judo
            if self.proc and self.proc.poll() is not None:
                s.close()
                raise OSError(f"mkdb_server start nahi hua (port {self.port} kisi aur ke paas?): {self._log_tail()}")
            self.sock = s
            self.rf = s.makefile("rb")
            return

    def _drop_conn(self):
        for x in (self.rf, self.sock):
            try:
                if x:
                    x.close()
            except OSError:
                pass
        self.rf = self.sock = None

    def close(self):
        try:
            if self.sock:
                self.sock.sendall(b"QUIT\n")
        except OSError:
            pass
        self._drop_conn()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    # ---- SQL ----
    def execute(self, sql: str) -> str:
        if "\n" in sql or "\r" in sql:
            raise SqlError("SQL me newline nahi chalega (line-based protocol)")
        if self.sock is None:
            self._connect()
        try:
            self.sock.sendall(sql.encode() + b"\n")
            head = self.rf.readline()
            if not head:
                rc = self.proc.poll() if self.proc else None
                raise ConnectionError(f"mkdb_server ne connection band kiya (exit={rc})")
            if head.startswith(b"-"):
                raise SqlError(head[1:].decode(errors="replace").strip())
            n = int(head[1:].strip())
            payload = self.rf.read(n)
            self.rf.readline()                      # trailing \r\n
            return payload.decode(errors="replace")
        except (OSError, ValueError):
            self._drop_conn()                       # agli call reconnect karegi
            raise

    # ---- Raft state machine interface ----
    def apply(self, cmd: str):
        try:
            return self.execute(cmd)
        except SqlError:
            return None

    def query(self, sql: str) -> str:
        """Local read (leader/follower jahan bhi). Linearizable read baad me."""
        return self.execute(sql)
