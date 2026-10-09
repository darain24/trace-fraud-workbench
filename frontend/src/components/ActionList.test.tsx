import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActionList } from "./ActionList";

const actions = [
  { action: "CREATE_CASE", route: "auto", reason: "Record the case." },
  { action: "BLOCK_CARD", route: "L1", reason: "Denied by the cardholder." },
  { action: "FILE_REPORT", route: "L2", reason: "Exposure above $1,000." },
];

describe("ActionList", () => {
  it("shows the approval route each action needs", () => {
    render(
      <ActionList
        actions={actions}
        approvals={[]}
        busy=""
        onApprove={() => {}}
      />,
    );
    expect(screen.getByText("Auto-permitted · simulated only")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "L1 approval · simulate" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "L2 approval · simulate" }),
    ).toBeEnabled();
    // An auto-routed action never offers an approval button.
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("numbers the actions in the order the policy returned them", () => {
    render(
      <ActionList
        actions={actions}
        approvals={[]}
        busy=""
        onApprove={() => {}}
      />,
    );
    expect(
      [...document.querySelectorAll(".action")].map((a) => [
        a.querySelector(".action-order")!.textContent,
        a.querySelector("b")!.textContent,
      ]),
    ).toEqual([
      ["1", "Create case"],
      ["2", "Block card"],
      ["3", "File report"],
    ]);
  });

  it("passes the clicked action to onApprove", () => {
    const onApprove = vi.fn();
    render(
      <ActionList
        actions={actions}
        approvals={[]}
        busy=""
        onApprove={onApprove}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "L2 approval · simulate" }),
    );
    expect(onApprove).toHaveBeenCalledWith(actions[2]);
  });

  it("locks an action once its approval is recorded", () => {
    render(
      <ActionList
        actions={actions}
        approvals={[{ action: "BLOCK_CARD", route: "L1" }]}
        busy=""
        onApprove={() => {}}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Demo approval recorded" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "L2 approval · simulate" }),
    ).toBeEnabled();
  });

  it("disables every approval while another request is in flight", () => {
    render(
      <ActionList
        actions={actions}
        approvals={[]}
        busy="approve"
        onApprove={() => {}}
      />,
    );
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });
});
