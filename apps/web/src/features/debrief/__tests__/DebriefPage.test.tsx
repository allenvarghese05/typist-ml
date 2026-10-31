// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ParticipantResults } from "../../../api/analysis";
import type { ParticipantResponse } from "../../../api/client";
import { DebriefPage } from "../DebriefPage";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

const MOCK_PARTICIPANTS: readonly ParticipantResponse[] = [
  {
    id: "p-done",
    alias: "pilot-completed",
    status: "done",
    is_builder: false,
    is_blinded: true,
    created_at: "2026-10-20T00:00:00Z",
    consent_at: "2026-10-20T00:00:00Z",
  },
  {
    id: "p-practice",
    alias: "pilot-practicing",
    status: "practice",
    is_builder: false,
    is_blinded: true,
    created_at: "2026-10-21T00:00:00Z",
    consent_at: "2026-10-21T00:00:00Z",
  },
  {
    id: "p-builder",
    alias: "builder-user",
    status: "done",
    is_builder: true,
    is_blinded: false,
    created_at: "2026-10-19T00:00:00Z",
    consent_at: "2026-10-19T00:00:00Z",
  },
];

const MOCK_RESULTS_DONE: ParticipantResults = {
  participant_id: "p-done",
  alias: "pilot-completed",
  status: "done",
  is_builder: false,
  is_blinded: true,
  baseline_wpm: 42.0,
  baseline_accuracy: 0.94,
  retest_wpm: 52.0,
  retest_accuracy: 0.98,
  analyzed_baseline_session_ids: ["s-base-1", "s-base-2"],
  analyzed_retest_session_ids: ["s-ret-1", "s-ret-2"],
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
    {
      set_label: "C",
      arm: "markov",
      bigrams: ["an"],
      retained_bigrams: ["an"],
      dropped_bigrams: [],
      baseline_attempts: 100,
      baseline_errors: 11,
      baseline_error_rate: 0.11,
      baseline_beta_ci_lower: 0.06,
      baseline_beta_ci_upper: 0.18,
      retest_attempts: 100,
      retest_errors: 3,
      retest_error_rate: 0.03,
      retest_beta_ci_lower: 0.01,
      retest_beta_ci_upper: 0.08,
      error_rate_change: -0.08,
      targeting_effect: -0.06,
      posterior_effect_median: -0.059,
      posterior_effect_ci_lower: -0.112,
      posterior_effect_ci_upper: -0.006,
      share_below_zero: 0.988,
      baseline_iki_n: 72,
      baseline_iki_median_ms: 190.0,
      baseline_iki_iqr_ms: 42.0,
      retest_iki_n: 78,
      retest_iki_median_ms: 162.0,
      retest_iki_iqr_ms: 28.0,
      iki_change_ms: -28.0,
      iki_targeting_effect_ms: -18.0,
      iki_bootstrap_median_ms: -17.8,
      iki_bootstrap_ci_lower_ms: -32.0,
      iki_bootstrap_ci_upper_ms: -3.5,
    },
    {
      set_label: "D",
      arm: "llm",
      bigrams: ["qu"],
      retained_bigrams: ["qu"],
      dropped_bigrams: [],
      baseline_attempts: 100,
      baseline_errors: 15,
      baseline_error_rate: 0.15,
      baseline_beta_ci_lower: 0.09,
      baseline_beta_ci_upper: 0.23,
      retest_attempts: 100,
      retest_errors: 2,
      retest_error_rate: 0.02,
      retest_beta_ci_lower: 0.003,
      retest_beta_ci_upper: 0.065,
      error_rate_change: -0.13,
      targeting_effect: -0.11,
      posterior_effect_median: -0.108,
      posterior_effect_ci_lower: -0.165,
      posterior_effect_ci_upper: -0.051,
      share_below_zero: 0.999,
      baseline_iki_n: 65,
      baseline_iki_median_ms: 210.0,
      baseline_iki_iqr_ms: 50.0,
      retest_iki_n: 74,
      retest_iki_median_ms: 160.0,
      retest_iki_iqr_ms: 25.0,
      iki_change_ms: -50.0,
      iki_targeting_effect_ms: -40.0,
      iki_bootstrap_median_ms: -39.5,
      iki_bootstrap_ci_lower_ms: -58.0,
      iki_bootstrap_ci_upper_ms: -21.0,
    },
  ],
  exclusions: {
    excluded_sessions: [
      {
        session_id: "s-abandoned-99",
        phase: "baseline",
        day_index: 1,
        reason: "abandoned",
      },
    ],
    dropped_bigrams: [
      {
        bigram: "in",
        set_label: "B",
        arm: "heuristic",
        retest_attempts: 14,
      },
    ],
    pause_counts: { "A:baseline": 1 },
  },
};

