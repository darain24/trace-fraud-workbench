import { Badge } from "./Badge";

export function PolicyPage({ policy }: { policy: string }) {
  return (
    <section className="standalone policy-library">
      <div className="panel-heading">
        <h2>Bank fraud policy</h2>
        <Badge tone="green">Version 1.0</Badge>
      </div>
      <p className="footnote">
        This is the benchmark policy, not a claim of production regulatory
        compliance.
      </p>
      <pre>{policy || "Loading policy…"}</pre>
    </section>
  );
}
