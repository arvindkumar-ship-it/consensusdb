import { useState } from "react";
import { Plus, Server } from "lucide-react";
import { post } from "../api";
import { leaderOf, useCluster } from "../cluster-context";
import { Badge, Button, Confirm, Empty, ErrorNote, PageHead, Section, Skeleton, useToast } from "../ui";

const tone: Record<string, string> = { LEADER: "accent", FOLLOWER: "green", CANDIDATE: "amber", DOWN: "red" };
const clock = (t: number) => new Date(t).toLocaleTimeString("en-GB");

export default function ClusterPage() {
  const { cluster, error, events, outage, recovery } = useCluster();
  const toast = useToast();
  const [ask, setAsk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const addShard = async () => {
    setBusy(true);
    try {
      const r = await post("/rebalance/add", { group: ask }, 60000);
      if (r.error) toast(r.error, true);
      else toast(`${ask} added. ${Object.keys(r.moved ?? {}).length} items moved.`);
      setAsk(null);
    } catch (e: any) { toast(e.message, true); } finally { setBusy(false); }
  };

  const groups = cluster ? Object.entries(cluster.groups) : [];
  const active = groups.filter(([, g]) => g.active);
  const spare = groups.filter(([, g]) => !g.active);

  return (
    <>
      <PageHead title="Cluster" desc="Every node's Raft role, term and log position, refreshed about twice a second." />
      {error && !cluster && <ErrorNote title="Can't reach the router." text="Check that router.py is running on port 8000." />}
      {cluster?.rebalancing && <div className="banner warn"><b>Rebalancing.</b> Writes are paused until the new shard is in the ring.</div>}
      {Object.entries(outage).map(([g, t]) => (
        <div className="banner warn" key={g}><span className="spin" /><span><b>{g} has no leader.</b> Election in progress, {((Date.now() - t) / 1000).toFixed(1)} s so far. The other group keeps serving.</span></div>
      ))}
      {Object.entries(recovery).filter(([, r]) => Date.now() - r.at < 12000).map(([g, r]) => (
        <div className="banner ok" key={g}><span><b>{g} recovered in about {(r.ms / 1000).toFixed(1)} s.</b> {r.node} is the new leader at term {r.term}. Committed writes were kept.</span></div>
      ))}

      {!cluster && !error && <div className="card card-pad"><Skeleton h={120} /></div>}

      <div style={{ display: "grid", gap: 20 }}>
        {active.map(([g, info]) => {
          const l = leaderOf(info); const up = Object.values(info.nodes).filter((n) => n.state !== "DOWN").length;
          return (
            <div className="card" key={g}>
              <div className="group-head">
                <div className="l">{g}<Badge tone={up === 3 ? "green" : up === 2 ? "amber" : "red"} dot>{up} of 3 up</Badge></div>
                <span className="hint">{l ? `Leader ${l[0]}` : "No leader"}{up < 2 ? " · writes blocked, no majority" : ""}</span>
              </div>
              <div className="table-wrap">
                <table className="t">
                  <thead><tr><th>Node</th><th>Role</th><th className="r">Term</th><th className="r">Log</th><th className="r">Committed</th><th className="r">Applied</th><th className="r">Port</th></tr></thead>
                  <tbody>
                    {Object.entries(info.nodes).map(([n, nd]) => (
                      <tr key={n} className={nd.state === "DOWN" ? "row-down" : ""}>
                        <td><span className="node-name"><span className={`pulse ${nd.state}`} />{n}</span></td>
                        <td><Badge tone={tone[nd.state]}>{nd.state.charAt(0) + nd.state.slice(1).toLowerCase()}</Badge></td>
                        <td className="r">{nd.term ?? "—"}</td><td className="r">{nd.log ?? "—"}</td><td className="r">{nd.commit ?? "—"}</td><td className="r">{nd.applied ?? "—"}</td><td className="r mono">{nd.port}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid2 section">
        <div>
          <div className="section-head"><div><h2>Events</h2><p>Detected from cluster changes while this tab is open</p></div></div>
          <div className="card">
            {events.length === 0 ? <Empty icon={<Server />} title="Nothing has happened yet" text="Stop a leader's terminal and the election will show up here, with the time it took." /> : (
              <ul className="log">{events.map((e) => (
                <li key={e.id}><time>{clock(e.t)}</time><span>{e.text}</span></li>
              ))}</ul>
            )}
          </div>
        </div>
        <div>
          <div className="section-head"><div><h2>Shard capacity</h2><p>Add a spare group to the hash ring</p></div></div>
          <div className="card card-pad">
            {spare.length === 0 && <p className="hint">No spare groups are configured.</p>}
            {spare.map(([g, info]) => {
              const up = Object.values(info.nodes).filter((n) => n.state !== "DOWN").length;
              return (
                <div key={g}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                    <div><b style={{ fontWeight: 600 }}>{g}</b> <Badge tone={up === 3 ? "green" : ""} dot>{up} of 3 running</Badge></div>
                    <Button variant="primary" size="sm" icon={<Plus />} disabled={up < 3 || cluster?.rebalancing} onClick={() => setAsk(g)}>Add to ring</Button>
                  </div>
                  {up < 3 && <p className="hint" style={{ marginTop: 10 }}>Start {Object.keys(info.nodes).join(", ")} first, with <span className="mono">python run_node.py {Object.keys(info.nodes)[0]}</span> and so on.</p>}
                </div>
              );
            })}
            <p className="hint" style={{ marginTop: 14 }}>Only the keys and tables whose owner changes are copied. Writes are paused for the duration.</p>
          </div>
        </div>
      </div>

      {ask && <Confirm title={`Add ${ask} to the ring?`} text="Ownership of some keys and tables will move to the new group. Writes pause until the copy finishes." confirm="Add shard" busy={busy} onConfirm={addShard} onCancel={() => setAsk(null)} />}
    </>
  );
}
