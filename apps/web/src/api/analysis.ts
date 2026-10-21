import { apiPath } from "./paths";

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
