# ConsensusDB Console

React + Vite + TypeScript. Router (`router.py`) ke upar chalta hai.

## Chalane ka tareeka

```powershell
# 1. nodes + router (pehle jaisa)
.\start_all.ps1

# 2. frontend
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Router alag port pe ho to: `$env:ROUTER_URL="http://127.0.0.1:8100"; npm run dev`
Build: `VITE_API=http://host:8000 npm run build`

## router.py me naya

`/cluster`, `/metrics`, `/bench`, `/stats`, `/optimize/*`, `/ab/*`, `/rebalance/add`, CORS, `ROUTER_PORT`.
Raft, KV, SQL routing ka purana code same hai.

## Demo flow

1. Data explorer > Load test chalao. Overview me traffic aur g1/g2 split dikhega.
2. Cluster page kholo, kisi leader ka terminal band karo. Election banner aur recovery time dikhega.
3. SQL mode (`USE_MKDB=1`): Optimizer > Generate demo workload > Apply index > Measure impact.
4. Experiments: A/B start karo, test queries bhejo.
