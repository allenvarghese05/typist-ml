import type { SessionTrendEntry } from "./client";
import { apiPath } from "./paths";

export type { SessionTrendEntry };

/** One bigram cell, mirroring the Pydantic MatrixCell (hand-written; no openapi-typescript yet). */
export interface MatrixCell {
  readonly bigram: string;
  readonly attempts: number;
  readonly errors: number;
  /** errors / attempts, computed server-side; null when attempts == 0. */
  readonly error_rate: number | null;
  /** Median IKI in ms; null exactly when iki_n == 0. */
  readonly iki_median_ms: number | null;
  readonly iki_n: number;
}

/** A completed session's bigram matrix, mirroring the Pydantic BigramMatrix. */
export interface BigramMatrix {
  readonly session_id: string;
  readonly participant_id: string;
  readonly phase: string;
  readonly wpm: number | null;
  readonly accuracy: number | null;
  readonly cells: readonly MatrixCell[];
}

/** The outcome of fetchSessionMatrix: a discriminated union the page renders directly. */
export type MatrixResult =
  | { readonly status: "ok"; readonly matrix: BigramMatrix }
  | { readonly status: "not-found" }
  | { readonly status: "not-completed" }
  | { readonly status: "error"; readonly message: string };

/**
 * GET /api/v1/analysis/sessions/{sessionId}/matrix. fetchImpl is injected so tests pass a fake
 * (the EventBuffer transport pattern); it defaults to the global fetch. Maps 404 -> "not-found",
 * 409 -> "not-completed", any other non-2xx or a thrown error -> "error", 2xx -> "ok".
 */
