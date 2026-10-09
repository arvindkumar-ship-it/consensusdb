import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { BookOpen, Boxes, FlaskConical, Gauge, LayoutDashboard, Menu, Sparkles, Terminal } from "lucide-react";
import { ClusterProvider, useCluster } from "./cluster-context";
import { ToastProvider } from "./ui";
import Overview from "./pages/Overview";
import ClusterPage from "./pages/Cluster";
import Explorer from "./pages/Explorer";
import Optimizer from "./pages/Optimizer";
import Experiments from "./pages/Experiments";
import Benchmarks from "./pages/Benchmarks";
import Architecture from "./pages/Architecture";

const NAV = [
  { group: "Monitor", items: [
    { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
    { to: "/cluster", label: "Cluster", icon: Boxes },
  ]},
  { group: "Work", items: [
    { to: "/explorer", label: "Data explorer", icon: Terminal },
    { to: "/optimizer", label: "Optimizer", icon: Sparkles },
    { to: "/experiments", label: "Experiments", icon: FlaskConical },
  ]},
  { group: "Learn", items: [
    { to: "/benchmarks", label: "Benchmarks", icon: Gauge },
    { to: "/architecture", label: "Architecture", icon: BookOpen },
  ]},
];

function Status() {
  const { cluster, error } = useCluster();
  if (error && !cluster) return <><span className="pulse DOWN" /> Router unreachable</>;
  if (!cluster) return <><span className="pulse" /> Connecting</>;
  return <><span className="pulse FOLLOWER" /> Router connected</>;
}

export default function App() {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  return (
    <ToastProvider>
      <ClusterProvider>
        <div className="shell">
          <aside className={`side ${open ? "open" : ""}`}>
            <div className="brand"><span className="brand-mark"><i /></span>ConsensusDB</div>
            <nav className="nav" aria-label="Main">
              {NAV.map((g) => (
                <div key={g.group}>
                  <div className="nav-label">{g.group}</div>
                  {g.items.map(({ to, label, icon: Icon, end }) => (
                    <NavLink key={to} to={to} end={end}><Icon />{label}</NavLink>
                  ))}
                </div>
              ))}
            </nav>
            <div className="side-foot"><Status /></div>
          </aside>
          <div className="main">
            <div className="topbar">
              <button className="btn ghost sm" aria-label="Open menu" onClick={() => setOpen((o) => !o)}><Menu /></button>
              <strong style={{ fontWeight: 600 }}>ConsensusDB</strong>
            </div>
            <div className="page fade-in" key={loc.pathname}>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/cluster" element={<ClusterPage />} />
                <Route path="/explorer" element={<Explorer />} />
                <Route path="/optimizer" element={<Optimizer />} />
                <Route path="/experiments" element={<Experiments />} />
                <Route path="/benchmarks" element={<Benchmarks />} />
                <Route path="/architecture" element={<Architecture />} />
              </Routes>
            </div>
          </div>
        </div>
      </ClusterProvider>
    </ToastProvider>
  );
}
