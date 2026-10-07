import socket, statistics as st, time

def conn(port, n=60):
    lat = []
    for _ in range(n):
        t = time.perf_counter()
        try:
            socket.create_connection(("127.0.0.1", port), timeout=2).close()
        except OSError:
            return "refused"
        lat.append((time.perf_counter() - t) * 1000)
    return round(st.median(lat), 2), round(max(lat), 2)

for name, port in [("trivial srv", 29200), ("router", 8000), ("node g1n1", 8001), ("node g2n1", 8011),
                   ("mkdb g1n1", 28001), ("mkdb g2n1", 28011)]:
    print(f"{name:12} {port}: {conn(port)}")