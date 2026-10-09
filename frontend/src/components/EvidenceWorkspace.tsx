import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { ArrowUpRight, Clock3, FileText, Network, X } from "lucide-react";
import { human, money } from "../format";
import type { Dict } from "../types";

export function EvidenceWorkspace({
  tab,
  setTab,
  focus,
  setFocus,
  graph,
  record,
  packet,
  trigger,
}: {
  tab: string;
  setTab: (tab: string) => void;
  focus: string[];
  setFocus: (ids: string[]) => void;
  graph: { nodes: Node[]; edges: Edge[] };
  record: Dict;
  packet: Dict | undefined;
  trigger: Dict;
}) {
  return (
    <section className="evidence-workspace">
      <div className="view-tabs">
        <div>
          {[
            {
              name: "graph",
              icon: Network,
              label: "Evidence graph",
            },
            {
              name: "timeline",
              icon: Clock3,
              label: "Timeline",
            },
            {
              name: "evidence",
              icon: FileText,
              label: "Evidence",
            },
          ].map(({ name, icon: Icon, label }) => (
            <button
              key={name}
              className={tab === name ? "active" : ""}
              onClick={() => setTab(name)}
            >
              <Icon size={14} />
              {label}
              {name === "evidence" && <span>{record.evidence.length}</span>}
            </button>
          ))}
        </div>
        {tab === "graph" &&
          (focus.length > 0 ? (
            <button className="text-button" onClick={() => setFocus([])}>
              <X size={14} /> Clear highlight
            </button>
          ) : (
            <span className="tab-meta">{graph.nodes.length} entities</span>
          ))}
      </div>
      {tab === "graph" ? (
        <>
          <div className="graph-area">
            <ReactFlow
              nodes={graph.nodes}
              edges={graph.edges}
              fitView
              fitViewOptions={{ padding: 0.15 }}
              minZoom={0.3}
              maxZoom={1.5}
              nodesDraggable={false}
              nodesConnectable={false}
              zoomOnScroll={false}
              preventScrolling={false}
              onNodeClick={(_, n) => {
                setFocus([n.id]);
              }}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#e3e5de" gap={22} size={1} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
          <div className="graph-legend">
            <span>
              <i className="legend-card" />
              Card / customer
            </span>
            <span>
              <i className="legend-tx" />
              Transaction
            </span>
            <span>
              <i className="legend-flag" />
              Flagged activity
            </span>
          </div>
        </>
      ) : tab === "timeline" ? (
        <div className="transaction-table">
          <table>
            <thead>
              <tr>
                <th>Transaction / time</th>
                <th>Channel</th>
                <th>Amount</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {packet?.timeline.map((t: Dict) => (
                <tr
                  key={t.id}
                  className={
                    t.id === trigger.flagged_txn_id ? "flagged-row" : ""
                  }
                >
                  <td>
                    <b>
                      {t.id}
                      {t.id === trigger.flagged_txn_id && (
                        <span className="tiny-label">Flagged</span>
                      )}
                    </b>
                    <small>{t.ts}</small>
                  </td>
                  <td>{human(t.channel)}</td>
                  <td>{money(t.amount)}</td>
                  <td>{t.risk.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="evidence-list">
          {record.evidence.map((e: Dict, i: number) => (
            <button
              key={i}
              onClick={() => {
                setFocus(e.entity_ids);
                setTab("graph");
              }}
            >
              <span className="evidence-number">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <p>{e.claim}</p>
                <small>{e.ref}</small>
                <span>
                  {e.entity_ids.length} referenced entities{" "}
                  <ArrowUpRight size={11} />
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
