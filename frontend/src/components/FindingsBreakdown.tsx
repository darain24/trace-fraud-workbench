import { human } from "../format";
import type { Dict } from "../types";

/** The log-odds each finding contributed, largest magnitude first. */
export function FindingsBreakdown({ assessment }: { assessment?: Dict }) {
  if (!assessment?.findings?.length) return null;
  return (
    <div className="findings-breakdown">
      <div className="section-label">Why this probability</div>
      {assessment.findings
        .slice()
        .sort((a: Dict, b: Dict) => Math.abs(b.weight) - Math.abs(a.weight))
        .map((f: Dict) => (
          <div className="finding-row" key={f.name}>
            <span className="finding-name">{human(f.name)}</span>
            <span
              className={
                f.weight >= 0 ? "finding-weight up" : "finding-weight down"
              }
            >
              {f.weight >= 0 ? "+" : ""}
              {f.weight.toFixed(2)}
            </span>
          </div>
        ))}
      <p className="calibration-note">
        Log-odds contributions, summed with a{" "}
        {assessment.log_odds >= 0 ? "+" : ""}
        {assessment.log_odds} total. The bank&rsquo;s own risk score contributes
        nothing by design.
      </p>
    </div>
  );
}
