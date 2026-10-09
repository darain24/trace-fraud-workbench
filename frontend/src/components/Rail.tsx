import {
  Aperture,
  BookOpen,
  ChevronRight,
  FlaskConical,
  Layers3,
  Network,
} from "lucide-react";

export function Rail({
  page,
  setPage,
  caseCount,
  onStatus,
}: {
  page: string;
  setPage: (page: string) => void;
  caseCount: number;
  onStatus: () => void;
}) {
  return (
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
          { name: "Investigations", icon: Layers3, count: caseCount },
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
            {count !== undefined && <span className="nav-count">{count}</span>}
          </button>
        ))}
      </nav>
      <div className="rail-bottom">
        <button onClick={onStatus}>
          <span className="status-dot" />
          <span>
            <b>System status</b>
            <small>Local only · $0 APIs</small>
          </span>
          <ChevronRight size={16} />
        </button>
      </div>
    </aside>
  );
}
