import { useState } from "react";
import { Check, Database, Play, Sparkles, TrendingUp } from "lucide-react";
import { post } from "../api";
import { fmt } from "../hooks";
import { seedDemo } from "../workload";
import { Badge, Button, Empty, ErrorNote, PageHead, Section, Skeleton, useToast } from "../ui";

export default function Optimizer() {
  const toast = useToast();
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [applying, setApplying] = useState<string | null>(null);
  const [applied, setApplied] = useState<Record<string, boolean>>({});
  const [impact, setImpact] = useState<Record<string, any>>({});
  const [seed, setSeed] = useState<{ p: number; label: string } | null>(null);

  const run = async () => {
    setBusy(true); setErr(null);
    try { const d = await post("/optimize/run", {}, 30000); setData(d); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const apply = async (s: any) => {
    setApplying(s.id);
    try {
      const r = await post("/optimize/apply", { id: s.id }, 30000);
      if (r.applied) { setApplied((a) => ({ ...a, [s.id]: true })); toast("Index applied on every replica."); }
      else toast(r.error ?? String(r.result?.error ?? "Could not apply the index."), true);
    } catch (e: any) { toast(e.message, true); } finally { setApplying(null); }
  };
  const measure = async (s: any) => {
    try { const r = await post("/optimize/impact", { id: s.id }); setImpact((i) => ({ ...i, [s.id]: r })); } catch (e: any) { toast(e.message, true); }
  };
  const seedNow = async () => {
    setSeed({ p: 0, label: "Creating table" });
    try { await seedDemo(300, 150, (p, label) => setSeed({ p, label })); toast("Demo workload recorded."); await run(); }
    catch (e: any) { toast(e.message, true); } finally { setSeed(null); }
  };

  const tables = data ? Object.entries<any>(data.features?.tables ?? {}) : [];
  const sugg: any[] = data?.suggestions ?? [];
  const isApplied = (s: any) => applied[s.id] || !!s.applied_at;

  return (
    <>
      <PageHead title="Optimizer" desc="Reads your real query log, suggests indexes, proves they are safe, and measures what they changed.">
        <Button icon={<Database />} onClick={seedNow} busy={!!seed}>Generate demo workload</Button>
        <Button variant="primary" icon={<Play />} onClick={run} busy={busy}>Run analysis</Button>
      </PageHead>

      {seed && <div className="card card-pad" style={{ marginBottom: 20 }}><div className="hint" style={{ marginBottom: 8 }}>{seed.label}</div><div className="progress"><i style={{ width: `${Math.min(100, seed.p * 100)}%` }} /></div></div>}
      {err && <ErrorNote title="Analysis failed." text={`${err}. Make sure the router is running, then try again.`} />}
      {busy && !data && <div className="card card-pad"><Skeleton h={90} /></div>}

      {!data && !busy && !err && (
        <div className="card"><Empty icon={<Sparkles />} title="No analysis yet" text="Run SQL through the Data explorer, or generate a demo workload, then run the analysis. Needs the SQL mode with mkdb." action={<Button variant="primary" onClick={run}>Run analysis</Button>} /></div>
      )}

      {data && (
        <div className="fade-in">
          <div className="actions" style={{ marginBottom: 16 }}>
            <Badge tone={data.source === "llm" ? "accent" : ""} dot>{data.source === "llm" ? "Suggested by the LLM" : "Suggested by rules"}</Badge>
            <span className="hint">{data.features?.total_queries ?? 0} queries analysed</span>
          </div>
          {data.llm_error && <div className="notice" style={{ marginBottom: 16 }}><div><b>LLM unavailable.</b> Fell back to rules. {data.llm_error}</div></div>}

          <Section title="Suggested indexes" desc="Ranked by estimated speed-up. Every suggestion passes the validator before it can be applied.">
            {sugg.length === 0 ? (
              <div className="card"><Empty icon={<Check />} title="No index worth adding" text="A table needs at least 20 queries with 30% or more full scans before a suggestion appears." /></div>
            ) : (
              <div style={{ display: "grid", gap: 14 }}>
                {sugg.map((s) => {
                  const im = impact[s.id];
                  return (
                    <div className="card card-pad" key={s.id}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 20, flexWrap: "wrap" }}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div className="actions" style={{ marginBottom: 8 }}><b style={{ fontWeight: 600 }}>{s.table}</b><span className="chip">{s.columns?.join(", ")}</span><Badge>{s.type}</Badge>{isApplied(s) && <Badge tone="green" dot>Applied</Badge>}</div>
                          <p style={{ color: "var(--text-2)" }}>{s.reason}</p>
                          <pre className="code" style={{ marginTop: 12 }}>{s.ddl}</pre>
                        </div>
                        <div className="actions" style={{ alignSelf: "flex-start" }}>
                          {isApplied(s)
                            ? <Button icon={<TrendingUp />} onClick={() => measure(s)}>Measure impact</Button>
                            : <Button variant="primary" busy={applying === s.id} onClick={() => apply(s)}>Apply index</Button>}
                        </div>
                      </div>
                      <div className="metrics" style={{ marginTop: 16, gridTemplateColumns: "repeat(3, 1fr)", boxShadow: "none" }}>
                        <div className="metric"><div className="k">Estimated speed-up</div><div className="v">{fmt(s.cost?.est_speedup_x, 1)}<small>×</small></div></div>
                        <div className="metric"><div className="k">Est. latency</div><div className="v">{fmt(s.cost?.est_before_ms, 2)}<small>→ {fmt(s.cost?.est_after_ms, 2)} ms</small></div></div>
                        <div className="metric"><div className="k">Write slowdown</div><div className="v">{fmt(s.cost?.est_write_slowdown_pct, 1)}<small>%</small></div></div>
                      </div>
                      <p className="hint" style={{ marginTop: 8 }}>Rough model, used only for ranking. {s.cost?.assumptions}</p>
                      {im && (
                        <div className="fade-in" style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
                          {im.error ? <ErrorNote title="No measurement." text={im.error} /> : im.significant === null || im.significant === undefined ? (
                            <div className="notice"><div><b>Not enough data yet.</b> {im.reason}. Run more queries that filter on this column, then measure again.</div></div>
                          ) : (
                            <div className="metrics" style={{ gridTemplateColumns: "repeat(4, 1fr)", boxShadow: "none" }}>
                              <div className="metric"><div className="k">Mean latency</div><div className="v">{fmt(im.mean_control_ms, 2)}<small>→ {fmt(im.mean_treatment_ms, 2)} ms</small></div></div>
                              <div className="metric"><div className="k">p95</div><div className="v">{fmt(im.p95_control_ms, 2)}<small>→ {fmt(im.p95_treatment_ms, 2)} ms</small></div></div>
                              <div className="metric"><div className="k">Improvement</div><div className="v" style={{ color: im.improvement_pct > 0 ? "var(--green)" : undefined }}>{fmt(im.improvement_pct, 1)}<small>%</small></div></div>
                              <div className="metric"><div className="k">Significance</div><div className="v">{im.significant ? "Yes" : "No"}<small>p = {fmt(im.p_value, 4)}</small></div></div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Section>

          {(data.notes?.length > 0) && (
            <Section title="Things an index won't fix">
              <div style={{ display: "grid", gap: 10 }}>{data.notes.map((n: string, i: number) => <div className="notice" key={i}><div>{n}</div></div>)}</div>
            </Section>
          )}

          {tables.length > 0 && (
            <Section title="What the optimizer saw" desc="Per-table summary of the query log">
              <div className="card table-wrap"><table className="t">
                <thead><tr><th>Table</th><th>Group</th><th className="r">Queries</th><th className="r">Full scans</th><th className="r">p95</th><th>Filters on</th><th>Indexed</th></tr></thead>
                <tbody>{tables.map(([t, f]) => (
                  <tr key={t}><td style={{ fontWeight: 500 }}>{t}</td><td>{f.group ?? "—"}</td><td className="r">{fmt(f.queries)}</td><td className="r">{fmt(f.full_scan_pct, 0)}%</td><td className="r">{fmt(f.p95_latency_ms, 2)} ms</td>
                    <td className="mono">{Object.keys(f.where_columns ?? {}).join(", ") || "—"}</td><td className="mono">{(f.indexed ?? []).join(", ") || "—"}</td></tr>
                ))}</tbody></table></div>
            </Section>
          )}

          {data.rejected?.length > 0 && (
            <Section title="Rejected by the validator" desc="Output that failed safety checks and was never run">
              <div className="card"><table className="t"><tbody>{data.rejected.map((r: any, i: number) => (
                <tr key={i}><td className="mono">{JSON.stringify(r.suggestion)}</td><td style={{ color: "var(--red)" }}>{r.reason}</td></tr>
              ))}</tbody></table></div>
            </Section>
          )}
        </div>
      )}
    </>
  );
}
