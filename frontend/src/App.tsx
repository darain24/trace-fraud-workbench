import { useCallback, useEffect, useMemo, useState } from "react";
import "@xyflow/react/dist/style.css";
import { Check, TriangleAlert, X } from "lucide-react";
import { api, post } from "./api";
import { CaseInbox } from "./components/CaseInbox";
import { CaseWorkspace } from "./components/CaseWorkspace";
import { DiscoveryPage } from "./components/DiscoveryPage";
import { Empty } from "./components/Empty";
import { EvaluationPage } from "./components/EvaluationPage";
import { buildGraph } from "./components/graph";
import { Modal } from "./components/Modal";
import { PolicyPage } from "./components/PolicyPage";
import { Rail } from "./components/Rail";
import { StatsStrip } from "./components/StatsStrip";
import type { Dict } from "./types";

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
    // Reconnect only when the run state changes, not on every detail refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  }, [page, refresh]);
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
  const answer = detail?.result;
  const filtered = cases.filter(
    (c) =>
      (filter === "all" || c.assessment?.verdict === filter) &&
      `${c.case_id} ${c.customer_id} ${c.card_id}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const running = !!detail && ["running", "scheduled"].includes(detail.state);
  const graph = useMemo(
    () => buildGraph(detail?.detail?.graph, focus),
    [detail, focus],
  );
  const showScenarios = () =>
    run("scenarios", async () => {
      setScenarios(await api("/cases/" + selected + "/scenarios"));
      setModal("scenarios");
    });
  const investigate = () =>
    run("investigate", async () => {
      if (answer) {
        await post("/cases/" + selected + "/review");
        setNotice("Local evidence review completed.");
        await loadCase();
      } else {
        await post("/cases/" + selected + "/investigate", { use_llm: true });
        await loadCase();
      }
    });
  const approve = (action: Dict) =>
    run("approve", async () => {
      await post("/cases/" + selected + "/approve", {
        action: action.action,
        route: action.route,
        decision_revision: detail?.revision,
      });
      await loadCase();
      setNotice("Demo approval recorded. No real action was executed.");
    });
  const recordEvidence = () =>
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
    });
  return (
    <div className="app-shell">
      <Rail
        page={page}
        setPage={setPage}
        caseCount={cases.length}
        onStatus={() => setModal("services")}
      />
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
            <StatsStrip caseCount={cases.length} metrics={metrics} />
          )}
          {page === "Investigations" && (
            <div className="investigation-layout">
              <CaseInbox
                caseCount={cases.length}
                filtered={filtered}
                selected={selected}
                setSelected={setSelected}
                search={search}
                setSearch={setSearch}
                filter={filter}
                setFilter={setFilter}
              />
              <div className="case-workspace">
                {detail ? (
                  <CaseWorkspace
                    selected={selected}
                    detail={detail}
                    busy={busy}
                    running={running}
                    approvals={approvals}
                    events={events}
                    tab={tab}
                    setTab={setTab}
                    focus={focus}
                    setFocus={setFocus}
                    graph={graph}
                    replay={replay}
                    setReplay={setReplay}
                    onStatus={() => setModal("services")}
                    onInvestigate={investigate}
                    onApprove={approve}
                    onScenarios={showScenarios}
                    onSimulate={() => {
                      setModal("evidence");
                      setNote("");
                    }}
                    onReport={() => setModal("report")}
                  />
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
            <DiscoveryPage
              discoveries={discoveries}
              busy={busy}
              onScan={() =>
                run("discovery", async () =>
                  setDiscoveries(await post("/discovery/run")),
                )
              }
            />
          )}
          {page === "Evaluation" && (
            <EvaluationPage
              metrics={metrics}
              busy={busy}
              onRun={() =>
                run("evaluate", async () => {
                  await post("/evaluation/run");
                  await refresh();
                })
              }
            />
          )}
          {page === "Policy library" && <PolicyPage policy={policy} />}
        </main>
      </div>
      {modal && (
        <Modal
          modal={modal}
          onClose={() => setModal("")}
          selected={selected}
          answer={answer}
          health={health}
          onRefreshHealth={() =>
            run("health", async () => setHealth(await api("/health")))
          }
          busy={busy}
          response={response}
          setResponse={setResponse}
          note={note}
          setNote={setNote}
          onRecordEvidence={recordEvidence}
          scenarios={scenarios}
        />
      )}
    </div>
  );
}
