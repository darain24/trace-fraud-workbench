import type { Dict } from "../types";
import { Stat } from "./Stat";

export function StatsStrip({
  caseCount,
  metrics,
}: {
  caseCount: number;
  metrics: Dict | null;
}) {
  return (
    <div className="stats-strip">
      <Stat
        label="Benchmark cases"
        value={String(caseCount)}
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
  );
}
