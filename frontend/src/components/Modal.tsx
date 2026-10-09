import {
  ArrowDownToLine,
  Check,
  FlaskConical,
  Globe2,
  LockKeyhole,
  Loader2,
  Network,
  Sparkles,
  X,
} from "lucide-react";
import { human } from "../format";
import type { Dict } from "../types";
import { Badge } from "./Badge";

export function Modal({
  modal,
  onClose,
  selected,
  answer,
  health,
  onRefreshHealth,
  busy,
  response,
  setResponse,
  note,
  setNote,
  onRecordEvidence,
  scenarios,
}: {
  modal: string;
  onClose: () => void;
  selected: string;
  answer: Dict | undefined;
  health: Dict | null;
  onRefreshHealth: () => void;
  busy: string;
  response: string;
  setResponse: (response: string) => void;
  note: string;
  setNote: (note: string) => void;
  onRecordEvidence: () => void;
  scenarios: Dict | null;
}) {
  const record = answer?.case;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className={"modal " + (modal === "scenarios" ? "wide" : "")}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={human(modal)}
      >
        <div className="modal-header">
          <h2>
            {modal === "services"
              ? "Connected services"
              : modal === "evidence"
                ? "Simulate customer evidence"
                : modal === "report"
                  ? "Case record & SAR"
                  : "What would change this decision?"}
          </h2>
          <button onClick={onClose} aria-label="Close dialog">
            <X size={20} />
          </button>
        </div>
        {modal === "services" && (
          <>
            <div className="service-row">
              <Globe2 />
              <div>
                <b>Source dataset</b>
                <p>
                  {health?.dataset
                    ? `${health.dataset.transactions.toLocaleString()} transactions · ${health.dataset.historical_cases.toLocaleString()} historical cases`
                    : "Dataset not loaded"}
                </p>
              </div>
              <Badge tone={health?.dataset ? "green" : "amber"}>
                {health?.dataset ? "Loaded" : "Pending"}
              </Badge>
            </div>
            <div className="service-row">
              <Sparkles />
              <div>
                <b>Local model · {health?.model?.model || "qwen3:4b"}</b>
                <p>Ollama on this computer. No paid API fallback.</p>
              </div>
              <Badge tone={health?.model?.available ? "green" : "amber"}>
                {health?.model?.available ? "Available" : "Pending"}
              </Badge>
            </div>
            <div className="service-row">
              <Network />
              <div>
                <b>TigerGraph MCP</b>
                <p>{health?.tigergraph?.reason}</p>
              </div>
              <Badge tone={health?.tigergraph?.available ? "green" : "amber"}>
                {health?.tigergraph?.available ? "Reachable" : "Not connected"}
              </Badge>
            </div>
            <div className="evaluation-notice">
              <LockKeyhole size={18} />
              <p>
                No billing or paid providers are enabled. Local SQLite analysis
                is explicitly not a substitute for the required TigerGraph
                integration.
              </p>
            </div>
            <button className="outline" onClick={onRefreshHealth}>
              Refresh connections
            </button>
          </>
        )}
        {modal === "evidence" && (
          <>
            <div className="evaluation-notice">
              <FlaskConical size={20} />
              <p>
                This is a simulated response, not a real customer contact. It
                will be recorded in the case and may change recommendations.
              </p>
            </div>
            <label className="field-label">
              Assumed customer response
              <select
                value={response}
                onChange={(e) => setResponse(e.target.value)}
              >
                <option value="confirmed">
                  Customer confirms authorization
                </option>
                <option value="denied">Customer denies authorization</option>
                <option value="no_reply">No reply after 24 hours</option>
                <option value="conflicting">
                  Response conflicts with evidence
                </option>
              </select>
            </label>
            <label className="field-label">
              Assumption notes
              <textarea
                placeholder="Optional context for this simulation"
                maxLength={1000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            <button
              className="primary"
              disabled={!!busy}
              onClick={onRecordEvidence}
            >
              {busy ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <Check size={15} />
              )}{" "}
              Record simulated response
            </button>
          </>
        )}
        {modal === "scenarios" && (
          <>
            <p className="modal-intro">
              Hypothetical branches only. Exploring these outcomes does not
              change the case record.
            </p>
            <div className="scenario-grid">
              {Object.entries(scenarios?.branches || {}).map(
                ([name, actions]) => (
                  <article key={name}>
                    <h3>{human(name)}</h3>
                    {(actions as Dict[]).map((ac) => (
                      <div key={ac.action}>
                        <b>{human(ac.action)}</b>
                        <Badge>{ac.route}</Badge>
                        <p>{ac.reason}</p>
                      </div>
                    ))}
                  </article>
                ),
              )}
            </div>
            <div className="decision-history">
              <h3>Recorded recommendation history</h3>
              <p>
                <b>Initial:</b>{" "}
                {answer?.next_best_actions.initial
                  .map((x: Dict) => human(x.action))
                  .join(" → ")}
              </p>
              <p>
                <b>Current:</b>{" "}
                {answer?.next_best_actions.final
                  .map((x: Dict) => human(x.action))
                  .join(" → ")}
              </p>
              <small>{answer?.next_best_actions.what_changed}</small>
            </div>
          </>
        )}
        {modal === "report" && answer && (
          <>
            <Badge tone={answer.sar.file ? "amber" : "green"}>
              {answer.sar.file
                ? "SAR recommended · L2 approval required"
                : "No SAR recommended"}
            </Badge>
            <h3>
              {selected} / {human(record.status)}
            </h3>
            <p>{record.summary}</p>
            <div className="report-block">
              <b>Reporting decision</b>
              <p>{answer.sar.reason}</p>
              {answer.sar.narrative && <p>{answer.sar.narrative}</p>}
            </div>
            <div className="report-block">
              <b>Stopping reason</b>
              <p>{answer.stop_reason}</p>
            </div>
            <a className="primary" href={"/api/cases/" + selected + "/export"}>
              <ArrowDownToLine size={15} /> Download draft JSON
            </a>
            <p className="footnote">
              Draft export. Verified export requires verified graph integration.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
