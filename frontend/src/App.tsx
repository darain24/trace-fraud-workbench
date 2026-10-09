import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Aperture,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  Clock3,
  Command,
  FileText,
  FlaskConical,
  GitBranch,
  Globe2,
  Layers3,
  Loader2,
  LockKeyhole,
  Network,
  Play,
  Search,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";

type Dict = Record<string, any>;
const money = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(n || 0);
const human = (s: string) =>
  s
    ?.toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (x) => x.toUpperCase()) || "Not assessed";
const api = async (path: string, options?: RequestInit) => {
  const r = await fetch("/api" + path, options);
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(
      typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail),
    );
  }
  return r.json();
};
const post = (path: string, body: Dict = {}) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
const icons = {
  customer: "◉",
  card: "▰",
  transaction: "↗",
  device: "▣",
  region: "◎",
  connected: "▰",
} as Record<string, string>;
function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty">
      <Network size={32} />
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("Investigations");
  const [cases, setCases] = useState<Dict[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<Dict | null>(null);
  const [health, setHealth] = useState<Dict | null>(null);
  const [metrics, setMetrics] = useState<Dict | null>(null);
  const [events, setEvents] = useState<Dict[]>([]);
  const [approvals, setApprovals] = useState<Dict[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [tab, setTab] = useState("graph");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [scenarios, setScenarios] = useState<Dict | null>(null);
  const [modal, setModal] = useState("");
  const [response, setResponse] = useState("confirmed");
  const [note, setNote] = useState("");
  const [focus, setFocus] = useState<string[]>([]);
  const [discoveries, setDiscoveries] = useState<Dict[]>([]);
  const [policy, setPolicy] = useState("");
  const [replay, setReplay] = useState<number | null>(null);
  const refresh = useCallback(async () => {
    const [c, m] = await Promise.all([api("/cases"), api("/evaluation")]);
    setCases(c);
    setMetrics(m);
    // The benchmark and the synthetic demo dataset carry different case IDs.
    setSelected(
      (s) =>
        s ||
        (c.find((x: Dict) => x.case_id === "HHG-014") ?? c[0])?.case_id ||
        "",
    );
  }, []);
  const loadCase = useCallback(async () => {
    if (!selected) return;
    const [d, e, a] = await Promise.all([
      api("/cases/" + selected),
      api("/cases/" + selected + "/events"),
      api("/cases/" + selected + "/approvals"),
    ]);
    setDetail(d);
    setEvents(e);
    setApprovals(a);
  }, [selected]);
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    api("/health")
      .then(setHealth)
      .catch((e) => setError(e.message));
  }, [refresh]);
  useEffect(() => {
    setDetail(null);
    setFocus([]);
    setReplay(null);
    loadCase().catch((e) => setError(e.message));
  }, [loadCase]);
  useEffect(() => {
    if (!detail || !["running", "scheduled"].includes(detail.state)) return;
    const stream = new EventSource("/api/cases/" + selected + "/stream");
    stream.onmessage = (e) => {
      const v = JSON.parse(e.data);
      setEvents((old) => (old.some((x) => x.id === v.id) ? old : [...old, v]));
    };
    stream.addEventListener("done", () => {
      stream.close();
      loadCase();
      refresh();
    });
    stream.onerror = () => {
      stream.close();
      loadCase().catch(() => {});
    };
    return () => stream.close();
  }, [detail?.state, selected, loadCase, refresh]);
  useEffect(() => {
    if (replay === null || replay >= events.length - 1) return;
    const t = setTimeout(
      () => setReplay((x) => (x === null ? null : x + 1)),
      1100,
    );
    return () => clearTimeout(t);
  }, [replay, events.length]);
  useEffect(() => {
    if (!modal) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setModal("");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [modal]);
  useEffect(() => {
    if (page === "Evaluation") refresh().catch((e) => setError(e.message));
    if (page === "Discovery")
      api("/discovery")
        .then(setDiscoveries)
        .catch((e) => setError(e.message));
    if (page === "Policy library")
      api("/policy")
        .then((x) => setPolicy(x.text))
        .catch((e) => setError(e.message));
  }, [page]);
  const run = async (name: string, fn: () => Promise<void>) => {
    setBusy(name);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const record = detail?.result?.case;
  const answer = detail?.result;
  const a = detail?.detail?.assessment;
  const packet = detail?.detail?.packet;
  const filtered = cases.filter(
    (c) =>
      (filter === "all" || c.assessment?.verdict === filter) &&
      `${c.case_id} ${c.customer_id} ${c.card_id}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const trigger = detail?.trigger;
  const running = !!detail && ["running", "scheduled"].includes(detail.state);
  const graph = useMemo(() => {
    const g = detail?.detail?.graph;
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
  }, [detail, focus]);
  const showScenarios = () =>
    run("scenarios", async () => {
      setScenarios(await api("/cases/" + selected + "/scenarios"));
      setModal("scenarios");
    });
  return (
    <div className="app-shell">
      <aside className="rail">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("Investigations");
          }}
        >
          <span className="brand-symbol">
            <Aperture size={22} />
          </span>
          <span>
            trace<span className="brand-dot">.</span>
          </span>
        </a>
        <nav>
          {[
            { name: "Investigations", icon: Layers3, count: cases.length },
            { name: "Discovery", icon: Network },
            { name: "Evaluation", icon: FlaskConical },
            { name: "Policy library", icon: BookOpen },
          ].map(({ name, icon: Icon, count }) => (
            <button
              key={name}
              title={name}
              className={page === name ? "active" : ""}
              onClick={() => setPage(name)}
            >
              <Icon size={18} />
              {name}
              {count !== undefined && (
                <span className="nav-count">{count}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="rail-bottom">
          <button onClick={() => setModal("services")}>
            <span className="status-dot" />
            <span>
              <b>System status</b>
              <small>Local only · $0 APIs</small>
            </span>
            <ChevronRight size={16} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <main>
          <header className="page-heading">
            <h1>{page}</h1>
            <p>
              {page === "Investigations"
                ? "Investigate connections, resolve uncertainty, and act with confidence."
                : page === "Discovery"
                  ? "Explore candidate networks beyond the twenty benchmark cases."
                  : page === "Evaluation"
                    ? "Real checks. Transparent limitations. No invented benchmark scores."
                    : "The bank’s fraud policy governs every recommendation and approval route."}
            </p>
          </header>
          {error && (
            <div role="alert" className="alert error">
              <TriangleAlert size={17} />
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="alert success">
              <Check size={16} />
              <span>{notice}</span>
              <button
                onClick={() => setNotice("")}
                aria-label="Dismiss notification"
              >
                <X size={16} />
              </button>
            </div>
          )}
          {(page === "Investigations" || page === "Evaluation") && (
            <div className="stats-strip">
              <Stat
                label="Benchmark cases"
                value={String(cases.length)}
                note="Benchmark case pack"
              />
              <Stat
                label="Investigations saved"
                value={String(metrics?.completed || 0)}
                note={`${metrics?.valid_exports || 0} structurally valid drafts`}
              />
              <Stat
                label="Awaiting clarity"
                value={String(metrics?.verdicts?.uncertain || 0)}
                note="Uncertainty is a valid outcome"
              />
              <Stat
                label="Graph persistence"
                value={`${metrics?.graph_verified || 0}/20`}
                note="Requires verified TigerGraph"
              />
            </div>
          )}
          {page === "Investigations" && (
            <div className="investigation-layout">
              <section className="case-panel">
                <div className="panel-heading">
                  <h2>
                    Case inbox <span>{cases.length}</span>
                  </h2>
                </div>
                <div className="search-box">
                  <Search size={15} />
                  <input
                    aria-label="Search cases"
                    placeholder="Search cases or customers"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <div className="filter-row">
                  {["all", "uncertain", "fraud", "legitimate"].map((f) => (
                    <button
                      key={f}
                      className={filter === f ? "selected" : ""}
                      onClick={() => setFilter(f)}
                    >
                      {f === "all"
                        ? "All cases"
                        : f === "legitimate"
                          ? "Cleared"
                          : human(f)}
                    </button>
                  ))}
                </div>
                <div className="case-list">
                  {filtered.map((c) => (
                    <button
                      className={
                        "case-item " +
                        (selected === c.case_id ? "selected" : "")
                      }
                      key={c.case_id}
                      onClick={() => setSelected(c.case_id)}
                    >
                      <div className="case-line">
                        <b>{c.case_id}</b>
                        <span>
                          {c.card_id} · {c.opened_at?.slice(5, 10)}
                        </span>
                      </div>
                      <div className="case-title">
                        {c.assessment?.pattern &&
                        c.assessment.pattern !== "none"
                          ? human(c.assessment.pattern)
                          : human(c.trigger_type)}
                      </div>
                      <div className="case-footer">
                        <Badge
                          tone={
                            c.assessment?.verdict === "fraud"
                              ? "red"
                              : c.assessment?.verdict === "legitimate"
                                ? "green"
                                : "amber"
                          }
                        >
                          {c.assessment
                            ? human(c.assessment.verdict)
                            : human(c.state)}
                        </Badge>
                        <span>
                          {c.assessment
                            ? money(c.assessment.exposure_usd)
                            : "Awaiting review"}
                        </span>
                      </div>
                    </button>
                  ))}
                  {filtered.length === 0 && (
                    <p className="small-empty">No matching cases.</p>
                  )}
                </div>
              </section>
              <div className="case-workspace">
                {detail ? (
                  <>
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
                              "source-chip " +
                              (record?.written_to_graph ? "verified" : "")
                            }
                            onClick={() => setModal("services")}
                            title={
                              record?.written_to_graph
                                ? "Case persistence confirmed."
                                : "Real benchmark data · TigerGraph integration not yet verified"
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
                          onClick={() =>
                            run("investigate", async () => {
                              if (answer) {
                                await post("/cases/" + selected + "/review");
                                setNotice("Local evidence review completed.");
                                await loadCase();
                              } else {
                                await post(
                                  "/cases/" + selected + "/investigate",
                                  { use_llm: true },
                                );
                                await loadCase();
                              }
                            })
                          }
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
                    {answer ? (
                      <>
                        <div className="analysis-grid">
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
                                    {name === "evidence" && (
                                      <span>{record.evidence.length}</span>
                                    )}
                                  </button>
                                ))}
                              </div>
                              {tab === "graph" &&
                                (focus.length > 0 ? (
                                  <button
                                    className="text-button"
                                    onClick={() => setFocus([])}
                                  >
                                    <X size={14} /> Clear highlight
                                  </button>
                                ) : (
                                  <span className="tab-meta">
                                    {graph.nodes.length} entities
                                  </span>
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
                                    <Background
                                      color="#e3e5de"
                                      gap={22}
                                      size={1}
                                    />
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
                                          t.id === trigger.flagged_txn_id
                                            ? "flagged-row"
                                            : ""
                                        }
                                      >
                                        <td>
                                          <b>
                                            {t.id}
                                            {t.id ===
                                              trigger.flagged_txn_id && (
                                              <span className="tiny-label">
                                                Flagged
                                              </span>
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
                                        {e.entity_ids.length} referenced
                                        entities <ArrowUpRight size={11} />
                                      </span>
                                    </div>
                                  </button>
                                ))}
                              </div>
                            )}
                          </section>
                          <section className="decision-panel">
                            <div className="decision-assessment">
                              <div className="section-label">
                                Current assessment
                              </div>
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
                              {detail.detail?.assessment?.findings?.length ? (
                                <div className="findings-breakdown">
                                  <div className="section-label">
                                    Why this probability
                                  </div>
                                  {detail.detail.assessment.findings
                                    .slice()
                                    .sort(
                                      (a: Dict, b: Dict) =>
                                        Math.abs(b.weight) - Math.abs(a.weight),
                                    )
                                    .map((f: Dict) => (
                                      <div className="finding-row" key={f.name}>
                                        <span className="finding-name">
                                          {human(f.name)}
                                        </span>
                                        <span
                                          className={
                                            f.weight >= 0
                                              ? "finding-weight up"
                                              : "finding-weight down"
                                          }
                                        >
                                          {f.weight >= 0 ? "+" : ""}
                                          {f.weight.toFixed(2)}
                                        </span>
                                      </div>
                                    ))}
                                  <p className="calibration-note">
                                    Log-odds contributions, summed with a{" "}
                                    {detail.detail.assessment.log_odds >= 0
                                      ? "+"
                                      : ""}
                                    {detail.detail.assessment.log_odds} total.
                                    The bank&rsquo;s own risk score contributes
                                    nothing by design.
                                  </p>
                                </div>
                              ) : null}
                              <div className="exposure-row">
                                <span>Potential exposure</span>
                                <b>{money(record.exposure_usd)}</b>
                              </div>
                              {detail.detail?.statistical_advisory && (
                                <p className="calibration-note">
                                  Historical-cohort model:{" "}
                                  {Math.round(
                                    detail.detail.statistical_advisory
                                      .probability * 100,
                                  )}
                                  % · advisory only; not validated for this
                                  benchmark distribution.
                                </p>
                              )}
                            </div>
                            <div className="decision-actions">
                              <div className="section-label">
                                Recommended next actions
                              </div>
                              <div className="action-list">
                                {answer.next_best_actions.final.map(
                                  (action: Dict, i: number) => (
                                    <div className="action" key={action.action}>
                                      <div className="action-order">
                                        {i + 1}
                                      </div>
                                      <div>
                                        <b>{human(action.action)}</b>
                                        <p>{action.reason}</p>
                                        {action.route !== "auto" ? (
                                          <button
                                            className="approval-button"
                                            disabled={
                                              !!busy ||
                                              approvals.some(
                                                (x) =>
                                                  x.action === action.action,
                                              )
                                            }
                                            onClick={() =>
                                              run("approve", async () => {
                                                await post(
                                                  "/cases/" +
                                                    selected +
                                                    "/approve",
                                                  {
                                                    action: action.action,
                                                    route: action.route,
                                                    decision_revision:
                                                      detail.revision,
                                                  },
                                                );
                                                await loadCase();
                                                setNotice(
                                                  "Demo approval recorded. No real action was executed.",
                                                );
                                              })
                                            }
                                          >
                                            <LockKeyhole size={11} />
                                            {approvals.some(
                                              (x) => x.action === action.action,
                                            )
                                              ? "Demo approval recorded"
                                              : action.route +
                                                " approval · simulate"}
                                          </button>
                                        ) : (
                                          <Badge tone="green">
                                            Auto-permitted · simulated only
                                          </Badge>
                                        )}
                                      </div>
                                    </div>
                                  ),
                                )}
                              </div>
                              <button
                                className="scenario-link"
                                onClick={showScenarios}
                                disabled={!!busy}
                              >
                                <GitBranch size={15} /> What would change this
                                decision?
                                <ArrowRight size={15} />
                              </button>
                            </div>
                          </section>
                        </div>
                        <div className="findings-grid">
                          <section className="finding-card">
                            <div className="section-label">
                              Supporting evidence
                            </div>
                            {a?.support
                              .slice(0, 3)
                              .map((s: string, i: number) => (
                                <p key={i}>
                                  <span className="evidence-dot" />
                                  {s}
                                </p>
                              ))}
                            {!a?.support.length && (
                              <p>
                                No independent fraud-supporting finding
                                established.
                              </p>
                            )}
                          </section>
                          <section className="finding-card alternative">
                            <div className="section-label">
                              The other explanation
                            </div>
                            {a?.counter
                              .slice(-3)
                              .map((s: string, i: number) => (
                                <p key={i}>
                                  <span className="evidence-dot" />
                                  {s}
                                </p>
                              ))}
                          </section>
                        </div>
                        <section className="bottom-summary">
                          <div>
                            <div className="section-label">
                              Investigator’s note
                            </div>
                            <p>{record.summary}</p>
                            {detail.detail?.synthesis && (
                              <div className="ai-note">
                                <Sparkles size={15} />
                                <div>
                                  <b>
                                    Local AI review ·{" "}
                                    {detail.detail.synthesis.model}
                                  </b>
                                  <p>
                                    {detail.detail.synthesis.synthesis.summary}
                                  </p>
                                  <small>
                                    Verbatim source evidence selected by the
                                    local model; no generated facts.
                                  </small>
                                </div>
                              </div>
                            )}
                            {detail.detail?.model_error && (
                              <div className="inline-warning">
                                Local AI review unavailable:{" "}
                                {detail.detail.model_error}
                              </div>
                            )}
                          </div>
                          <div className="summary-buttons">
                            <button
                              className="outline"
                              onClick={() => {
                                setModal("evidence");
                                setNote("");
                              }}
                            >
                              <Command size={14} /> Simulate evidence
                            </button>
                            <button
                              className="outline"
                              onClick={() => setModal("report")}
                            >
                              <FileText size={14} /> Case & SAR
                            </button>
                          </div>
                        </section>
                        <section className="activity-panel">
                          <div className="panel-heading">
                            <h2>Investigation activity</h2>
                            <button
                              className="text-button"
                              onClick={() =>
                                setReplay(replay === null ? 0 : null)
                              }
                            >
                              <Play size={12} />
                              {replay === null
                                ? "Replay recorded events"
                                : "Exit replay"}
                            </button>
                          </div>
                          {replay !== null && (
                            <div className="replay-banner">
                              Recorded replay ·{" "}
                              {Math.min(replay + 1, events.length)} /{" "}
                              {events.length} events · final case panels remain
                              current
                            </div>
                          )}
                          <div className="activity-list">
                            {events
                              .slice(
                                0,
                                replay === null ? undefined : replay + 1,
                              )
                              .map((e: Dict) => (
                                <div className="activity" key={e.id}>
                                  <span
                                    className={
                                      "activity-dot " +
                                      (e.kind === "warning" ? "warning" : "")
                                    }
                                  />
                                  <b>{e.title}</b>
                                  <small>
                                    {new Date(e.created_at).toLocaleTimeString(
                                      "en-US",
                                      { hour: "2-digit", minute: "2-digit" },
                                    )}
                                  </small>
                                </div>
                              ))}
                          </div>
                        </section>
                      </>
                    ) : (
                      <Empty
                        title={
                          running
                            ? "Following the evidence…"
                            : "Ready to investigate"
                        }
                        body={
                          running
                            ? "The local investigator is collecting evidence and reviewing policy. Progress appears as events arrive."
                            : trigger?.trigger_text ||
                              "Start an investigation to build an evidence-backed case."
                        }
                      />
                    )}
                  </>
                ) : (
                  <Empty
                    title="Loading investigation"
                    body="Retrieving the case record…"
                  />
                )}
              </div>
            </div>
          )}
          {page === "Discovery" && (
            <section className="standalone">
              <div className="panel-heading">
                <div>
                  <h2>Network discovery</h2>
                  <p>
                    Candidate shared-profile clusters · separate from the
                    benchmark
                  </p>
                </div>
                <button
                  className="primary"
                  disabled={!!busy}
                  onClick={() =>
                    run("discovery", async () =>
                      setDiscoveries(await post("/discovery/run")),
                    )
                  }
                >
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
          )}
          {page === "Evaluation" && (
            <section className="standalone">
              <div className="panel-heading">
                <div>
                  <h2>Evaluation cockpit</h2>
                  <p>
                    Benchmark completeness and chronological historical
                    diagnostics
                  </p>
                </div>
                <button
                  className="primary"
                  disabled={!!busy}
                  onClick={() =>
                    run("evaluate", async () => {
                      await post("/evaluation/run");
                      await refresh();
                    })
                  }
                >
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
                    {metrics?.note} Historical evaluation uses a selected sample
                    and is not a population estimate.
                  </p>
                </div>
              </div>
              <div className="checklist">
                {[
                  ["All 20 cases investigated", metrics?.completed === 20],
                  [
                    "Draft JSON and policy validation",
                    metrics?.valid_exports === 20 &&
                      metrics?.policy_errors === 0,
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
                    Trained on {metrics.statistical_model.train_cases}{" "}
                    July–August cases; calibrated on{" "}
                    {metrics.statistical_model.calibration_cases} September
                    cases; evaluated on {metrics.statistical_model.test_cases}{" "}
                    October cases.
                  </p>
                  <div>
                    <b>
                      {(
                        metrics.statistical_model.metrics.historical_model
                          .roc_auc * 100
                      ).toFixed(1)}
                      %<small>October ROC AUC</small>
                    </b>
                    <b>
                      {metrics.statistical_model.metrics.historical_model.brier}
                      <small>October Brier score</small>
                    </b>
                  </div>
                  <p>
                    Selected historical investigations differ from the
                    benchmark. This model remains advisory and cannot
                    independently close cases or authorize actions. October was
                    used for development diagnostics; these are not pristine
                    holdout or benchmark results.
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
                      {Object.entries(metrics.historical.metrics).map(
                        ([name, m]) => {
                          const v = m as Dict;
                          return (
                            <tr key={name}>
                              <td>{human(name)}</td>
                              <td>{v.n}</td>
                              <td>{v.brier}</td>
                              <td>{Math.round(v.coverage * 100)}%</td>
                              <td>
                                {Math.round(
                                  v.accuracy_including_abstentions * 100,
                                )}
                                %
                              </td>
                            </tr>
                          );
                        },
                      )}
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
          )}
          {page === "Policy library" && (
            <section className="standalone policy-library">
              <div className="panel-heading">
                <h2>Bank fraud policy</h2>
                <Badge tone="green">Version 1.0</Badge>
              </div>
              <p className="footnote">
                This is the benchmark policy, not a claim of production
                regulatory compliance.
              </p>
              <pre>{policy || "Loading policy…"}</pre>
            </section>
          )}
        </main>
      </div>
      {modal && (
        <div className="modal-backdrop" onClick={() => setModal("")}>
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
              <button onClick={() => setModal("")} aria-label="Close dialog">
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
                  <Badge
                    tone={health?.tigergraph?.available ? "green" : "amber"}
                  >
                    {health?.tigergraph?.available
                      ? "Reachable"
                      : "Not connected"}
                  </Badge>
                </div>
                <div className="evaluation-notice">
                  <LockKeyhole size={18} />
                  <p>
                    No billing or paid providers are enabled. Local SQLite
                    analysis is explicitly not a substitute for the required
                    TigerGraph integration.
                  </p>
                </div>
                <button
                  className="outline"
                  onClick={() =>
                    run("health", async () => setHealth(await api("/health")))
                  }
                >
                  Refresh connections
                </button>
              </>
            )}
            {modal === "evidence" && (
              <>
                <div className="evaluation-notice">
                  <FlaskConical size={20} />
                  <p>
                    This is a simulated response, not a real customer contact.
                    It will be recorded in the case and may change
                    recommendations.
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
                    <option value="denied">
                      Customer denies authorization
                    </option>
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
                  onClick={() =>
                    run("evidence", async () => {
                      await post("/cases/" + selected + "/evidence", {
                        response,
                        note,
                        simulated: true,
                      });
                      await loadCase();
                      await refresh();
                      setModal("");
                      setNotice(
                        "Simulated evidence recorded. Initial recommendations preserved.",
                      );
                    })
                  }
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
                <a
                  className="primary"
                  href={"/api/cases/" + selected + "/export"}
                >
                  <ArrowDownToLine size={15} /> Download draft JSON
                </a>
                <p className="footnote">
                  Draft export. Verified export requires verified graph
                  integration.
                </p>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="stat">
      <span>{label}</span>
      <b>{value}</b>
      <p>{note}</p>
    </div>
  );
}
