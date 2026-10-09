import { ArrowRight, GitBranch } from "lucide-react";
import { human, money } from "../format";
import type { Dict } from "../types";
import { ActionList } from "./ActionList";
import { Badge } from "./Badge";
import { FindingsBreakdown } from "./FindingsBreakdown";

export function DecisionPanel({
  detail,
  approvals,
  busy,
  onApprove,
  onScenarios,
}: {
  detail: Dict;
  approvals: Dict[];
  busy: string;
  onApprove: (action: Dict) => void;
  onScenarios: () => void;
}) {
  const answer = detail.result;
  const record = answer.case;
  return (
    <section className="decision-panel">
      <div className="decision-assessment">
        <div className="section-label">Current assessment</div>
        <div className="verdict-row">
          <h3>{human(record.verdict)}</h3>
          <Badge
            tone={
              record.verdict === "fraud"
                ? "red"
                : record.verdict === "legitimate"
                  ? "green"
                  : "amber"
            }
          >
            {human(record.status)}
          </Badge>
        </div>
        <div className="probability">
          <span>Assessed fraud probability</span>
          <b>
            {Math.round(record.fraud_probability * 100)}
            <small>%</small>
          </b>
        </div>
        <div className="probability-bar">
          <i
            style={{
              width: record.fraud_probability * 100 + "%",
            }}
          />
        </div>
        <p className="calibration-note">
          Fitted on closed cases · holdout AUC 0.849
        </p>
        <FindingsBreakdown assessment={detail.detail?.assessment} />
        <div className="exposure-row">
          <span>Potential exposure</span>
          <b>{money(record.exposure_usd)}</b>
        </div>
        {detail.detail?.statistical_advisory && (
          <p className="calibration-note">
            Historical-cohort model:{" "}
            {Math.round(detail.detail.statistical_advisory.probability * 100)}%
            · advisory only; not validated for this benchmark distribution.
          </p>
        )}
      </div>
      <div className="decision-actions">
        <div className="section-label">Recommended next actions</div>
        <ActionList
          actions={answer.next_best_actions.final}
          approvals={approvals}
          busy={busy}
          onApprove={onApprove}
        />
        <button
          className="scenario-link"
          onClick={onScenarios}
          disabled={!!busy}
        >
          <GitBranch size={15} /> What would change this decision?
          <ArrowRight size={15} />
        </button>
      </div>
    </section>
  );
}
