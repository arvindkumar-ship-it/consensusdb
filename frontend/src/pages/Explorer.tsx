import { useState } from "react";
import { Play, Search, Trash2, Save } from "lucide-react";
import { post } from "../api";
import { fmt } from "../hooks";
import { pct, runJobs, RunStats } from "../workload";
import { Badge, Button, ErrorNote, Field, PageHead, useToast } from "../ui";

type Res = { path: string; ms: number; body: any } | null;

function Result({ r }: { r: Res }) {
  if (!r) return null;
  const b = r.body, err = b?.error ?? (b?.ok && typeof b.ok === "object" ? b.ok.error : null);
  const rows = Array.isArray(b?.result) ? b.result : null;
  const cols = rows?.length && typeof rows[0] === "object" && !Array.isArray(rows[0]) ? Object.keys(rows[0]) : null;
  return (
    <div className="card fade-in" style={{ marginTop: 20 }}>
      <div className="group-head">
        <div className="l">Result{err ? <Badge tone="red" dot>Error</Badge> : <Badge tone="green" dot>OK</Badge>}</div>
        <div className="actions">{b?.group && <span className="chip">Routed to <b style={{ fontWeight: 600, color: "var(--text)" }}>{b.group}</b></span>}<span className="chip num">{r.ms.toFixed(1)} ms</span></div>
      </div>
      <div className="card-pad">
        {err ? <ErrorNote title="The database rejected this." text={String(err)} />
          : cols ? (
            <div className="table-wrap"><table className="t"><thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{rows.map((row: any, i: number) => <tr key={i}>{cols.map((c) => <td key={c}>{String(row[c])}</td>)}</tr>)}</tbody></table></div>
          ) : <pre className="code">{JSON.stringify(b, null, 2)}</pre>}
      </div>
    </div>
  );
}

function KV() {
  const [key, setKey] = useState(""); const [value, setValue] = useState("");
  const [busy, setBusy] = useState<string | null>(null); const [res, setRes] = useState<Res>(null);
  const run = async (path: string) => {
    if (!key.trim()) return;
    setBusy(path); const t = performance.now();
    try { const body = await post(path, path === "/set" ? { key, value } : { key }); setRes({ path, ms: performance.now() - t, body }); }
    catch (e: any) { setRes({ path, ms: performance.now() - t, body: { error: e.message } }); }
    finally { setBusy(null); }
  };
  return (
    <>
      <div className="card card-pad">
        <div className="grid2">
          <Field label="Key" hint="The key decides which group stores it."><input className="input" value={key} onChange={(e) => setKey(e.target.value)} placeholder="user:1" /></Field>
          <Field label="Value" hint="Only used for Set."><input className="input" value={value} onChange={(e) => setValue(e.target.value)} placeholder="arvind" /></Field>
        </div>
        <div className="actions" style={{ marginTop: 18, justifyContent: "space-between" }}>
          <div className="actions">
            <Button variant="primary" icon={<Save />} busy={busy === "/set"} disabled={!key.trim()} onClick={() => run("/set")}>Set</Button>
            <Button icon={<Search />} busy={busy === "/get"} disabled={!key.trim()} onClick={() => run("/get")}>Get</Button>
          </div>
          <Button variant="danger" icon={<Trash2 />} busy={busy === "/del"} disabled={!key.trim()} onClick={() => run("/del")}>Delete</Button>
        </div>
      </div>
      <Result r={res} />
    </>
  );
}

const TEMPLATES = [
  { label: "Create table", mode: "/sql", table: "people", sql: "CREATE TABLE people (id INT PRIMARY KEY, name TEXT)" },
  { label: "Insert row", mode: "/sql", table: "people", sql: "INSERT INTO people VALUES (1, 'asha')" },
  { label: "Select by id", mode: "/query", table: "people", sql: "SELECT * FROM people WHERE id = 1" },
  { label: "Select by name", mode: "/query", table: "people", sql: "SELECT * FROM people WHERE name = 'asha'" },
];

