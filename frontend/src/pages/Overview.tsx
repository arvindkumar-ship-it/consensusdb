import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { get, Metrics } from "../api";
import { fmt, usePoll } from "../hooks";
import { leaderOf, useCluster } from "../cluster-context";
import { Badge, ErrorNote, PageHead, Section, Skeleton, Spark } from "../ui";
import { IMPACT } from "../data";

function Metric({ k, v, unit, sub }: { k: string; v?: string; unit?: string; sub?: string }) {
  return (
    <div className="metric">
      <div className="k">{k}</div>
      <div className="v">{v ?? <Skeleton h={28} w={80} />}{v && unit && <small>{unit}</small>}</div>
      <div className="s">{sub ?? "\u00A0"}</div>
    </div>
  );
}

export function ImpactBars({ compact }: { compact?: boolean }) {
  return (
    <div className="card card-pad">
      {IMPACT.map((r) => {
        const max = Math.max(r.before, r.after);
        const gain = r.lowerIsBetter ? r.before / r.after : r.after / r.before;
        return (
          <div className="compare" key={r.label}>
            <div className="compare-head"><b>{r.label}</b><span className="gain">{gain.toFixed(gain >= 10 ? 0 : 1)}× better</span></div>
            <div className="bars">
              <div className="bar-row"><span className="lbl">Before</span><div className="bar-track"><div className="bar-fill" style={{ width: `${(r.before / max) * 100}%` }} /></div><span className="val">{fmt(r.before, r.before % 1 ? 1 : 0)} {r.unit}</span></div>
              <div className="bar-row"><span className="lbl">After · {r.note}</span><div className="bar-track"><div className="bar-fill after" style={{ width: `${(r.after / max) * 100}%` }} /></div><span className="val">{fmt(r.after, r.after % 1 ? 1 : 0)} {r.unit}</span></div>
            </div>
          </div>
        );
      })}
      {!compact && null}
    </div>
  );
}

export default function Overview() {
  const { cluster, error } = useCluster();
  const m = usePoll<Metrics>(() => get("/metrics"), 2000);
  const active = cluster ? Object.entries(cluster.groups).filter(([, g]) => g.active) : [];
  const healthy = active.filter(([, g]) => leaderOf(g) && Object.values(g.nodes).filter((n) => n.state !== "DOWN").length >= 2).length;
  const maxG = Math.max(1, ...Object.values(m.data?.per_group ?? {}));

  return (
    <>
      <PageHead title="Overview" desc="Live health, traffic and the measured effect of every optimisation, in one place." />
      {error && !cluster && <div style={{ marginBottom: 20 }}><ErrorNote title="Can't reach the router." text="Start the nodes and router.py, then this page will fill in on its own." /></div>}

      <div className="metrics">
        <Metric k="Throughput" v={m.data ? fmt(m.data.ops_per_sec, 1) : undefined} unit="ops/s" sub="Average, last 60 s" />
        <Metric k="p95 latency" v={m.data ? fmt(m.data.p95_ms, 1) : undefined} unit="ms" sub={m.data ? `p50 ${fmt(m.data.p50_ms, 1)} ms` : undefined} />
        <Metric k="Shard groups healthy" v={cluster ? `${healthy} / ${active.length}` : undefined} sub="Leader and a majority up" />
        <Metric k="Errors" v={m.data ? fmt(m.data.errors) : undefined} sub="Last 60 s" />
      </div>

      <div className="grid2 section">
        <div className="card card-pad">
          <div className="section-head"><div><h2>Traffic</h2><p>Requests per second through the router</p></div></div>
          {m.data ? (m.data.ops ? <Spark data={m.data.series} /> : <p className="hint" style={{ padding: "18px 0" }}>No requests yet. Open the Data explorer and run a load test.</p>) : <Skeleton h={56} />}
        </div>
        <div className="card card-pad">
          <div className="section-head"><div><h2>Routing</h2><p>Requests handled per shard group</p></div></div>
          {m.data && Object.keys(m.data.per_group).length ? (
            <div className="bars">
              {Object.entries(m.data.per_group).sort().map(([g, n]) => (
                <div className="bar-row" key={g} style={{ gridTemplateColumns: "48px 1fr 56px" }}><span className="lbl">{g}</span><div className="bar-track"><div className="bar-fill after" style={{ width: `${(n / maxG) * 100}%` }} /></div><span className="val">{fmt(n)}</span></div>
              ))}
            </div>
          ) : <p className="hint" style={{ padding: "18px 0" }}>Shows how consistent hashing splits your keys.</p>}
        </div>
      </div>

      <Section title="Cluster" right={<Link to="/cluster" className="btn ghost sm">Open cluster <ArrowRight /></Link>}>
        <div className="card">
          <table className="t"><thead><tr><th>Group</th><th>Leader</th><th className="r">Term</th><th>Replicas</th></tr></thead>
            <tbody>
              {!cluster && <tr><td colSpan={4}><Skeleton h={18} /></td></tr>}
              {active.map(([g, info]) => {
                const l = leaderOf(info); const up = Object.values(info.nodes).filter((n) => n.state !== "DOWN").length;
                return (
                  <tr key={g}>
                    <td style={{ fontWeight: 500 }}>{g}</td>
                    <td>{l ? <span className="node-name"><span className="pulse LEADER" />{l[0]}</span> : <Badge tone="amber" dot>Electing</Badge>}</td>
                    <td className="r">{l?.[1].term ?? "—"}</td>
                    <td><Badge tone={up === 3 ? "green" : up === 2 ? "amber" : "red"} dot>{up} of 3 up</Badge></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Measured impact" desc="What each engineering fix changed. From README, measured on one laptop over localhost." right={<Link to="/benchmarks" className="btn ghost sm">All benchmarks <ArrowRight /></Link>}>
        <ImpactBars />
      </Section>
    </>
  );
}
