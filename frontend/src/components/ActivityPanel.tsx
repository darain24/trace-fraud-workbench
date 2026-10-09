import { Play } from "lucide-react";
import type { Dict } from "../types";

export function ActivityPanel({
  events,
  replay,
  setReplay,
}: {
  events: Dict[];
  replay: number | null;
  setReplay: (replay: number | null) => void;
}) {
  return (
    <section className="activity-panel">
      <div className="panel-heading">
        <h2>Investigation activity</h2>
        <button
          className="text-button"
          onClick={() => setReplay(replay === null ? 0 : null)}
        >
          <Play size={12} />
          {replay === null ? "Replay recorded events" : "Exit replay"}
        </button>
      </div>
      {replay !== null && (
        <div className="replay-banner">
          Recorded replay · {Math.min(replay + 1, events.length)} /{" "}
          {events.length} events · final case panels remain current
        </div>
      )}
      <div className="activity-list">
        {events
          .slice(0, replay === null ? undefined : replay + 1)
          .map((e: Dict) => (
            <div className="activity" key={e.id}>
              <span
                className={
                  "activity-dot " + (e.kind === "warning" ? "warning" : "")
                }
              />
              <b>{e.title}</b>
              <small>
                {new Date(e.created_at).toLocaleTimeString("en-US", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </small>
            </div>
          ))}
      </div>
    </section>
  );
}