function SQL() {
  const [table, setTable] = useState("people"); const [mode, setMode] = useState("/sql"); const [sql, setSql] = useState("");
  const [busy, setBusy] = useState(false); const [res, setRes] = useState<Res>(null);
  const run = async () => {
    if (!sql.trim() || !table.trim()) return;
    setBusy(true); const t = performance.now();
    try { const body = await post(mode, { table, sql: sql.trim() }); setRes({ path: mode, ms: performance.now() - t, body }); }
    catch (e: any) { setRes({ path: mode, ms: performance.now() - t, body: { error: e.message } }); }
    finally { setBusy(false); }
  };
  return (
    <>
      <div className="card card-pad">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 18 }}>
          <span className="hint" style={{ alignSelf: "center", marginRight: 4 }}>Start from</span>
          {TEMPLATES.map((t) => <button key={t.label} className="chip" style={{ cursor: "pointer" }} onClick={() => { setTable(t.table); setMode(t.mode); setSql(t.sql); }}>{t.label}</button>)}
        </div>
        <div className="grid2" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <Field label="Table" hint="Router picks the group from the table name."><input className="input" value={table} onChange={(e) => setTable(e.target.value)} /></Field>
          <Field label="Statement type" hint="Writes go through Raft, reads come from the leader."><select className="select" value={mode} onChange={(e) => setMode(e.target.value)}><option value="/sql">Write (CREATE, INSERT, UPDATE, DELETE)</option><option value="/query">Read (SELECT)</option></select></Field>
        </div>
        <div style={{ marginTop: 16 }}><Field label="SQL" hint="Single line only. Newlines are not supported."><textarea className="textarea" value={sql} onChange={(e) => setSql(e.target.value.replace(/\n/g, " "))} placeholder="SELECT * FROM people WHERE id = 1" onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run(); }} /></Field></div>
        <div className="actions" style={{ marginTop: 18, justifyContent: "flex-end" }}>
          <span className="hint">Ctrl + Enter to run</span>
          <Button variant="primary" icon={<Play />} busy={busy} disabled={!sql.trim()} onClick={run}>Run</Button>
        </div>
      </div>
      <Result r={res} />
    </>
  );
}

function Load() {
  const [ops, setOps] = useState(1000); const [conc, setConc] = useState(8);
  const [done, setDone] = useState(0); const [busy, setBusy] = useState(false); const [st, setSt] = useState<RunStats | null>(null);
  const toast = useToast();
  const go = async () => {
    setBusy(true); setSt(null); setDone(0);
    const tag = Math.random().toString(36).slice(2, 7);
    const jobs = Array.from({ length: ops }, (_, i) => () => post("/set", { key: `lt:${tag}:${i}`, value: String(i) }));
    try { setSt(await runJobs(jobs, conc, setDone)); } catch (e: any) { toast(e.message, true); } finally { setBusy(false); }
  };
  const total = st ? Object.values(st.byGroup).reduce((a, b) => a + b, 0) || 1 : 1;
  return (
    <>
      <div className="card card-pad">
        <div className="grid2">
          <Field label="Writes to send"><select className="select" value={ops} onChange={(e) => setOps(+e.target.value)}>{[200, 500, 1000, 2000].map((n) => <option key={n} value={n}>{n.toLocaleString()} SET operations</option>)}</select></Field>
          <Field label="Parallel clients" hint="Higher concurrency lets group commit batch more writes."><select className="select" value={conc} onChange={(e) => setConc(+e.target.value)}>{[1, 4, 8, 16].map((n) => <option key={n} value={n}>{n}</option>)}</select></Field>
        </div>
        <div className="actions" style={{ marginTop: 18, justifyContent: "space-between" }}>
          <p className="hint" style={{ maxWidth: 420 }}>The browser is the client, so absolute numbers depend on this machine. Use it to see sharding and the effect of concurrency.</p>
          <Button variant="primary" icon={<Play />} busy={busy} onClick={go}>Run load test</Button>
        </div>
        {busy && <div className="progress" style={{ marginTop: 16 }}><i style={{ width: `${(done / ops) * 100}%` }} /></div>}
      </div>
      {st && (
        <div className="fade-in" style={{ marginTop: 20 }}>
          <div className="metrics">
            <div className="metric"><div className="k">Throughput</div><div className="v">{fmt(st.ops / st.seconds)}<small>ops/s</small></div></div>
            <div className="metric"><div className="k">p50</div><div className="v">{fmt(pct(st.ms, 50), 1)}<small>ms</small></div></div>
            <div className="metric"><div className="k">p95</div><div className="v">{fmt(pct(st.ms, 95), 1)}<small>ms</small></div></div>
            <div className="metric"><div className="k">Errors</div><div className="v">{fmt(st.errors)}</div></div>
          </div>
          <div className="card card-pad" style={{ marginTop: 20 }}>
            <div className="section-head"><div><h2>Where the keys went</h2><p>Consistent hashing should split them roughly evenly</p></div></div>
            <div className="bars">{Object.entries(st.byGroup).sort().map(([g, n]) => (
              <div className="bar-row" key={g} style={{ gridTemplateColumns: "48px 1fr 110px" }}><span className="lbl">{g}</span><div className="bar-track"><div className="bar-fill after" style={{ width: `${(n / total) * 100}%` }} /></div><span className="val">{fmt(n)} · {((n / total) * 100).toFixed(0)}%</span></div>
            ))}</div>
          </div>
        </div>
      )}
    </>
  );
}

export default function Explorer() {
  const [tab, setTab] = useState<"kv" | "sql" | "load">("kv");
  return (
    <>
      <PageHead title="Data explorer" desc="Talk to the cluster directly and see which shard handled each request." />
      <div className="tabs" role="tablist" style={{ marginBottom: 20 }}>
        {([["kv", "Key-value"], ["sql", "SQL"], ["load", "Load test"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "kv" && <KV />}{tab === "sql" && <SQL />}{tab === "load" && <Load />}
    </>
  );
}
