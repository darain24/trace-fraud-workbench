import type { Dict } from "../types";

export function FindingsGrid({ a }: { a: Dict | undefined }) {
  return (
    <div className="findings-grid">
      <section className="finding-card">
        <div className="section-label">Supporting evidence</div>
        {a?.support.slice(0, 3).map((s: string, i: number) => (
          <p key={i}>
            <span className="evidence-dot" />
            {s}
          </p>
        ))}
        {!a?.support.length && (
          <p>No independent fraud-supporting finding established.</p>
        )}
      </section>
      <section className="finding-card alternative">
        <div className="section-label">The other explanation</div>
        {a?.counter.slice(-3).map((s: string, i: number) => (
          <p key={i}>
            <span className="evidence-dot" />
            {s}
          </p>
        ))}
      </section>
    </div>
  );
}
