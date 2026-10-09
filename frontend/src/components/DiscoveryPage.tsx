import { Loader2, Network } from "lucide-react";
import type { Dict } from "../types";
import { Badge } from "./Badge";
import { Empty } from "./Empty";

export function DiscoveryPage({
  discoveries,
  busy,
  onScan,
}: {
  discoveries: Dict[];
  busy: string;
  onScan: () => void;
}) {
  return (
    <section className="standalone">
      <div className="panel-heading">
        <div>
          <h2>Network discovery</h2>
          <p>Candidate shared-profile clusters · separate from the benchmark</p>
        </div>
        <button className="primary" disabled={!!busy} onClick={onScan}>
          {busy ? (
            <Loader2 size={15} className="spin" />
          ) : (
            <Network size={15} />
          )}{" "}
          Scan dataset
        </button>
      </div>
      <div className="discovery-grid">
        {discoveries.map((d) => (
          <article key={d.id}>
            <Badge tone="amber">Candidate · unassessed</Badge>
            <h3>{d.id}</h3>
            <p className="device-name">{d.device}</p>
            <div className="discovery-counts">
              <span>
                <b>{d.customers}</b>customers
              </span>
              <span>
                <b>{d.transactions}</b>transactions
              </span>
            </div>
            <p>{d.reason}</p>
            <small>
              {d.first_seen} — {d.last_seen}
            </small>
          </article>
        ))}
      </div>
      {!discoveries.length && (
        <Empty
          title="Find the next investigation"
          body="Scan the exam period for shared-profile candidates. A cluster is a lead, not a fraud verdict."
        />
      )}
    </section>
  );
}