const MOCK_RETEST_MATRIX = {
  session_id: "s-ret-1",
  participant_id: "p-done",
  phase: "retest",
  wpm: 52.0,
  accuracy: 0.98,
  cells: [
    { bigram: "th", attempts: 50, errors: 4, error_rate: 0.08, iki_median_ms: 170.0, iki_n: 45 },
    { bigram: "er", attempts: 50, errors: 1, error_rate: 0.02, iki_median_ms: 165.0, iki_n: 48 },
    { bigram: "an", attempts: 50, errors: 1, error_rate: 0.02, iki_median_ms: 162.0, iki_n: 49 },
    { bigram: "qu", attempts: 50, errors: 1, error_rate: 0.02, iki_median_ms: 160.0, iki_n: 48 },
  ],
};

function createFakeFetch() {
  return async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.endsWith("/participants")) {
      return new Response(JSON.stringify(MOCK_PARTICIPANTS), { status: 200 });
    }

    if (url.includes("/analysis/participants/p-done")) {
      return new Response(JSON.stringify(MOCK_RESULTS_DONE), { status: 200 });
    }

    if (url.includes("/analysis/participants/p-builder")) {
      return new Response(
        JSON.stringify({
          ...MOCK_RESULTS_DONE,
          participant_id: "p-builder",
          alias: "builder-user",
          is_builder: true,
          is_blinded: false,
        }),
        { status: 200 },
      );
    }

    if (url.includes("/analysis/participants/p-practice")) {
      return new Response(
        JSON.stringify({
          detail: "participant 'p-practice' status is 'practice', expected 'done'",
        }),
        { status: 409 },
      );
    }

    if (url.includes("/analysis/sessions/") && url.endsWith("/matrix")) {
      return new Response(JSON.stringify(MOCK_RETEST_MATRIX), { status: 200 });
    }

    return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
  };
}

