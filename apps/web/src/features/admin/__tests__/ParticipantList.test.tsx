// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ParticipantResponse } from "../../../api/client";
import { ParticipantList } from "../ParticipantList";

afterEach(() => {
  cleanup();
});

const mockParticipants: readonly ParticipantResponse[] = [
  {
    id: "p-1",
    alias: "pilot-1",
    status: "baseline",
    is_builder: false,
    is_blinded: true,
    created_at: "2026-10-20T00:00:00Z",
    consent_at: "2026-10-20T00:00:00Z",
  },
  {
    id: "p-2",
    alias: "builder-user",
    status: "assigned",
    is_builder: true,
    is_blinded: false,
    created_at: "2026-10-20T00:00:00Z",
    consent_at: "2026-10-20T00:00:00Z",
  },
];

describe("ParticipantList", () => {
  it("renders participant rows and selects participant on click", () => {
    const onSelect = vi.fn();
    render(
      <ParticipantList
        participants={mockParticipants}
        selectedId="p-1"
        onSelect={onSelect}
        onCreate={vi.fn()}
        onAssign={vi.fn()}
      />,
    );

    expect(screen.getByText("pilot-1")).toBeInTheDocument();
    expect(screen.getByText("builder-user")).toBeInTheDocument();
    expect(screen.getByText("Builder")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("participant-row-p-2"));
    expect(onSelect).toHaveBeenCalledWith("p-2");
  });

  it("creates a new participant with alias and builder flag", () => {
    const onCreate = vi.fn();
    render(
      <ParticipantList
        participants={mockParticipants}
        selectedId={null}
        onSelect={vi.fn()}
        onCreate={onCreate}
        onAssign={vi.fn()}
      />,
    );

    const input = screen.getByTestId("new-alias-input");
    const checkbox = screen.getByTestId("builder-checkbox");
    const submitBtn = screen.getByTestId("create-participant-btn");

    fireEvent.change(input, { target: { value: "pilot-3" } });
    fireEvent.click(checkbox);
    fireEvent.click(submitBtn);

    expect(onCreate).toHaveBeenCalledWith("pilot-3", true);
  });

  it("enables assign button only for baseline participants", () => {
    const onAssign = vi.fn();
    render(
      <ParticipantList
        participants={mockParticipants}
        selectedId={null}
        onSelect={vi.fn()}
        onCreate={vi.fn()}
        onAssign={onAssign}
      />,
    );

    const assignBtn1 = screen.getByTestId("assign-btn-p-1");
    expect(assignBtn1).toBeEnabled();
    fireEvent.click(assignBtn1);
    expect(onAssign).toHaveBeenCalledWith("p-1");

    const assignBtn2 = screen.getByTestId("assign-btn-p-2");
    expect(assignBtn2).toBeDisabled();
  });
});
