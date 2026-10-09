// Router ke saath saari baat yahin se. Base: dev me vite proxy (/api), prod me VITE_API.
const BASE = (import.meta.env.VITE_API as string | undefined) ?? "/api";

export class ApiError extends Error {}

async function req<T = any>(method: "GET" | "POST", path: string, body?: unknown, timeoutMs = 8000): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(BASE + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctl.signal,
    });
    if (!r.ok) throw new ApiError(`Router replied ${r.status}`);
    return (await r.json()) as T;
  } catch (e: any) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(e?.name === "AbortError" ? "Router did not respond in time" : "Cannot reach the router");
  } finally {
    clearTimeout(timer);
  }
}

export const get = <T = any>(p: string) => req<T>("GET", p);
export const post = <T = any>(p: string, b: unknown = {}, t?: number) => req<T>("POST", p, b, t);

export type NodeInfo = { port: number; state: string; term?: number; log?: number; commit?: number; applied?: number };
export type GroupInfo = { active: boolean; nodes: Record<string, NodeInfo> };
export type Cluster = { groups: Record<string, GroupInfo>; leaders: Record<string, number>; rebalancing: boolean; ts: number };
export type Metrics = { window_s: number; ops: number; ops_per_sec: number; errors: number; p50_ms: number | null; p95_ms: number | null; per_group: Record<string, number>; series: number[] };
