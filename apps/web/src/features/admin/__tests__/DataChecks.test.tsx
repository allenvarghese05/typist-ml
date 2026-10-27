// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ChecksResponse } from "../../../api/client";
import { DataChecks } from "../DataChecks";

afterEach(() => {
  cleanup();
});

const mockChecksPassed: ChecksResponse = {
  participant_id: "p-1",
  alias: "pilot-1",
  status: "assigned",
  passed: true,
  checks: {
    seq_gaps: { passed: true, count: 0, details: [] },
    dwell_anomalies: { passed: true, negative_count: 0, over_1000ms_count: 0, details: [] },
    short_blocks: { passed: true, count: 0, details: [] },
    missing_keyups: {
      passed: true,
      total_events: 100,
      missing_count: 2,
      missing_share: 0.02,
      details: ["2/100 missing keyup(s)"],
    },
    in_progress_sessions: { passed: true, count: 0, details: [] },
  },
  trend: [
    {
      session_id: "s-1",
      phase: "baseline",
      day_index: 1,
      started_at: "2026-10-20T10:00:00Z",
      wpm: 68.4,
      accuracy: 0.982,
      per_set_error_rate: { A: 0.02, B: 0.04 },
      per_set_attempts: { A: 50, B: 50 },
      per_set_errors: { A: 1, B: 2 },
    },
  ],
};

const mockChecksFailed: ChecksResponse = {
  ...mockChecksPassed,
  passed: false,
  checks: {
    ...mockChecksPassed.checks,
    seq_gaps: {
      passed: false,
      count: 1,
      details: ["block b-1: gap between seq 1 and 4"],
    },
  },
};

describe("DataChecks", () => {
  it("renders pass banner and check badges when all checks pass", () => {
    render(<DataChecks checksResponse={mockChecksPassed} />);

    expect(screen.getByTestId("checks-summary-banner")).toHaveTextContent(
      "All 5 Data Checks Passed",
    );
    expect(screen.getByTestId("badge-seq-gaps")).toHaveTextContent("PASS");
    expect(screen.getByTestId("badge-dwell-anomalies")).toHaveTextContent("PASS");
    expect(screen.getByTestId("badge-short-blocks")).toHaveTextContent("PASS");
    expect(screen.getByTestId("badge-missing-keyups")).toHaveTextContent("PASS");
    expect(screen.getByTestId("badge-in-progress")).toHaveTextContent("PASS");
  });

  it("renders fail banner and details when a check fails", () => {
    render(<DataChecks checksResponse={mockChecksFailed} />);

    expect(screen.getByTestId("checks-summary-banner")).toHaveTextContent(
      "Data Quality Issues Detected",
    );
    expect(screen.getByTestId("badge-seq-gaps")).toHaveTextContent("FAIL");
    expect(screen.getByText(/gap between seq 1 and 4/)).toBeInTheDocument();
  });

  it("renders session trend table with wpm, accuracy, set error rates, and matrix link", () => {
    render(<DataChecks checksResponse={mockChecksPassed} />);

    expect(screen.getByTestId("trends-table")).toBeInTheDocument();
    expect(screen.getByText("68.4")).toBeInTheDocument();
    expect(screen.getByText("98.2%")).toBeInTheDocument();
    expect(screen.getByText("2.0%")).toBeInTheDocument();
    expect(screen.getByText("4.0%")).toBeInTheDocument();

    const link = screen.getByTestId("matrix-link-s-1");
    expect(link).toHaveAttribute("href", "#/matrix/s-1");
  });
});
