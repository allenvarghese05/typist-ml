import { apiPath } from "./paths";

export interface ParticipantResponse {
  readonly id: string;
  readonly alias: string;
  readonly status: string;
  readonly is_builder: boolean;
  readonly is_blinded: boolean;
  readonly keyboard_label?: string | null;
  readonly created_at: string;
  readonly consent_at: string | null;
}

export interface BlockPlan {
  readonly block_id: string;
  readonly block_index: number;
  readonly label: string;
  readonly target_text: string;
  readonly started_at: string | null;
  readonly ended_at: string | null;
}

export interface SessionPlan {
  readonly session_id: string;
  readonly participant_id: string;
  readonly phase: "baseline" | "practice" | "retest" | string;
  readonly day_index: number;
  readonly status: string;
  readonly blocks: readonly BlockPlan[];
}

export interface BlockResponse {
  readonly id: string;
  readonly session_id: string;
  readonly block_index: number;
  readonly label: string;
  readonly started_at: string | null;
  readonly ended_at: string | null;
}

export interface SessionSummary {
  readonly session_id: string;
  readonly wpm: number | null;
  readonly accuracy: number | null;
  readonly bigram_count: number;
  readonly blocks: number;
}

export interface AssignmentResponse {
  readonly participant_id: string;
  readonly status: string;
  readonly frozen_bigrams: number;
  readonly mapping: Record<string, string>;
  readonly form_b_composed: boolean;
}

export interface ArmPoolStatus {
  readonly arm: string;
  readonly ready_count: number;
  readonly target_count: number;
  readonly queued_count: number;
  readonly used_count: number;
  readonly deficit: number;
  readonly is_ready: boolean;
}

export interface PoolResponse {
  readonly participant_id: string;
  readonly alias: string;
  readonly arms: readonly ArmPoolStatus[];
}

export interface JobResponse {
  readonly id: string;
  readonly participant_id: string;
  readonly arm: string;
  readonly requested: number;
  readonly status: "pending" | "running" | "done" | "failed";
  readonly retries: number;
  readonly error: string | null;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly finished_at: string | null;
}

export interface CheckDetail {
  readonly passed: boolean;
  readonly count: number;
  readonly details: readonly string[];
}

export interface DwellCheckDetail {
  readonly passed: boolean;
  readonly negative_count: number;
  readonly over_1000ms_count: number;
  readonly details: readonly string[];
}

export interface MissingKeyupsDetail {
  readonly passed: boolean;
  readonly total_events: number;
  readonly missing_count: number;
  readonly missing_share: number;
  readonly details: readonly string[];
}

export interface DataChecksResult {
  readonly seq_gaps: CheckDetail;
  readonly dwell_anomalies: DwellCheckDetail;
  readonly short_blocks: CheckDetail;
  readonly missing_keyups: MissingKeyupsDetail;
  readonly in_progress_sessions: CheckDetail;
}

export interface SessionTrendEntry {
  readonly session_id: string;
  readonly phase: string;
  readonly day_index: number;
  readonly started_at: string;
  readonly wpm: number | null;
  readonly accuracy: number | null;
  readonly per_set_error_rate: Record<string, number | null>;
  readonly per_set_attempts: Record<string, number>;
  readonly per_set_errors: Record<string, number>;
}

export interface ChecksResponse {
  readonly participant_id: string;
  readonly alias: string;
  readonly status: string;
  readonly passed: boolean;
  readonly checks: DataChecksResult;
  readonly trend: readonly SessionTrendEntry[];
}

export interface HealthResponse {
  readonly status: string;
  readonly database: string;
  readonly worker: {
    readonly status: "ok" | "stale" | "missing";
    readonly heartbeat_age_s: number | null;
  };
}

