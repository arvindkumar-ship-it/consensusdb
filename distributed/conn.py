"""Keep-alive JSON POST. Windows pe har naya TCP connect ~15 ms leta hai (naapa gaya),
isliye har thread apna connection (host, port) ke hisaab se reuse karta hai."""
import http.client
import json
import threading

_tls = threading.local()


def post_json(host, port, path, body, timeout):
    data = json.dumps(body).encode()
    conns = _tls.__dict__.setdefault("conns", {})
    key = (host, port)
    for attempt in (0, 1):
        c = conns.get(key)
        reused = c is not None
        if c is None:
            c = conns[key] = http.client.HTTPConnection(host, port, timeout=timeout)
        c.timeout = timeout
        if c.sock:
            c.sock.settimeout(timeout)
        try:
            c.request("POST", path, data, {"Content-Type": "application/json"})
            return json.loads(c.getresponse().read())
        except (OSError, http.client.HTTPException) as e:
            c.close()
            conns.pop(key, None)
            # sirf stale keep-alive (server ne idle conn band kiya) pe ek baar retry; timeout pe nahi (double-apply ka darr)
            if attempt == 0 and reused and isinstance(e, (ConnectionError, http.client.RemoteDisconnected)):
                continue
            raise OSError(str(e)) from e
