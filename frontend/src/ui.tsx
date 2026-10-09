import { createContext, ReactNode, useCallback, useContext, useState } from "react";
import { Inbox, TriangleAlert } from "lucide-react";

export function Button({ variant = "secondary", size, busy, icon, children, ...p }: any) {
  return (
    <button {...p} disabled={p.disabled || busy} className={`btn ${variant === "secondary" ? "" : variant} ${size ?? ""} ${p.className ?? ""}`}>
      {busy ? <span className="spin" /> : icon}
      {children}
    </button>
  );
}

export const Badge = ({ tone = "", dot, children }: { tone?: string; dot?: boolean; children: ReactNode }) => (
  <span className={`badge ${tone}`}>{dot && <i className="dot" />}{children}</span>
);

export const Field = ({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) => (
  <div className="field"><label>{label}</label>{children}{hint && <span className="hint">{hint}</span>}</div>
);

export const PageHead = ({ title, desc, children }: { title: string; desc?: string; children?: ReactNode }) => (
  <header className="page-head">
    <div><h1>{title}</h1>{desc && <p>{desc}</p>}</div>
    {children && <div className="actions">{children}</div>}
  </header>
);

export const Section = ({ title, desc, right, children }: { title: string; desc?: string; right?: ReactNode; children: ReactNode }) => (
  <section className="section">
    <div className="section-head"><div><h2>{title}</h2>{desc && <p>{desc}</p>}</div>{right}</div>
    {children}
  </section>
);

export const Skeleton = ({ h = 16, w = "100%" }: { h?: number; w?: number | string }) => <div className="skeleton" style={{ height: h, width: w }} />;

export function Empty({ icon, title, text, action }: { icon?: ReactNode; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="ico">{icon ?? <Inbox />}</div>
      <h3>{title}</h3>{text && <p>{text}</p>}{action}
    </div>
  );
}

export function ErrorNote({ title, text }: { title: string; text: string }) {
  return <div className="notice red"><TriangleAlert /><div><b>{title}</b> {text}</div></div>;
}

export function Confirm({ title, text, confirm, busy, onConfirm, onCancel }: any) {
  return (
    <div className="scrim" onClick={onCancel} role="dialog" aria-modal="true">
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3><p>{text}</p>
        <div className="foot">
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button variant="primary" busy={busy} onClick={onConfirm}>{confirm}</Button>
        </div>
      </div>
    </div>
  );
}

type Toast = { id: number; msg: string; err?: boolean };
const ToastCtx = createContext<(msg: string, err?: boolean) => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((msg: string, err?: boolean) => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, msg, err }]);
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), 3600);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">{items.map((t) => <div key={t.id} className={`toast ${t.err ? "err" : ""}`}>{t.msg}</div>)}</div>
    </ToastCtx.Provider>
  );
}

export function Spark({ data, h = 56 }: { data: number[]; h?: number }) {
  const w = 600, max = Math.max(1, ...data);
  const pts = data.map((v, i) => [(i / Math.max(1, data.length - 1)) * w, h - 4 - (v / max) * (h - 12)]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none" role="img" aria-label="Requests per second, last 60 seconds">
      <path d={`${line} L${w},${h} L0,${h} Z`} fill="var(--accent-soft)" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth="1.75" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
