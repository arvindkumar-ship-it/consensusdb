import { useState } from "react";
import { FlaskConical, Play, Square } from "lucide-react";
import { get, post } from "../api";
import { fmt, usePoll } from "../hooks";
import { DEMO_TABLE, scanDemo } from "../workload";
import { Badge, Button, Empty, Field, PageHead, useToast } from "../ui";

function Report({ name, onStop }: { name: string; onStop: () => void }) {
  const r = usePoll(() => post("/ab/report", { name }), 2500, [name]);
  const d = r.data;
  return (
    <div className="card">
      <div className="group-head">
        <div className="l">{name}{d && (d.significant === null || d.significant === undefined ? <Badge tone="amber" dot>Collecting</Badge> : d.significant ? <Badge tone="green" dot>Significant</Badge> : <Badge dot>No clear difference</Badge>)}</div>
        <Button size="sm" variant="danger" icon={<Square />} onClick={onStop}>Stop</Button>
      </div>
      <div className="card-pad">
        {!d ? <p className="hint">Loading…</p> : d.error ? <p className="hint">{d.error}</p> : (
          <>
            <div className="metrics" style={{ boxShadow: "none" }}>
              <div className="metric"><div className="k">Control samples</div><div className="v">{fmt(d.n_control)}</div></div>
              <div className="metric"><div className="k">Treatment samples</div><div className="v">{fmt(d.n_treatment)}</div></div>
              <div className="metric"><div className="k">Mean latency</div><div className="v">{d.mean_control_ms != null ? `${fmt(d.mean_control_ms, 2)}` : "—"}<small>{d.mean_treatment_ms != null ? `vs ${fmt(d.mean_treatment_ms, 2)} ms` : ""}</small></div></div>
              <div className="metric"><div className="k">Improvement</div><div className="v">{d.improvement_pct != null ? fmt(d.improvement_pct, 1) : "—"}<small>{d.p_value != null ? `p = ${fmt(d.p_value, 4)}` : ""}</small></div></div>
            </div>
            {d.reason && <p className="hint" style={{ marginTop: 10 }}>{d.reason}. No claim is made until both sides have 30 samples.</p>}
          </>
        )}
      </div>
    </div>
  );
}

export default function Experiments() {
  const toast = useToast();
  const stats = usePoll(() => get("/stats"), 3000);
  const [name, setName] = useState(""); const [pctv, setPct] = useState(50); const [busy, setBusy] = useState(false); const [gen, setGen] = useState(false);
  const active: string[] = stats.data?.ab_active ?? [];

  const start = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try { const r = await post("/ab/start", { name: name.trim(), treatment_pct: pctv }); if (r.error) toast(r.error, true); else { toast("Experiment started."); setName(""); stats.refresh(); } }
    catch (e: any) { toast(e.message, true); } finally { setBusy(false); }
  };
  const stop = async (n: string) => { await post("/ab/stop", { name: n }); stats.refresh(); };
  const traffic = async () => {
    setGen(true);
    try { await scanDemo(120, 300); toast(`Sent 120 queries on ${DEMO_TABLE}.`); } catch (e: any) { toast(e.message, true); } finally { setGen(false); }
  };

  return (
    <>
      <PageHead title="Experiments" desc="Split SQL traffic into control and treatment by hashing the query, then compare latency with a Welch t-test." />
      <div className="card card-pad">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 220px auto", gap: 16, alignItems: "end" }} className="exp-form">
          <Field label="Experiment name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="index-on-name" onKeyDown={(e) => e.key === "Enter" && start()} /></Field>
          <Field label="Treatment share"><select className="select" value={pctv} onChange={(e) => setPct(+e.target.value)}>{[10, 25, 50, 75].map((n) => <option key={n} value={n}>{n}% of traffic</option>)}</select></Field>
          <Button variant="primary" icon={<Play />} busy={busy} disabled={!name.trim()} onClick={start}>Start</Button>
        </div>
        <p className="hint" style={{ marginTop: 12 }}>The same query always lands in the same bucket, so one user never sees both sides.</p>
      </div>

      <div className="section-head" style={{ marginTop: 36 }}><div><h2>Running</h2></div><Button size="sm" onClick={traffic} busy={gen} disabled={active.length === 0}>Send 120 test queries</Button></div>
      {active.length === 0 ? (
        <div className="card"><Empty icon={<FlaskConical />} title="No experiments running" text="Start one above. It records every SQL query that passes through the router until you stop it." /></div>
      ) : <div style={{ display: "grid", gap: 16 }}>{active.map((n) => <Report key={n} name={n} onStop={() => stop(n)} />)}</div>}
      <style>{`@media (max-width: 760px) { .exp-form { grid-template-columns: 1fr !important; } }`}</style>
    </>
  );
}
