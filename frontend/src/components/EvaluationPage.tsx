import {
  Check,
  Clock3,
  FlaskConical,
  Loader2,
  TriangleAlert,
} from "lucide-react";
import { human } from "../format";
import type { Dict } from "../types";
import { Badge } from "./Badge";
import { Empty } from "./Empty";

export function EvaluationPage({
  metrics,
  busy,
  onRun,
}: {
  metrics: Dict | null;
  busy: string;
  onRun: () => void;
}) {
  return (
    <section className="standalone">
      <div className="panel-heading">
        <div>
          <h2>Evaluation cockpit</h2>
          <p>Benchmark completeness and chronological historical diagnostics</p>
        </div>
        <button className="primary" disabled={!!busy} onClick={onRun}>
          {busy ? (
            <Loader2 className="spin" size={15} />
          ) : (
            <FlaskConical size={15} />
          )}{" "}
          Run historical evaluation
        </button>
      </div>
      <div className="evaluation-notice">
        <TriangleAlert size={20} />
        <div>
          <b>Hidden benchmark accuracy is unknown.</b>
          <p>
            {metrics?.note} Historical evaluation uses a selected sample and is
            not a population estimate.
          </p>
        </div>
      </div>
      <div className="checklist">
        {[
          ["All 20 cases investigated", metrics?.completed === 20],
          [
            "Draft JSON and policy validation",
            metrics?.valid_exports === 20 && metrics?.policy_errors === 0,
          ],
          [
            "TigerGraph case persistence verified",
            metrics?.graph_verified === 20,
          ],
          ["Verified graph integration", metrics?.verified],
        ].map(([label, ok]) => (
          <div key={String(label)}>
            <span className={ok ? "check-icon" : "pending-icon"}>
              {ok ? <Check size={16} /> : <Clock3 size={16} />}
            </span>
            <b>{String(label)}</b>
            <Badge tone={ok ? "green" : "amber"}>
              {ok ? "Passed" : "Pending"}
            </Badge>
          </div>
        ))}
      </div>
      {metrics?.statistical_model && (
        <div className="model-report">
          <h3>Historical statistical model · separate diagnostic</h3>
          <p>
            Trained on {metrics.statistical_model.train_cases} July–August
            cases; calibrated on {metrics.statistical_model.calibration_cases}{" "}
            September cases; evaluated on {metrics.statistical_model.test_cases}{" "}
            October cases.
          </p>
          <div>
            <b>
              {(
                metrics.statistical_model.metrics.historical_model.roc_auc * 100
              ).toFixed(1)}
              %<small>October ROC AUC</small>
            </b>
            <b>
              {metrics.statistical_model.metrics.historical_model.brier}
              <small>October Brier score</small>
            </b>
          </div>
          <p>
            Selected historical investigations differ from the benchmark. This
            model remains advisory and cannot independently close cases or
            authorize actions. October was used for development diagnostics;
            these are not pristine holdout or benchmark results.
          </p>
        </div>
      )}
      {metrics?.historical ? (
        <>
          <p className="evaluation-split">{metrics.historical.split}</p>
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Approach</th>
                <th>Sample size</th>
                <th>Brier score ↓</th>
                <th>Coverage</th>
                <th>Accuracy incl. abstentions</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(metrics.historical.metrics).map(([name, m]) => {
                const v = m as Dict;
                return (
                  <tr key={name}>
                    <td>{human(name)}</td>
                    <td>{v.n}</td>
                    <td>{v.brier}</td>
                    <td>{Math.round(v.coverage * 100)}%</td>
                    <td>
                      {Math.round(v.accuracy_including_abstentions * 100)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {metrics.historical.limitations.map((s: string) => (
            <p className="footnote" key={s}>
              • {s}
            </p>
          ))}
        </>
      ) : (
        <Empty
          title="Measure before making claims"
          body="Run the historical diagnostic to compare risk scores, investigation heuristics, and memory-enabled analysis."
        />
      )}
    </section>
  );
}
