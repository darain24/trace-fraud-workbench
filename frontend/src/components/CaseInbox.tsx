import { Search } from "lucide-react";
import { human, money } from "../format";
import type { Dict } from "../types";
import { Badge } from "./Badge";

export function CaseInbox({
  caseCount,
  filtered,
  selected,
  setSelected,
  search,
  setSearch,
  filter,
  setFilter,
}: {
  caseCount: number;
  filtered: Dict[];
  selected: string;
  setSelected: (id: string) => void;
  search: string;
  setSearch: (s: string) => void;
  filter: string;
  setFilter: (f: string) => void;
}) {
  return (
    <section className="case-panel">
      <div className="panel-heading">
        <h2>
          Case inbox <span>{caseCount}</span>
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
              "case-item " + (selected === c.case_id ? "selected" : "")
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
              {c.assessment?.pattern && c.assessment.pattern !== "none"
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
                {c.assessment ? human(c.assessment.verdict) : human(c.state)}
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
  );
}
