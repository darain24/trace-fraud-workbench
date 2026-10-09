import { Command, FileText, Sparkles } from "lucide-react";
import type { Dict } from "../types";

export function CaseSummary({
  detail,
  onSimulate,
  onReport,
}: {
  detail: Dict;
  onSimulate: () => void;
  onReport: () => void;
}) {
  const record = detail.result.case;
  return (
    <section className="bottom-summary">
      <div>
        <div className="section-label">Investigator’s note</div>
        <p>{record.summary}</p>
        {detail.detail?.synthesis && (
          <div className="ai-note">
            <Sparkles size={15} />
            <div>
              <b>Local AI review · {detail.detail.synthesis.model}</b>
              <p>{detail.detail.synthesis.synthesis.summary}</p>
              <small>
                Verbatim source evidence selected by the local model; no
                generated facts.
              </small>
            </div>
          </div>
        )}
        {detail.detail?.model_error && (
          <div className="inline-warning">
            Local AI review unavailable: {detail.detail.model_error}
          </div>
        )}
      </div>
      <div className="summary-buttons">
        <button className="outline" onClick={onSimulate}>
          <Command size={14} /> Simulate evidence
        </button>
        <button className="outline" onClick={onReport}>
          <FileText size={14} /> Case & SAR
        </button>
      </div>
    </section>
  );
}
