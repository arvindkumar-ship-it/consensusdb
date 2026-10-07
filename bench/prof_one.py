import socket, statistics as st, sys, time
port = int(sys.argv[1]); lat = []
for _ in range(60):
    t = time.perf_counter()
    try:
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
    except OSError:
        print(port, "refused"); sys.exit()
    lat.append((time.perf_counter() - t) * 1000)
print(port, "connect p50/max ms:", round(st.median(lat), 2), round(max(lat), 2))