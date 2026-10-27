// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PoolResponse } from "../../../api/client";
import { PoolStatus } from "../PoolStatus";

afterEach(() => {
  cleanup();
});

const mockPool: PoolResponse = {
  participant_id: "p-1",
  alias: "pilot-1",
  arms: [
    {
      arm: "control",
      ready_count: 6,
      target_count: 6,
      queued_count: 0,
      used_count: 2,
      deficit: 0,
      is_ready: true,
    },
    {
      arm: "heuristic",
      ready_count: 2,
      target_count: 6,
      queued_count: 4,
      used_count: 0,
      deficit: 0,
      is_ready: false,
    },
    {
      arm: "llm",
      ready_count: 1,
      target_count: 6,
      queued_count: 0,
      used_count: 0,
      deficit: 5,
      is_ready: false,
    },
  ],
};

describe("PoolStatus", () => {
  it("renders empty message when pool is null", () => {
    render(<PoolStatus pool={null} onReplenish={vi.fn()} onEnqueue={vi.fn()} />);
    expect(screen.getByText(/No participant selected/)).toBeInTheDocument();
  });

  it("renders arm cards with proper badges and counts", () => {
    render(<PoolStatus pool={mockPool} onReplenish={vi.fn()} onEnqueue={vi.fn()} />);

    expect(screen.getByText("pilot-1")).toBeInTheDocument();
    expect(screen.getByTestId("badge-control")).toHaveTextContent("Ready");
    expect(screen.getByTestId("badge-heuristic")).toHaveTextContent("Generating");
    expect(screen.getByTestId("badge-llm")).toHaveTextContent("Deficit");
  });

  it("triggers onReplenish when Replenish Pool button is clicked", () => {
    const onReplenish = vi.fn();
    render(<PoolStatus pool={mockPool} onReplenish={onReplenish} onEnqueue={vi.fn()} />);

    fireEvent.click(screen.getByTestId("replenish-btn"));
    expect(onReplenish).toHaveBeenCalled();
  });

  it("triggers onEnqueue with selected arm and count", () => {
    const onEnqueue = vi.fn();
    render(<PoolStatus pool={mockPool} onReplenish={vi.fn()} onEnqueue={onEnqueue} />);

    fireEvent.change(screen.getByTestId("arm-select"), { target: { value: "llm" } });
    fireEvent.change(screen.getByTestId("count-input"), { target: { value: "4" } });
    fireEvent.click(screen.getByTestId("enqueue-btn"));

    expect(onEnqueue).toHaveBeenCalledWith("llm", 4);
  });
});
