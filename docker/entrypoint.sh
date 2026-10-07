#!/bin/bash
# Ek container me poora cluster: 6 raft nodes + router (sab 127.0.0.1 pe, code me koi badlav nahi).
# Router 127.0.0.1:8100 pe bind hota hai, socat usko 0.0.0.0:8000 pe expose karta hai.
set -u
cd /app
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null; exit 0; }
trap cleanup TERM INT

for n in g1n1 g1n2 g1n3 g2n1 g2n2 g2n3; do
    python run_node.py "$n" &
    pids+=($!)
done
sleep 3
ROUTER_PORT=8100 python router.py &
pids+=($!)
socat TCP-LISTEN:8000,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:8100 &
pids+=($!)

echo "consensusdb up: router http://localhost:8000 (USE_MKDB=${USE_MKDB:-0})"
wait -n
echo "ek process mar gaya, container band ho raha hai" >&2
cleanup