async function requestJson<T>(
  url: string,
  options: RequestInit = {},
  fetchImpl: typeof fetch = fetch,
): Promise<T> {
  const res = await fetchImpl(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export async function fetchHealth(fetchImpl: typeof fetch = fetch): Promise<HealthResponse> {
  return requestJson<HealthResponse>(apiPath("/health"), {}, fetchImpl);
}

export async function fetchParticipants(
  fetchImpl: typeof fetch = fetch,
): Promise<readonly ParticipantResponse[]> {
  return requestJson<readonly ParticipantResponse[]>(apiPath("/participants"), {}, fetchImpl);
}

export async function createParticipant(
  alias: string,
  isBuilder: boolean,
  fetchImpl: typeof fetch = fetch,
  keyboardLabel?: string,
): Promise<ParticipantResponse> {
  const trimmedLabel = keyboardLabel?.trim();
  const payload = trimmedLabel
    ? { alias, is_builder: isBuilder, keyboard_label: trimmedLabel }
    : { alias, is_builder: isBuilder };
  return requestJson<ParticipantResponse>(
    apiPath("/participants"),
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    fetchImpl,
  );
}

export async function recordParticipantConsent(
  participantId: string,
  keyboardLabel?: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ParticipantResponse> {
  const trimmedLabel = keyboardLabel?.trim();
  const body = trimmedLabel ? { keyboard_label: trimmedLabel } : {};
  return requestJson<ParticipantResponse>(
    apiPath(`/participants/${encodeURIComponent(participantId)}/consent`),
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    fetchImpl,
  );
}

export async function startOrResumeSession(
  participantId: string,
  options: { phase?: string; client_info?: Record<string, unknown> } = {},
  fetchImpl: typeof fetch = fetch,
): Promise<SessionPlan> {
  return requestJson<SessionPlan>(
    apiPath(`/participants/${encodeURIComponent(participantId)}/sessions`),
    {
      method: "POST",
      body: JSON.stringify(options),
    },
    fetchImpl,
  );
}

export async function fetchSessionPlan(
  sessionId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SessionPlan> {
  return requestJson<SessionPlan>(
    apiPath(`/sessions/${encodeURIComponent(sessionId)}`),
    {},
    fetchImpl,
  );
}

export async function startBlock(
  blockId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<BlockResponse> {
  return requestJson<BlockResponse>(
    apiPath(`/blocks/${encodeURIComponent(blockId)}/start`),
    { method: "POST" },
    fetchImpl,
  );
}

export async function completeBlock(
  blockId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<BlockResponse> {
  return requestJson<BlockResponse>(
    apiPath(`/blocks/${encodeURIComponent(blockId)}/complete`),
    { method: "POST" },
    fetchImpl,
  );
}

export async function completeSession(
  sessionId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SessionSummary> {
  return requestJson<SessionSummary>(
    apiPath(`/sessions/${encodeURIComponent(sessionId)}/complete`),
    { method: "POST" },
    fetchImpl,
  );
}

export async function assignParticipant(
  participantId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AssignmentResponse> {
  return requestJson<AssignmentResponse>(
    apiPath(`/admin/participants/${encodeURIComponent(participantId)}/assign`),
    { method: "POST" },
    fetchImpl,
  );
}

export async function fetchPoolStatus(
  participantId?: string,
  fetchImpl: typeof fetch = fetch,
): Promise<readonly PoolResponse[]> {
  const query = participantId ? `?participant_id=${encodeURIComponent(participantId)}` : "";
  return requestJson<readonly PoolResponse[]>(apiPath(`/admin/pool${query}`), {}, fetchImpl);
}

export async function replenishPool(
  participantId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<readonly JobResponse[]> {
  return requestJson<readonly JobResponse[]>(
    apiPath("/admin/pool/replenish"),
    {
      method: "POST",
      body: JSON.stringify({ participant_id: participantId }),
    },
    fetchImpl,
  );
}

export async function fetchJobs(
  params?: { participant_id?: string; status?: string; limit?: number },
  fetchImpl: typeof fetch = fetch,
): Promise<readonly JobResponse[]> {
  const search = new URLSearchParams();
  if (params?.participant_id) search.set("participant_id", params.participant_id);
  if (params?.status) search.set("status", params.status);
  if (params?.limit) search.set("limit", String(params.limit));
  const query = search.toString() ? `?${search.toString()}` : "";
  return requestJson<readonly JobResponse[]>(apiPath(`/admin/jobs${query}`), {}, fetchImpl);
}

export async function createJob(
  payload: { participant_id: string; arm?: string; requested?: number },
  fetchImpl: typeof fetch = fetch,
): Promise<readonly JobResponse[]> {
  return requestJson<readonly JobResponse[]>(
    apiPath("/admin/jobs"),
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    fetchImpl,
  );
}

export async function fetchChecks(
  participantId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ChecksResponse> {
  return requestJson<ChecksResponse>(
    apiPath(`/admin/checks/${encodeURIComponent(participantId)}`),
    {},
    fetchImpl,
  );
}
