// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SessionTrendEntry } from "../../api/analysis";
import { TrendTab } from "../TrendTab";

afterEach(() => {
  cleanup();
});

const MOCK_TREND: readonly SessionTrendEntry[] = [
  {
    session_id: "s1-baseline-id-1234",
    phase: "baseline",
    day_index: 1,
    started_at: "2026-10-20T10:00:00Z",
    wpm: 38.45,
    accuracy: 0.945,
    per_set_error_rate: { A: 0.05, B: 0.08, C: 0.12, D: 0.06 },
    per_set_attempts: { A: 20, B: 25, C: 25, D: 20 },
    per_set_errors: { A: 1, B: 2, C: 3, D: 1 },
  },
  {
    session_id: "s2-practice-id-5678",
    phase: "practice",
    day_index: 2,
    started_at: "2026-10-21T10:00:00Z",
    wpm: 42.1,
    accuracy: 0.962,
    per_set_error_rate: { A: 0.04, B: 0.05, C: 0.07, D: 0.04 },
    per_set_attempts: { A: 25, B: 25, C: 25, D: 25 },
    per_set_errors: { A: 1, B: 1, C: 2, D: 1 },
  },
];

describe("TrendTab", () => {
  it("renders empty state when trend is empty", () => {
    render(<TrendTab trend={[]} loading={false} />);
    expect(screen.getByText("No completed sessions for this participant yet.")).toBeInTheDocument();
  });

  it("renders session table with formatted metrics and sets A-D error rates", () => {
    render(<TrendTab trend={MOCK_TREND} loading={false} />);

    expect(screen.getByText("Completed Sessions Log")).toBeInTheDocument();
    expect(screen.getByText("Session Performance Trajectory")).toBeInTheDocument();

    // Table headers
    expect(screen.getByText("Set A Error Rate")).toBeInTheDocument();
    expect(screen.getByText("Set B Error Rate")).toBeInTheDocument();
    expect(screen.getByText("Set C Error Rate")).toBeInTheDocument();
    expect(screen.getByText("Set D Error Rate")).toBeInTheDocument();

    // Day indices and phases
    expect(screen.getByText("Day 1")).toBeInTheDocument();
    expect(screen.getByText("baseline")).toBeInTheDocument();
    expect(screen.getByText("Day 2")).toBeInTheDocument();
    expect(screen.getByText("practice")).toBeInTheDocument();

    // Metric formatting
    expect(screen.getByText("38.5")).toBeInTheDocument();
    expect(screen.getByText("94.5%")).toBeInTheDocument();
    expect(screen.getAllByText("5.0%")).toHaveLength(2);
    expect(screen.getByText("8.0%")).toBeInTheDocument();

    expect(screen.getByText("42.1")).toBeInTheDocument();
    expect(screen.getByText("96.2%")).toBeInTheDocument();

    // SVG elements
    const svg = screen.getByRole("img", { name: "Performance trajectory line chart" });
    expect(svg).toBeInTheDocument();
  });
});
