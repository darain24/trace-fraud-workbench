import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FindingsBreakdown } from "./FindingsBreakdown";

const findings = [
  { name: "burst", weight: 0.353 },
  { name: "new_device", weight: -3.011 },
  { name: "device_seen", weight: 1.376 },
  { name: "dispute_conflict", weight: 0 },
];

const rows = () =>
  [...document.querySelectorAll(".finding-row")].map((r) => [
    r.querySelector(".finding-name")!.textContent,
    r.querySelector(".finding-weight")!.textContent,
    r.querySelector(".finding-weight")!.className,
  ]);

describe("FindingsBreakdown", () => {
  it("orders findings by the size of their contribution, either sign", () => {
    render(<FindingsBreakdown assessment={{ findings, log_odds: -1.282 }} />);
    expect(rows().map((r) => r[0])).toEqual([
      "New device",
      "Device seen",
      "Burst",
      "Dispute conflict",
    ]);
  });

  it("signs every weight and rounds it to two places", () => {
    render(<FindingsBreakdown assessment={{ findings, log_odds: -1.282 }} />);
    expect(rows()).toEqual([
      ["New device", "-3.01", "finding-weight down"],
      ["Device seen", "+1.38", "finding-weight up"],
      ["Burst", "+0.35", "finding-weight up"],
      ["Dispute conflict", "+0.00", "finding-weight up"],
    ]);
  });

  it("states the summed log-odds with its sign", () => {
    const { rerender } = render(
      <FindingsBreakdown assessment={{ findings, log_odds: -1.282 }} />,
    );
    expect(screen.getByText(/summed with a/).textContent).toContain(
      "summed with a -1.282 total",
    );
    rerender(<FindingsBreakdown assessment={{ findings, log_odds: 2.5 }} />);
    expect(screen.getByText(/summed with a/).textContent).toContain(
      "summed with a +2.5 total",
    );
  });

  it("leaves the assessment's own order untouched", () => {
    const original = findings.map((f) => f.name);
    render(<FindingsBreakdown assessment={{ findings, log_odds: 0 }} />);
    expect(findings.map((f) => f.name)).toEqual(original);
  });

  it("renders nothing when there are no findings", () => {
    const { container } = render(
      <FindingsBreakdown assessment={{ findings: [], log_odds: 0.92 }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
