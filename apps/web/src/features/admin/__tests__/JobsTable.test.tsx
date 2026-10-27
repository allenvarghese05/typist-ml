// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { JobResponse } from "../../../api/client";
import { JobsTable } from "../JobsTable";

afterEach(() => {
  cleanup();
});

const mockJobs: readonly JobResponse[] = [
  {
    id: "job-1",
    participant_id: "p-1",
    arm: "control",
    requested: 2,
    status: "done",
    retries: 0,
    error: null,
    created_at: "2026-10-20T12:00:00Z",
    started_at: "2026-10-20T12:00:01Z",
    finished_at: "2026-10-20T12:00:02Z",
  },
  {
    id: "job-2",
    participant_id: "p-1",
    arm: "llm",
    requested: 1,
    status: "failed",
    retries: 3,
    error: "MLX model timed out",
    created_at: "2026-10-20T12:05:00Z",
    started_at: "2026-10-20T12:05:01Z",
    finished_at: "2026-10-20T12:06:00Z",
  },
];

describe("JobsTable", () => {
  it("renders job rows, status, and error message", () => {
    render(<JobsTable jobs={mockJobs} onRefresh={vi.fn()} onRetry={vi.fn()} />);

    expect(screen.getByText("job-1")).toBeInTheDocument();
    expect(screen.getByText("job-2")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByTestId("job-error-job-2")).toHaveTextContent("MLX model timed out");
  });

  it("calls onRefresh when refresh button is clicked", () => {
    const onRefresh = vi.fn();
    render(<JobsTable jobs={mockJobs} onRefresh={onRefresh} onRetry={vi.fn()} />);

    fireEvent.click(screen.getByTestId("refresh-jobs-btn"));
    expect(onRefresh).toHaveBeenCalled();
  });

  it("calls onRetry when re-enqueue button is clicked on failed job", () => {
    const onRetry = vi.fn();
    render(<JobsTable jobs={mockJobs} onRefresh={vi.fn()} onRetry={onRetry} />);

    const retryBtn = screen.getByTestId("retry-job-btn-job-2");
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledWith(mockJobs[1]);
  });
});
