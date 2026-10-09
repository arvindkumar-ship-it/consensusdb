import { get } from "../api";
import { fmt, usePoll } from "../hooks";
import { Badge, Empty, ErrorNote, PageHead, Section, Skeleton } from "../ui";
import { ImpactBars } from "./Overview";

const rowFor = (arr: any[], phase: string) => arr?.find((r) => r.phase === phase);

export default function Benchmarks() {
  const b = usePoll<any>(() => get("/bench"), 60000);
  const d = b.data;
  const phases = d && !d.error ? (d.single_mkdb ?? []).map((r: any) => r.phase) : [];
  return (
    <>
      <PageHead title="Benchmarks" desc="What was measured, what it cost, and what each fix was worth. Single Windows laptop, everything over localhost." />
      <Section title="What changed performance" desc="Before and after each fix, from the engineering log"><ImpactBars /></Section>

      <Section title="Standalone mkdb vs Raft cluster" desc="This is the price of replication: every write waits for a majority, and every request pays one router hop.">
        {b.loading ? <div className="card card-pad"><Skeleton h={90} /></div> : b.error || d?.error ? (
          <ErrorNote title="Benchmark file not available." text={b.error ?? d.error} />
        ) : phases.length === 0 ? <div className="card"><Empty title="No SQL benchmark yet" text="Run python -m bench.compare to produce bench_results.json." /></div> : (
          <div className="card table-wrap"><table className="t">
            <thead><tr><th>Phase</th><th className="r">Standalone</th><th className="r">Raft cluster</th><th className="r">p50 (cluster)</th><th className="r">p95 (cluster)</th><th className="r">Slowdown</th></tr></thead>
            <tbody>{phases.map((p: string) => {
              const a = rowFor(d.single_mkdb, p), c = rowFor(d.raft_cluster, p);
              return (<tr key={p}><td style={{ fontWeight: 500 }}>{p}</td><td className="r">{fmt(a?.ops_per_sec, 0)} ops/s</td><td className="r">{fmt(c?.ops_per_sec, 0)} ops/s</td><td className="r">{fmt(c?.p50_ms, 1)} ms</td><td className="r">{fmt(c?.p95_ms, 1)} ms</td><td className="r">{a && c ? `${(a.ops_per_sec / c.ops_per_sec).toFixed(1)}×` : "—"}</td></tr>);
            })}</tbody></table></div>
        )}
        <p className="hint" style={{ marginTop: 10 }}>These SQL numbers were taken before group commit, so writes should now be faster.</p>
      </Section>

      {d?.index_effect && !d.error && (
        <Section title="Index effect" desc="The optimizer's suggestion, applied through Raft, same scan run again (median of 3 rounds)">
          <div className="card card-pad">
            <div className="metrics" style={{ boxShadow: "none" }}>
              <div className="metric"><div className="k">Scan throughput</div><div className="v">{fmt(d.index_effect.before?.ops_per_sec, 0)}<small>→ {fmt(d.index_effect.after?.ops_per_sec, 0)}</small></div></div>
              <div className="metric"><div className="k">p50 latency</div><div className="v">{fmt(d.index_effect.before?.p50_ms, 2)}<small>→ {fmt(d.index_effect.after?.p50_ms, 2)} ms</small></div></div>
              <div className="metric"><div className="k">Speed-up</div><div className="v" style={{ color: "var(--green)" }}>{fmt(d.index_effect.speedup_ops_per_sec, 2)}<small>×</small></div></div>
              <div className="metric"><div className="k">Statistical claim</div><div className="v" style={{ fontSize: 16, lineHeight: "32px" }}><Badge tone="amber">Not made</Badge></div><div className="s">Sample windows did not match</div></div>
            </div>
            <div style={{ marginTop: 14 }}>{(d.index_effect.applied ?? []).map((q: string) => <pre className="code" key={q} style={{ marginTop: 6 }}>{q}</pre>)}</div>
          </div>
        </Section>
      )}
    </>
  );
}
