// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { BigramMatrix } from "../../api/analysis";
import { MatrixTab } from "../MatrixTab";

afterEach(() => {
  cleanup();
});

const MOCK_SESSIONS = [
  { id: "s1-baseline", phase: "baseline", day_index: 1 },
  { id: "s2-retest", phase: "retest", day_index: 2 },
];

const MOCK_MATRIX: BigramMatrix = {
  session_id: "s1-baseline",
  participant_id: "p1",
  phase: "baseline",
  wpm: 34.0,
  accuracy: 0.95,
  cells: [
    {
      bigram: "th",
      attempts: 20,
      errors: 2,
      error_rate: 0.1,
      iki_median_ms: 180.0,
      iki_n: 18,
    },
    {
      bigram: "he",
      attempts: 25,
      errors: 0,
      error_rate: 0.0,
      iki_median_ms: 150.0,
      iki_n: 25,
    },
  ],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("MatrixTab", () => {
  it("renders empty state when no sessions are provided", () => {
    render(<MatrixTab sessions={[]} />);
    expect(
      screen.getByText("No completed sessions available to display bigram matrix."),
    ).toBeInTheDocument();
  });

  it("renders session selector dropdown and loads matrix", async () => {
    const fetchFake = async () => jsonResponse(MOCK_MATRIX);
    render(<MatrixTab sessions={MOCK_SESSIONS} fetchImpl={fetchFake} />);

    expect(screen.getByLabelText("Session selector")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Day 1 \(baseline\)/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Day 2 \(retest\)/ })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Recorded Bigrams:")).toBeInTheDocument();
    });

    const thCell = document.querySelector('[data-cell-bigram="th"]');
    expect(thCell).toBeInTheDocument();
    expect(thCell).toHaveAttribute("data-value", "0.1");
    expect(thCell).toHaveAttribute("title", "th: 2/20 errors; IKI 180 ms (n=18)");
  });

  it("toggles between error rate and median IKI metrics", async () => {
    const fetchFake = async () => jsonResponse(MOCK_MATRIX);
    render(<MatrixTab sessions={MOCK_SESSIONS} fetchImpl={fetchFake} />);

    await waitFor(() => {
      expect(screen.getByText("Recorded Bigrams:")).toBeInTheDocument();
    });

    const ikiButton = screen.getByRole("button", { name: "Median IKI" });
    fireEvent.click(ikiButton);

    const thCell = document.querySelector('[data-cell-bigram="th"]');
    expect(thCell).toHaveAttribute("data-metric", "iki");
    expect(thCell).toHaveAttribute("data-value", "180");
  });
});
