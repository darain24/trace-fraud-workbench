import { MarkerType, type Edge, type Node } from "@xyflow/react";
import { human } from "../format";
import type { Dict } from "../types";

const icons = {
  customer: "◉",
  card: "▰",
  transaction: "↗",
  device: "▣",
  region: "◎",
  connected: "▰",
} as Record<string, string>;

/** Lay out the evidence graph in columns by entity kind, dimming anything
 * outside the current focus. */
export function buildGraph(g: Dict | undefined, focus: string[]) {
  if (!g) return { nodes: [], edges: [] };
  const counts: Record<string, number> = {};
  const x: Record<string, number> = {
    customer: 0,
    card: 185,
    transaction: 370,
    device: 560,
    region: 560,
    connected: 745,
  };
  const nodes: Node[] = g.nodes.map((n: Dict) => {
    const index = counts[n.kind] || 0;
    counts[n.kind] = index + 1;
    const dim = focus.length > 0 && !focus.includes(n.id);
    return {
      id: n.id,
      position: {
        x: x[n.kind] || 0,
        y:
          index * (n.kind === "transaction" ? 82 : 125) +
          (n.kind === "customer"
            ? 180
            : n.kind === "card"
              ? 130
              : n.kind === "device" || n.kind === "region"
                ? 180
                : 10),
      },
      data: {
        label: (
          <div className={"graph-card " + (n.flagged ? "flagged" : "")}>
            <span className="node-kind">
              {icons[n.kind]} {human(n.kind)}
            </span>
            <strong>{n.label}</strong>
            <small>
              {n.flagged
                ? "Flagged transaction"
                : n.kind === "transaction"
                  ? n.id
                  : n.kind === "connected"
                    ? "Connection, not verdict"
                    : "Evidence entity"}
            </small>
          </div>
        ),
      },
      style: { opacity: dim ? 0.35 : 1 },
      className: "trace-node",
    };
  });
  const edges: Edge[] = g.edges.map((e: Dict) => ({
    ...e,
    type: "smoothstep",
    animated: false,
    style: { stroke: "#aeb8a2", strokeWidth: 1.5 },
    labelStyle: { fontSize: 11, fill: "#5f6a57" },
    labelBgStyle: { fill: "#fafaf8" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#aeb8a2" },
  }));
  return { nodes, edges };
}
