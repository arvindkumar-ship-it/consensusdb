import { createContext, ReactNode, useContext, useEffect, useRef, useState } from "react";
import { Cluster, get } from "./api";

export type Evt = { id: number; t: number; text: string; tone: "ok" | "warn" | "info" };
type Recovery = { ms: number; node: string; term: number; at: number };
type Ctx = { cluster: Cluster | null; error: string | null; events: Evt[]; outage: Record<string, number>; recovery: Record<string, Recovery> };

const C = createContext<Ctx>({ cluster: null, error: null, events: [], outage: {}, recovery: {} });
export const useCluster = () => useContext(C);

export const leaderOf = (g?: { nodes: Record<string, any> }) =>
  g ? Object.entries(g.nodes).find(([, n]) => n.state === "LEADER") : undefined;

/** Ek jagah poll karta hai (har page share karta hai) aur snapshots ko diff karke events + failover recovery time nikalta hai. */
export function ClusterProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<Ctx>({ cluster: null, error: null, events: [], outage: {}, recovery: {} });
  const mem = useRef({ prevLeader: {} as Record<string, string | undefined>, prevState: {} as Record<string, string>, outage: {} as Record<string, number>, recovery: {} as Record<string, Recovery>, events: [] as Evt[], seq: 0 });

  useEffect(() => {
    let alive = true;
    const add = (text: string, tone: Evt["tone"]) => {
      const m = mem.current;
      m.events = [{ id: m.seq++, t: Date.now(), text, tone }, ...m.events].slice(0, 40);
    };
    const loop = async () => {
      while (alive) {
        try {
          const c = await get<Cluster>("/cluster");
          const m = mem.current, first = Object.keys(m.prevState).length === 0;
          for (const [g, info] of Object.entries(c.groups)) {
            if (!info.active) continue;
            for (const [n, nd] of Object.entries(info.nodes)) {
              const was = m.prevState[n];
              if (!first && was && was !== nd.state) {
                if (nd.state === "DOWN") add(`${n} went down`, "warn");
                else if (was === "DOWN") add(`${n} is back as ${nd.state.toLowerCase()}`, "ok");
              }
              m.prevState[n] = nd.state;
            }
            const lead = leaderOf(info);
            if (!lead) {
              if (!m.outage[g] && !first) { m.outage[g] = Date.now(); add(`${g} has no leader, election in progress`, "warn"); }
            } else {
              const [name, nd] = lead;
              if (m.outage[g]) {
                const ms = Date.now() - m.outage[g];
                m.recovery[g] = { ms, node: name, term: nd.term ?? 0, at: Date.now() };
                add(`${name} elected leader of ${g} (term ${nd.term}), recovered in ~${(ms / 1000).toFixed(1)} s`, "ok");
                delete m.outage[g];
              } else if (m.prevLeader[g] && m.prevLeader[g] !== name) {
                add(`Leadership of ${g} moved to ${name} (term ${nd.term})`, "info");
              }
              m.prevLeader[g] = name;
            }
          }
          setS({ cluster: c, error: null, events: m.events, outage: { ...m.outage }, recovery: { ...m.recovery } });
        } catch (e: any) {
          setS((p) => ({ ...p, error: e.message }));
        }
        await new Promise((r) => setTimeout(r, 400));
      }
    };
    loop();
    return () => { alive = false; };
  }, []);

  return <C.Provider value={s}>{children}</C.Provider>;
}
