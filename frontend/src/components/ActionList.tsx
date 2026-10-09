import { LockKeyhole } from "lucide-react";
import { human } from "../format";
import type { Dict } from "../types";
import { Badge } from "./Badge";

/** Recommended actions with their approval route. Anything not `auto` needs a
 * (simulated) human approval before it would run. */
export function ActionList({
  actions,
  approvals,
  busy,
  onApprove,
}: {
  actions: Dict[];
  approvals: Dict[];
  busy: string;
  onApprove: (action: Dict) => void;
}) {
  return (
    <div className="action-list">
      {actions.map((action: Dict, i: number) => (
        <div className="action" key={action.action}>
          <div className="action-order">{i + 1}</div>
          <div>
            <b>{human(action.action)}</b>
            <p>{action.reason}</p>
            {action.route !== "auto" ? (
              <button
                className="approval-button"
                disabled={
                  !!busy || approvals.some((x) => x.action === action.action)
                }
                onClick={() => onApprove(action)}
              >
                <LockKeyhole size={11} />
                {approvals.some((x) => x.action === action.action)
                  ? "Demo approval recorded"
                  : action.route + " approval · simulate"}
              </button>
            ) : (
              <Badge tone="green">Auto-permitted · simulated only</Badge>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
