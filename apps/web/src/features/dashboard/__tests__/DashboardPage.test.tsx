// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Overview, ParticipantResults, SessionTrendEntry } from "../../../api/analysis";
import { DashboardPage } from "../DashboardPage";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

const MOCK_OVERVIEW: Overview = {
  participants: [
    {
      id: "p1",
      alias: "pilot-1",
      status: "done",
      is_builder: true,
      is_blinded: false,
      completed_sessions: 4,
    },
    {
      id: "p2",
      alias: "peer-2",
      status: "practice",
      is_builder: false,
      is_blinded: true,
      completed_sessions: 2,
    },
  ],
  overhead: [
    {
      session_id: "all",
      participant_id: "all",
      events: 500,
      handler: { p50: 0.15, p95: 0.42, p99: 0.75 },
      dispatch: { p50: 1.0, p95: 2.0, p99: 3.0 },
    },
  ],
  generation: {
    arms: [
      {
        arm: "control",
        drills_count: 5,
        attempts_count: 5,
        acceptance_rate: 1.0,
        attempts_per_drill: 1.0,
        mean_target_density: 0.0,
        mean_word_length: 4.5,
        mean_real_word_ratio: 1.0,
        tokens_per_sec: null,
        mean_gen_ms: null,
        peak_memory_mb: null,
      },
    ],
    total_drills: 5,
    total_attempts: 5,
  },
};

const MOCK_RESULTS_P1: ParticipantResults = {
  participant_id: "p1",
  alias: "pilot-1",
  status: "done",
  is_builder: true,
  is_blinded: false,
  baseline_wpm: 38.0,
  baseline_accuracy: 0.95,
  retest_wpm: 44.0,
  retest_accuracy: 0.98,
  analyzed_baseline_session_ids: ["s1"],
  analyzed_retest_session_ids: ["s2"],
  posterior_draws: 100000,
  bootstrap_resamples: 10000,
  seed: 20261030,
  sets: [
    {
      set_label: "A",
      arm: "control",
      bigrams: ["th"],
      retained_bigrams: ["th"],
      dropped_bigrams: [],
      baseline_attempts: 50,
      baseline_errors: 5,
      baseline_error_rate: 0.1,
      baseline_beta_ci_lower: 0.04,
      baseline_beta_ci_upper: 0.18,
      retest_attempts: 50,
      retest_errors: 3,
      retest_error_rate: 0.06,
      retest_beta_ci_lower: 0.02,
      retest_beta_ci_upper: 0.14,
      error_rate_change: -0.04,
      targeting_effect: null,
      posterior_effect_median: null,
      posterior_effect_ci_lower: null,
      posterior_effect_ci_upper: null,
      share_below_zero: null,
      baseline_iki_n: 40,
      baseline_iki_median_ms: 180.0,
      baseline_iki_iqr_ms: 30.0,
      retest_iki_n: 40,
      retest_iki_median_ms: 170.0,
      retest_iki_iqr_ms: 25.0,
      iki_change_ms: -10.0,
      iki_targeting_effect_ms: null,
      iki_bootstrap_median_ms: null,
      iki_bootstrap_ci_lower_ms: null,
      iki_bootstrap_ci_upper_ms: null,
    },
  ],
  exclusions: {
    excluded_sessions: [],
    dropped_bigrams: [],
    pause_counts: {},
  },
};

const MOCK_TREND_P1: readonly SessionTrendEntry[] = [
  {
    session_id: "s1",
    phase: "baseline",
    day_index: 1,
    started_at: "2026-10-20T10:00:00Z",
    wpm: 38.0,
    accuracy: 0.95,
    per_set_error_rate: { A: 0.1 },
    per_set_attempts: { A: 50 },
    per_set_errors: { A: 5 },
  },
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function makeFetchFake() {
  return async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/analysis/overview")) {
      return jsonResponse(MOCK_OVERVIEW);
    }
    if (url.includes("/analysis/participants/p1/trend")) {
      return jsonResponse(MOCK_TREND_P1);
    }
    if (url.includes("/analysis/participants/p2/trend")) {
      return jsonResponse([]);
    }
    if (url.includes("/analysis/participants/p1")) {
      return jsonResponse(MOCK_RESULTS_P1);
    }
    if (url.includes("/analysis/participants/p2")) {
      return jsonResponse({ detail: "participant status is practice" }, 409);
    }
    return new Response(null, { status: 404 });
  };
}

describe("DashboardPage", () => {
  it("renders dashboard with participant picker and default outcomes tab", async () => {
    const fetchFake = makeFetchFake();
    render(<DashboardPage fetchImpl={fetchFake} />);

    await waitFor(() => {
      expect(screen.getByText("Analysis Dashboard")).toBeInTheDocument();
    });

    // Participant selector dropdown
    expect(screen.getByLabelText("Participant selector")).toBeInTheDocument();
    expect(screen.getByText("Builder (Unblinded)")).toBeInTheDocument();

    // Default outcomes tab loaded
    await waitFor(() => {
      expect(screen.getAllByText("Control Set (Held-out)")).toHaveLength(2);
    });
  });

  it("switches tabs and updates hash query parameters", async () => {
    const fetchFake = makeFetchFake();
    render(<DashboardPage fetchImpl={fetchFake} />);

    await waitFor(() => {
      expect(screen.getByText("Analysis Dashboard")).toBeInTheDocument();
    });

    const trendTabBtn = screen.getByRole("button", { name: "Session Trend" });
    act(() => {
      fireEvent.click(trendTabBtn);
    });

    await waitFor(() => {
      expect(screen.getByText("Session Performance Trajectory")).toBeInTheDocument();
    });

    expect(window.location.hash).toContain("tab=trend");

    const genTabBtn = screen.getByRole("button", { name: "Drill Generation" });
    act(() => {
      fireEvent.click(genTabBtn);
    });

    await waitFor(() => {
      expect(screen.getByText("Total Drills Generated")).toBeInTheDocument();
    });

    expect(window.location.hash).toContain("tab=generation");
  });

  it("switches selected participant and re-fetches participant data", async () => {
    const fetchFake = makeFetchFake();
    render(<DashboardPage fetchImpl={fetchFake} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Participant selector")).toBeInTheDocument();
    });

    const select = screen.getByLabelText("Participant selector");
    act(() => {
      fireEvent.change(select, { target: { value: "p2" } });
    });

    await waitFor(() => {
      expect(screen.getByText("Peer (Blinded)")).toBeInTheDocument();
    });

    // Outcomes tab should now show the 409 not-done banner for p2
    await waitFor(() => {
      expect(
        screen.getByText(/Outcomes unlock after study completion; current phase has not concluded/),
      ).toBeInTheDocument();
    });

    expect(window.location.hash).toContain("participant=p2");
  });
});
