// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ParticipantResults } from "../../api/analysis";
import { OutcomesTab } from "../OutcomesTab";

afterEach(() => {
  cleanup();
});

const MOCK_RESULTS: ParticipantResults = {
  participant_id: "p1",
  alias: "pilot-1",
  status: "done",
  is_builder: false,
  is_blinded: true,
  baseline_wpm: 40.0,
  baseline_accuracy: 0.95,
  retest_wpm: 46.0,
  retest_accuracy: 0.98,
  analyzed_baseline_session_ids: ["s1", "s2"],
  analyzed_retest_session_ids: ["s3", "s4"],
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
      baseline_attempts: 100,
      baseline_errors: 10,
      baseline_error_rate: 0.1,
      baseline_beta_ci_lower: 0.05,
      baseline_beta_ci_upper: 0.16,
      retest_attempts: 100,
      retest_errors: 8,
      retest_error_rate: 0.08,
      retest_beta_ci_lower: 0.04,
      retest_beta_ci_upper: 0.14,
      error_rate_change: -0.02,
      targeting_effect: null,
      posterior_effect_median: null,
      posterior_effect_ci_lower: null,
      posterior_effect_ci_upper: null,
      share_below_zero: null,
      baseline_iki_n: 80,
      baseline_iki_median_ms: 180.0,
      baseline_iki_iqr_ms: 40.0,
      retest_iki_n: 80,
      retest_iki_median_ms: 170.0,
      retest_iki_iqr_ms: 35.0,
      iki_change_ms: -10.0,
      iki_targeting_effect_ms: null,
      iki_bootstrap_median_ms: null,
      iki_bootstrap_ci_lower_ms: null,
      iki_bootstrap_ci_upper_ms: null,
    },
    {
      set_label: "B",
      arm: "heuristic",
      bigrams: ["er", "in"],
      retained_bigrams: ["er"],
      dropped_bigrams: ["in"],
      baseline_attempts: 100,
      baseline_errors: 12,
      baseline_error_rate: 0.12,
      baseline_beta_ci_lower: 0.06,
      baseline_beta_ci_upper: 0.19,
      retest_attempts: 100,
      retest_errors: 4,
      retest_error_rate: 0.04,
      retest_beta_ci_lower: 0.01,
      retest_beta_ci_upper: 0.09,
      error_rate_change: -0.08,
      targeting_effect: -0.06,
      posterior_effect_median: -0.058,
      posterior_effect_ci_lower: -0.11,
      posterior_effect_ci_upper: -0.005,
      share_below_zero: 0.985,
      baseline_iki_n: 70,
      baseline_iki_median_ms: 195.0,
      baseline_iki_iqr_ms: 45.0,
      retest_iki_n: 75,
      retest_iki_median_ms: 165.0,
      retest_iki_iqr_ms: 30.0,
      iki_change_ms: -30.0,
      iki_targeting_effect_ms: -20.0,
      iki_bootstrap_median_ms: -19.5,
      iki_bootstrap_ci_lower_ms: -35.0,
      iki_bootstrap_ci_upper_ms: -4.0,
    },
  ],
  exclusions: {
    excluded_sessions: [
      {
        session_id: "s-superseded-1234",
        phase: "baseline",
        day_index: 1,
        reason: "superseded",
      },
    ],
    dropped_bigrams: [
      {
        bigram: "in",
        set_label: "B",
        arm: "heuristic",
        retest_attempts: 12,
      },
    ],
    pause_counts: { "A:baseline": 2, "B:retest": 1 },
  },
};

describe("OutcomesTab", () => {
  it("displays banner when participant is not-done (409)", () => {
    render(
      <OutcomesTab
        results={null}
        loadState={{ status: "not-done", message: "participant status is 'practice'" }}
      />,
    );
    expect(
      screen.getByText(
        /Outcomes unlock after study completion; current phase has not concluded \(participant status is 'practice'\)\./,
      ),
    ).toBeInTheDocument();
  });

  it("renders tables, control set badge, and interval plots when participant is done", () => {
    render(<OutcomesTab results={MOCK_RESULTS} loadState={{ status: "ok" }} />);

    expect(screen.getAllByText("Control Set (Held-out)")).toHaveLength(2);
    expect(screen.getAllByText("heuristic")).toHaveLength(2);
    expect(
      screen.getByText("Primary Outcome: Error Rate Targeting Effect E(s) = d(s) - d(control)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Key Secondary Outcome: Median IKI Targeting Effect F(s) = c(s) - c(control)",
      ),
    ).toBeInTheDocument();

    // Whisker plot labels
    expect(screen.getAllByText("Set B (heuristic)")).toHaveLength(2);
  });

  it("renders exclusions card with dropped bigrams when present", () => {
    render(<OutcomesTab results={MOCK_RESULTS} loadState={{ status: "ok" }} />);

    expect(screen.getByText('Pre-registered Exclusions Report (D20, D23)')).toBeInTheDocument();
    expect(screen.getByText('"in"')).toBeInTheDocument();
    expect(screen.getByText(/12 attempts/)).toBeInTheDocument();
    expect(screen.getByText(/superseded/)).toBeInTheDocument();
  });
});
