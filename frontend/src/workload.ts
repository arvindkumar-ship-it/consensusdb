import { post } from "./api";

export type RunStats = { ops: number; errors: number; ms: number[]; byGroup: Record<string, number>; seconds: number };

export const pct = (a: number[], p: number) => {
  if (!a.length) return null;
  const s = [...a].sort((x, y) => x - y);
  return s[Math.min(s.length - 1, Math.round((s.length - 1) * (p / 100)))];
};

/** `jobs` ko `conc` parallel workers me chalao. Har job router ko ek call hai. */
export async function runJobs(jobs: (() => Promise<any>)[], conc: number, onProgress?: (done: number) => void): Promise<RunStats> {
  const st: RunStats = { ops: 0, errors: 0, ms: [], byGroup: {}, seconds: 0 };
  let i = 0, done = 0;
  const t0 = performance.now();
  const worker = async () => {
    while (i < jobs.length) {
      const job = jobs[i++];
      const s = performance.now();
      try {
        const r = await job();
        st.ms.push(performance.now() - s);
        if (r?.error) st.errors++;
        if (r?.group) st.byGroup[r.group] = (st.byGroup[r.group] ?? 0) + 1;
      } catch { st.errors++; }
      st.ops++; onProgress?.(++done);
    }
  };
  await Promise.all(Array.from({ length: conc }, worker));
  st.seconds = (performance.now() - t0) / 1000;
  return st;
}

export const DEMO_TABLE = "users_demo";

/** Optimizer ko data dene ke liye: table + rows + full-scan queries (name pe filter, koi index nahi). */
export async function seedDemo(rows: number, scans: number, onProgress: (p: number, label: string) => void) {
  const make = await post("/sql", { table: DEMO_TABLE, sql: `CREATE TABLE ${DEMO_TABLE} (id INT PRIMARY KEY, name TEXT)` });
  const already = make?.error && /exist/i.test(String(make.error));
  if (make?.error && !already) throw new Error(String(make.error));
  const total = rows + scans;
  if (!already) {
    const ins = Array.from({ length: rows }, (_, i) => () => post("/sql", { table: DEMO_TABLE, sql: `INSERT INTO ${DEMO_TABLE} VALUES (${i}, 'user${i}')` }));
    await runJobs(ins, 6, (d) => onProgress(d / total, "Inserting rows"));
  }
  await scanDemo(scans, rows || 300, (d) => onProgress(((already ? 0 : rows) + d) / (already ? scans : total), "Running queries"));
}

export function scanDemo(n: number, rows: number, onProgress?: (d: number) => void) {
  const scan = Array.from({ length: n }, (_, i) => () => post("/query", { table: DEMO_TABLE, sql: `SELECT * FROM ${DEMO_TABLE} WHERE name = 'user${(i * 7) % rows}'` }));
  return runJobs(scan, 4, onProgress);
}
