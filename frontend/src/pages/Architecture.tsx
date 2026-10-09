import { DIAGRAMS, LIMITS } from "../data";
import { PageHead, Section } from "../ui";

export default function Architecture() {
  return (
    <>
      <PageHead title="Architecture" desc="How a request travels, how the cluster survives failure, and where the design stops." />
      <div style={{ display: "grid", gap: 36 }}>
        {DIAGRAMS.map((d) => (
          <section key={d.file}>
            <div className="section-head"><div><h2>{d.title}</h2><p>{d.text}</p></div></div>
            <div className="figure"><img src={`/diagrams/${d.file}`} alt={`${d.title} diagram`} loading="lazy" /></div>
          </section>
        ))}
      </div>
      <Section title="Known limits" desc="Stated up front, so the numbers above are read in the right light">
        <div className="card"><ul className="log" style={{ listStyle: "none" }}>{LIMITS.map((l) => <li key={l} style={{ gridTemplateColumns: "1fr" }}>{l}</li>)}</ul></div>
      </Section>
    </>
  );
}