describe("DebriefPage", () => {
  it("renders locked view when participant is in practice phase (409) and hides all arm mappings", async () => {
    const fakeFetch = createFakeFetch();
    render(<DebriefPage initialParticipantId="p-practice" fetchImpl={fakeFetch as typeof fetch} />);

    expect(await screen.findByTestId("debrief-locked")).toBeInTheDocument();
    expect(
      screen.getByText(/Study Debrief Locked \(Experimental Blinding Active\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Status: practice/)).toBeInTheDocument();

    // STRICT BLINDING VALIDATION: ZERO arm names or generator identities must be rendered
    const pageHtml = screen.getByTestId("debrief-page").innerHTML;
    expect(pageHtml).not.toContain("heuristic");
    expect(pageHtml).not.toContain("Dictionary Heuristic");
    expect(pageHtml).not.toContain("markov");
    expect(pageHtml).not.toContain("Markov Chain");
    expect(pageHtml).not.toContain("llm");
    expect(pageHtml).not.toContain("On-device 1B LLM");
    expect(pageHtml).not.toContain("control");
    expect(pageHtml).not.toContain("Targeting Effect");
  });

  it("renders unblinded arm reveal and outcomes when participant is done", async () => {
    const fakeFetch = createFakeFetch();
    render(<DebriefPage initialParticipantId="p-done" fetchImpl={fakeFetch as typeof fetch} />);

    expect(await screen.findByTestId("debrief-revealed")).toBeInTheDocument();
    expect(screen.getByText("Control (held-out)")).toBeInTheDocument();
    expect(screen.getByText("Dictionary Heuristic")).toBeInTheDocument();
    expect(screen.getByText("Markov Chain")).toBeInTheDocument();
    expect(screen.getByText("On-device 1B LLM")).toBeInTheDocument();

    expect(
      screen.getByText("Primary Confirmatory Outcome: Error Rate Targeting Effect E(s)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Key Secondary Outcome: Median IKI Targeting Effect F(s)"),
    ).toBeInTheDocument();
    expect(screen.getByText("Peer (Blinded)")).toBeInTheDocument();
  });

  it("allows participant to toggle arm reveal between unmasked and masked view", async () => {
    const fakeFetch = createFakeFetch();
    render(<DebriefPage initialParticipantId="p-done" fetchImpl={fakeFetch as typeof fetch} />);

    expect(await screen.findByTestId("toggle-reveal-btn")).toBeInTheDocument();
    expect(screen.getByText("Dictionary Heuristic")).toBeInTheDocument();

    // Click toggle to mask
    fireEvent.click(screen.getByTestId("toggle-reveal-btn"));
    expect(screen.getByText("Reveal Arm Identities")).toBeInTheDocument();
    expect(screen.getByText("Masked (Block 2)")).toBeInTheDocument();
    expect(screen.queryByText("Dictionary Heuristic")).not.toBeInTheDocument();

    // Click toggle to re-reveal
    fireEvent.click(screen.getByTestId("toggle-reveal-btn"));
    expect(screen.getByText("Mask Arm Identities")).toBeInTheDocument();
    expect(screen.getByText("Dictionary Heuristic")).toBeInTheDocument();
  });

  it("renders participant selector and switches participant view", async () => {
    const fakeFetch = createFakeFetch();
    render(<DebriefPage initialParticipantId="p-done" fetchImpl={fakeFetch as typeof fetch} />);

    expect(await screen.findByTestId("debrief-revealed")).toBeInTheDocument();

    // Switch to practice participant
    const select = screen.getByLabelText("Participant selector");
    fireEvent.change(select, { target: { value: "p-practice" } });

    expect(await screen.findByTestId("debrief-locked")).toBeInTheDocument();
  });

  it("displays Builder (Unblinded) badge for builder participants", async () => {
    const fakeFetch = createFakeFetch();
    render(<DebriefPage initialParticipantId="p-builder" fetchImpl={fakeFetch as typeof fetch} />);

    expect(await screen.findByText("Builder (Unblinded)")).toBeInTheDocument();
  });

  it("displays diagnostic feedback for persistent weak bigrams with >5% retest error rate", async () => {
    const fakeFetch = createFakeFetch();
    render(<DebriefPage initialParticipantId="p-done" fetchImpl={fakeFetch as typeof fetch} />);

    const card = await screen.findByTestId("diagnostic-nudges-card");
    expect(card).toBeInTheDocument();
    // "th" had 8% error rate in mock retest matrix -> must be listed as nudge in the diagnostic card
    expect(within(card).getByText('"th"')).toBeInTheDocument();
    expect(within(card).getByText(/8.0% error rate/)).toBeInTheDocument();
  });

  it("renders exclusions report with dropped bigrams and excluded sessions", async () => {
    const fakeFetch = createFakeFetch();
    render(<DebriefPage initialParticipantId="p-done" fetchImpl={fakeFetch as typeof fetch} />);

    expect(
      await screen.findByText("Pre-registered Exclusions Report (D20, D23)"),
    ).toBeInTheDocument();
    expect(screen.getByText("s-abando...")).toBeInTheDocument();
    expect(screen.getByText(/abandoned/)).toBeInTheDocument();
    expect(screen.getByText(/14 attempts/)).toBeInTheDocument();
  });
});
