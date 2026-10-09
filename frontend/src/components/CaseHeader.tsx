import { ArrowDownToLine, Clock3, Loader2, Sparkles } from "lucide-react";
import { human } from "../format";
import type { Dict } from "../types";
import { Badge } from "./Badge";

export function CaseHeader({
  selected,
  detail,
  busy,
  running,
  onStatus,
  onInvestigate,
}: {
  selected: string;
  detail: Dict;
  busy: string;
  running: boolean;
  onStatus: () => void;
  onInvestigate: () => void;
}) {
  const answer = detail.result;
  const record = answer?.case;
  const trigger = detail.trigger;
  return (
    <div className="case-header">
      <div>
        <div className="case-overline">
          {selected}
          {detail.detail?.simulated && (
            <Badge tone="amber">Simulated evidence</Badge>
          )}
        </div>
        <h2>
          {record?.pattern && record.pattern !== "none"
            ? human(record.pattern)
            : human(trigger?.trigger_type)}
        </h2>
        <p className="case-meta">
          <span>{trigger?.card_id}</span>
          <span>
            <Clock3 size={14} /> {trigger?.opened_at}
          </span>
          <span>{human(trigger?.trigger_type)}</span>
          <button
            className={
              "source-chip " + (record?.written_to_graph ? "verified" : "")
            }
            onClick={onStatus}
            title={
              record?.written_to_graph
                ? "Case persistence confirmed."
                : "TigerGraph integration not yet verified"
            }
          >
            <span className="status-dot" />
            {record?.written_to_graph
              ? "Graph record verified"
              : "Local evidence mode · graph not verified"}
          </button>
        </p>
      </div>
      <div className="case-header-actions">
        {answer && (
          <a
            className="icon-button"
            title="Download draft JSON"
            href={"/api/cases/" + selected + "/export"}
          >
            <ArrowDownToLine size={17} />
          </a>
        )}
        <button
          className="primary"
          disabled={!!busy || running}
          onClick={onInvestigate}
        >
          {busy === "investigate" || running ? (
            <Loader2 className="spin" size={15} />
          ) : (
            <Sparkles size={15} />
          )}{" "}
          {answer ? "Review with AI" : "Investigate"}
        </button>
      </div>
    </div>
  );
}
