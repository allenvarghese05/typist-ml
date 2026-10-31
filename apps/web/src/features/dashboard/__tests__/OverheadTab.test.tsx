// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SessionOverheadEntry } from "../../../api/analysis";
import { OverheadTab } from "../OverheadTab";

afterEach(() => {
  cleanup();
});

const MOCK_OVERHEAD: readonly SessionOverheadEntry[] = [
  {
    session_id: "s1-baseline-1234",
    participant_id: "p1-pilot-1",
    events: 450,
    handler: { p50: 0.12, p95: 0.35, p99: 0.58 },
    dispatch: { p50: 1.1, p95: 2.3, p99: 3.5 },
  },
  {
    session_id: "all",
    participant_id: "all",
    events: 450,
    handler: { p50: 0.12, p95: 0.35, p99: 0.58 },
    dispatch: { p50: 1.1, p95: 2.3, p99: 3.5 },
  },
];

describe("OverheadTab", () => {
  it("renders empty state when overhead is null or empty", () => {
    render(<OverheadTab overhead={null} />);
    expect(screen.getByText("No overhead latency records found.")).toBeInTheDocument();
  });

  it("renders per-session latency percentiles and checks p95 < 1.0 ms", () => {
    render(<OverheadTab overhead={MOCK_OVERHEAD} />);

    // PASS status banner
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText(/Measured pooled handler p95 is 0.350 ms/)).toBeInTheDocument();

    // Table rows
    expect(screen.getByText("Pooled (All Sessions)")).toBeInTheDocument();
    expect(screen.getByText("s1-basel...")).toBeInTheDocument();
    expect(screen.getAllByText("0.120 / 0.350 / 0.580")).toHaveLength(2);
  });

  it("renders WARN banner when pooled p95 >= 1.0 ms", () => {
    const highOverhead: readonly SessionOverheadEntry[] = [
      {
        session_id: "all",
        participant_id: "all",
        events: 100,
        handler: { p50: 0.5, p95: 1.25, p99: 2.0 },
        dispatch: { p50: 1.0, p95: 2.0, p99: 3.0 },
      },
    ];
    render(<OverheadTab overhead={highOverhead} />);
    expect(screen.getByText("WARN")).toBeInTheDocument();
    expect(screen.getByText(/Measured pooled handler p95 is 1.250 ms/)).toBeInTheDocument();
  });
});
