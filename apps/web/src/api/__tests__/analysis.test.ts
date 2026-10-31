import { describe, expect, it } from "vitest";
import {
  type BigramMatrix,
  fetchOverview,
  fetchParticipantResults,
  fetchParticipantTrend,
  fetchSessionMatrix,
  type Overview,
  type ParticipantResults,
  type SessionTrendEntry,
} from "../analysis";

const MATRIX: BigramMatrix = {
  session_id: "s1",
  participant_id: "p1",
  phase: "baseline",
  wpm: 22,
  accuracy: 0.86,
  cells: [{ bigram: "th", attempts: 10, errors: 5, error_rate: 0.5, iki_median_ms: 200, iki_n: 4 }],
};

const OVERVIEW: Overview = {
  participants: [
    {
      id: "p1",
      alias: "pilot-1",
      status: "done",
      is_builder: false,
      is_blinded: true,
      completed_sessions: 4,
    },
  ],
  overhead: [
    {
      session_id: "all",
      participant_id: "all",
      events: 100,
      handler: { p50: 0.2, p95: 0.5, p99: 0.8 },
      dispatch: { p50: 1.1, p95: 2.2, p99: 3.3 },
    },
  ],
  generation: {
    arms: [
      {
        arm: "llm",
        drills_count: 5,
        attempts_count: 10,
        acceptance_rate: 0.5,
        attempts_per_drill: 2.0,
        mean_target_density: 0.25,
        mean_word_length: 4.5,
        mean_real_word_ratio: 0.98,
        tokens_per_sec: 25.0,
        mean_gen_ms: 350.0,
        peak_memory_mb: 1200.0,
      },
    ],
    total_drills: 5,
    total_attempts: 10,
  },
};

const PARTICIPANT_RESULTS: ParticipantResults = {
  participant_id: "p1",
  alias: "pilot-1",
  status: "done",
  is_builder: false,
  is_blinded: true,
  baseline_wpm: 35.0,
  baseline_accuracy: 0.95,
  retest_wpm: 42.0,
  retest_accuracy: 0.98,
  analyzed_baseline_session_ids: ["s1"],
  analyzed_retest_session_ids: ["s2"],
  posterior_draws: 100000,
  bootstrap_resamples: 10000,
  seed: 20261030,
  sets: [],
  exclusions: null,
};

const TREND: readonly SessionTrendEntry[] = [
  {
    session_id: "s1",
    phase: "baseline",
    day_index: 1,
    started_at: "2026-10-20T10:00:00Z",
    wpm: 35.0,
    accuracy: 0.95,
    per_set_error_rate: { A: 0.05 },
    per_set_attempts: { A: 20 },
    per_set_errors: { A: 1 },
  },
];

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("fetchSessionMatrix", () => {
  it("returns ok with the parsed matrix on 200", async () => {
    const result = await fetchSessionMatrix("s1", async () => jsonResponse(MATRIX, 200));
    expect(result).toEqual({ status: "ok", matrix: MATRIX });
  });

  it("maps 404 to not-found", async () => {
    const result = await fetchSessionMatrix("s1", async () => new Response(null, { status: 404 }));
    expect(result).toEqual({ status: "not-found" });
  });

  it("maps 409 to not-completed", async () => {
    const result = await fetchSessionMatrix("s1", async () => new Response(null, { status: 409 }));
    expect(result).toEqual({ status: "not-completed" });
  });

  it("maps other non-2xx to error", async () => {
    const result = await fetchSessionMatrix("s1", async () => new Response(null, { status: 500 }));
    expect(result).toEqual({ status: "error", message: "request failed with status 500" });
  });

  it("maps a thrown fetch to error", async () => {
    const result = await fetchSessionMatrix("s1", async () => {
      throw new Error("boom");
    });
    expect(result).toEqual({ status: "error", message: "boom" });
  });

  it("encodes the session id in the path", async () => {
    let seen = "";
    await fetchSessionMatrix("a/b", async (input) => {
      seen = String(input);
      return jsonResponse(MATRIX, 200);
    });
    expect(seen).toBe("/api/v1/analysis/sessions/a%2Fb/matrix");
  });
});

describe("fetchOverview", () => {
  it("returns ok with the overview on 200", async () => {
    const result = await fetchOverview(async () => jsonResponse(OVERVIEW, 200));
    expect(result).toEqual({ status: "ok", overview: OVERVIEW });
  });

  it("returns error on 500", async () => {
    const result = await fetchOverview(async () => new Response(null, { status: 500 }));
    expect(result).toEqual({ status: "error", message: "HTTP 500" });
  });

  it("returns error on network throw", async () => {
    const result = await fetchOverview(async () => {
      throw new Error("network failed");
    });
    expect(result).toEqual({ status: "error", message: "network failed" });
  });
});

describe("fetchParticipantResults", () => {
  it("returns ok with results on 200", async () => {
    const result = await fetchParticipantResults("p1", async () =>
      jsonResponse(PARTICIPANT_RESULTS, 200),
    );
    expect(result).toEqual({ status: "ok", results: PARTICIPANT_RESULTS });
  });

  it("returns not-found on 404", async () => {
    const result = await fetchParticipantResults(
      "unknown",
      async () => new Response(null, { status: 404 }),
    );
    expect(result).toEqual({ status: "not-found" });
  });

  it("returns not-done on 409", async () => {
    const result = await fetchParticipantResults("p-inprogress", async () =>
      jsonResponse({ detail: "participant study outcomes not completed" }, 409),
    );
    expect(result).toEqual({
      status: "not-done",
      message: "participant study outcomes not completed",
    });
  });

  it("returns error on 500", async () => {
    const result = await fetchParticipantResults(
      "p1",
      async () => new Response(null, { status: 500 }),
    );
    expect(result).toEqual({ status: "error", message: "HTTP 500" });
  });
});

describe("fetchParticipantTrend", () => {
  it("returns ok with trend array on 200", async () => {
    const result = await fetchParticipantTrend("p1", async () => jsonResponse(TREND, 200));
    expect(result).toEqual({ status: "ok", trend: TREND });
  });

  it("returns not-found on 404", async () => {
    const result = await fetchParticipantTrend(
      "unknown",
      async () => new Response(null, { status: 404 }),
    );
    expect(result).toEqual({ status: "not-found" });
  });

  it("returns error on network failure", async () => {
    const result = await fetchParticipantTrend("p1", async () => {
      throw new Error("timeout");
    });
    expect(result).toEqual({ status: "error", message: "timeout" });
  });
});
