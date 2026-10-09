import type { Edge, Node } from "@xyflow/react";
import type { Dict } from "../types";
import { ActivityPanel } from "./ActivityPanel";
import { CaseHeader } from "./CaseHeader";
import { CaseSummary } from "./CaseSummary";
import { DecisionPanel } from "./DecisionPanel";
import { Empty } from "./Empty";
import { EvidenceWorkspace } from "./EvidenceWorkspace";
import { FindingsGrid } from "./FindingsGrid";

/** One loaded case: header, then either the finished investigation or the
 * prompt to start one. */
export function CaseWorkspace({
  selected,
  detail,
  busy,
  running,
  approvals,
  events,
  tab,
  setTab,
  focus,
  setFocus,
  graph,
  replay,
  setReplay,
  onStatus,
  onInvestigate,
  onApprove,
  onScenarios,
  onSimulate,
  onReport,
}: {
  selected: string;
  detail: Dict;
  busy: string;
  running: boolean;
  approvals: Dict[];
  events: Dict[];
  tab: string;
  setTab: (tab: string) => void;
  focus: string[];
  setFocus: (ids: string[]) => void;
  graph: { nodes: Node[]; edges: Edge[] };
  replay: number | null;
  setReplay: (replay: number | null) => void;
  onStatus: () => void;
  onInvestigate: () => void;
  onApprove: (action: Dict) => void;
  onScenarios: () => void;
  onSimulate: () => void;
  onReport: () => void;
}) {
  const answer = detail.result;
  const trigger = detail.trigger;
  return (
    <>
      <CaseHeader
        selected={selected}
        detail={detail}
        busy={busy}
        running={running}
        onStatus={onStatus}
        onInvestigate={onInvestigate}
      />
      {answer ? (
        <>
          <div className="analysis-grid">
            <EvidenceWorkspace
              tab={tab}
              setTab={setTab}
              focus={focus}
              setFocus={setFocus}
              graph={graph}
              record={answer.case}
              packet={detail.detail?.packet}
              trigger={trigger}
            />
            <DecisionPanel
              detail={detail}
              approvals={approvals}
              busy={busy}
              onApprove={onApprove}
              onScenarios={onScenarios}
            />
          </div>
          <FindingsGrid a={detail.detail?.assessment} />
          <CaseSummary
            detail={detail}
            onSimulate={onSimulate}
            onReport={onReport}
          />
          <ActivityPanel
            events={events}
            replay={replay}
            setReplay={setReplay}
          />
        </>
      ) : (
        <Empty
          title={running ? "Following the evidence…" : "Ready to investigate"}
          body={
            running
              ? "The local investigator is collecting evidence and reviewing policy. Progress appears as events arrive."
              : trigger?.trigger_text ||
                "Start an investigation to build an evidence-backed case."
          }
        />
      )}
    </>
  );
}