export async function fetchSessionMatrix(
  sessionId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<MatrixResult> {
  let response: Response;
  try {
    response = await fetchImpl(
      apiPath(`/analysis/sessions/${encodeURIComponent(sessionId)}/matrix`),
    );
  } catch (error) {
    return { status: "error", message: error instanceof Error ? error.message : "network error" };
  }
  if (response.status === 404) {
    return { status: "not-found" };
  }
  if (response.status === 409) {
    return { status: "not-completed" };
  }
  if (!response.ok) {
    return { status: "error", message: `request failed with status ${response.status}` };
  }
  const matrix = (await response.json()) as BigramMatrix;
  return { status: "ok", matrix };
}

export interface ParticipantSummary {
  readonly id: string;
  readonly alias: string;
  readonly status: string;
  readonly is_builder: boolean;
  readonly is_blinded: boolean;
  readonly completed_sessions: number;
}

export interface Percentiles {
  readonly p50: number;
  readonly p95: number;
  readonly p99: number;
}

export interface SessionOverheadEntry {
  readonly session_id: string;
  readonly participant_id: string;
  readonly events: number;
  readonly handler: Percentiles | null;
  readonly dispatch: Percentiles | null;
}

export interface ArmGenerationSummary {
  readonly arm: string;
  readonly drills_count: number;
  readonly attempts_count: number;
  readonly acceptance_rate: number | null;
  readonly attempts_per_drill: number | null;
  readonly mean_target_density: number | null;
  readonly mean_word_length: number | null;
  readonly mean_real_word_ratio: number | null;
  readonly tokens_per_sec: number | null;
  readonly mean_gen_ms: number | null;
  readonly peak_memory_mb: number | null;
}

export interface GenerationOverview {
  readonly arms: readonly ArmGenerationSummary[];
  readonly total_drills: number;
  readonly total_attempts: number;
}

export interface Overview {
  readonly participants: readonly ParticipantSummary[];
  readonly overhead: readonly SessionOverheadEntry[];
  readonly generation: GenerationOverview;
}

export interface ExcludedSession {
  readonly session_id: string;
  readonly phase: string;
  readonly day_index: number;
  readonly reason: string;
}

export interface DroppedBigram {
  readonly bigram: string;
  readonly set_label: string;
  readonly arm: string;
  readonly retest_attempts: number;
}

export interface ExclusionsReport {
  readonly excluded_sessions: readonly ExcludedSession[];
  readonly dropped_bigrams: readonly DroppedBigram[];
  readonly pause_counts: Record<string, number>;
}

export interface SetOutcome {
  readonly set_label: string;
  readonly arm: string;
  readonly bigrams: readonly string[];
  readonly retained_bigrams: readonly string[];
  readonly dropped_bigrams: readonly string[];
  readonly baseline_attempts: number;
  readonly baseline_errors: number;
  readonly baseline_error_rate: number | null;
  readonly baseline_beta_ci_lower: number | null;
  readonly baseline_beta_ci_upper: number | null;
  readonly retest_attempts: number;
  readonly retest_errors: number;
  readonly retest_error_rate: number | null;
  readonly retest_beta_ci_lower: number | null;
  readonly retest_beta_ci_upper: number | null;
  readonly error_rate_change: number | null;
  readonly targeting_effect: number | null;
  readonly posterior_effect_median: number | null;
  readonly posterior_effect_ci_lower: number | null;
  readonly posterior_effect_ci_upper: number | null;
  readonly share_below_zero: number | null;
  readonly baseline_iki_n: number;
  readonly baseline_iki_median_ms: number | null;
  readonly baseline_iki_iqr_ms: number | null;
  readonly retest_iki_n: number;
  readonly retest_iki_median_ms: number | null;
  readonly retest_iki_iqr_ms: number | null;
  readonly iki_change_ms: number | null;
  readonly iki_targeting_effect_ms: number | null;
  readonly iki_bootstrap_median_ms: number | null;
  readonly iki_bootstrap_ci_lower_ms: number | null;
  readonly iki_bootstrap_ci_upper_ms: number | null;
}

export interface ParticipantResults {
  readonly participant_id: string;
  readonly alias: string;
  readonly status: string;
  readonly is_builder: boolean;
  readonly is_blinded: boolean;
  readonly baseline_wpm: number | null;
  readonly baseline_accuracy: number | null;
  readonly retest_wpm: number | null;
  readonly retest_accuracy: number | null;
  readonly analyzed_baseline_session_ids: readonly string[];
  readonly analyzed_retest_session_ids: readonly string[];
  readonly posterior_draws: number;
  readonly bootstrap_resamples: number;
  readonly seed: number;
  readonly sets: readonly SetOutcome[];
  readonly exclusions: ExclusionsReport | null;
}

export type OverviewResult =
  | { readonly status: "ok"; readonly overview: Overview }
  | { readonly status: "error"; readonly message: string };

export type ParticipantResultsResult =
  | { readonly status: "ok"; readonly results: ParticipantResults }
  | { readonly status: "not-found" }
  | { readonly status: "not-done"; readonly message: string }
  | { readonly status: "error"; readonly message: string };

export type TrendResult =
  | { readonly status: "ok"; readonly trend: readonly SessionTrendEntry[] }
  | { readonly status: "not-found" }
  | { readonly status: "error"; readonly message: string };

export async function fetchOverview(
  fetchImpl: typeof fetch = fetch,
): Promise<OverviewResult> {
  try {
    const response = await fetchImpl(apiPath("/analysis/overview"));
    if (!response.ok) {
      return { status: "error", message: `HTTP ${response.status}` };
    }
    const overview = (await response.json()) as Overview;
    return { status: "ok", overview };
  } catch (error) {
    return { status: "error", message: error instanceof Error ? error.message : "network error" };
  }
}

export async function fetchParticipantResults(
  participantId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ParticipantResultsResult> {
  try {
    const response = await fetchImpl(
      apiPath(`/analysis/participants/${encodeURIComponent(participantId)}`),
    );
    if (response.status === 404) {
      return { status: "not-found" };
    }
    if (response.status === 409) {
      let msg = "Participant study outcomes not completed";
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) msg = body.detail;
      } catch {
        // ignore
      }
      return { status: "not-done", message: msg };
    }
    if (!response.ok) {
      return { status: "error", message: `HTTP ${response.status}` };
    }
    const results = (await response.json()) as ParticipantResults;
    return { status: "ok", results };
  } catch (error) {
    return { status: "error", message: error instanceof Error ? error.message : "network error" };
  }
}

export async function fetchParticipantTrend(
  participantId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<TrendResult> {
  try {
    const response = await fetchImpl(
      apiPath(`/analysis/participants/${encodeURIComponent(participantId)}/trend`),
    );
    if (response.status === 404) {
      return { status: "not-found" };
    }
    if (!response.ok) {
      return { status: "error", message: `HTTP ${response.status}` };
    }
    const trend = (await response.json()) as readonly SessionTrendEntry[];
    return { status: "ok", trend };
  } catch (error) {
    return { status: "error", message: error instanceof Error ? error.message : "network error" };
  }
}
