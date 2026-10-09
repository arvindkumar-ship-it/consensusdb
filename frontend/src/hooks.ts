import { useCallback, useEffect, useRef, useState } from "react";

/** Har `ms` pe fetch. Pehli baar loading=true, baad ke refresh me purana data dikhta rehta hai (layout jump nahi). */
export function usePoll<T>(fn: () => Promise<T>, ms: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const run = useCallback(async () => {
    try { setData(await fnRef.current()); setError(null); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    let alive = true;
    const tick = async () => { if (alive) await run(); };
    tick();
    const id = setInterval(tick, ms);
    return () => { alive = false; clearInterval(id); };
  }, [ms, run, ...deps]);
  return { data, error, loading, refresh: run };
}

export function fmt(n: number | null | undefined, d = 0) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
}
