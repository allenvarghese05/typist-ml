import { useEffect, useState } from "react";
import {
  fetchParticipantResults,
  fetchSessionMatrix,
  type ParticipantResults,
} from "../../api/analysis";
import { fetchParticipants, type ParticipantResponse } from "../../api/client";
import { IntervalPlot } from "../dashboard/IntervalPlot";

export interface DebriefPageProps {
  readonly initialParticipantId?: string;
  readonly fetchImpl?: typeof fetch;
}

export interface ArmDisplayMeta {
  readonly name: string;
  readonly badge: string;
  readonly description: string;
  readonly badgeClass: string;
}

export const ARM_METADATA: Record<string, ArmDisplayMeta> = {
  control: {
    name: "Control (held-out)",
    badge: "Held-out Comparison",
    description:
      "Zero targeted drills during practice; measures natural improvement from typing volume alone.",
    badgeClass: "bg-[#F3F2EE] text-[#4A4945] border-[#E4E2DC]",
  },
  heuristic: {
    name: "Dictionary Heuristic",
    badge: "Word-list Frequency",
    description:
      "Practice sentences composed of standard dictionary words containing target bigrams.",
    badgeClass: "bg-[#EBF3FA] text-[#1F5E8B] border-[#CEE2F4]",
  },
  markov: {
    name: "Markov Chain",
    badge: "Statistical N-gram",
    description: "Synthetic pseudo-words generated via character-level transition distributions.",
    badgeClass: "bg-[#EDF3EC] text-[#2B5930] border-[#D7E6D5]",
  },
  llm: {
    name: "On-device 1B LLM",
    badge: "Local Generative LM",
    description: "Natural sentences synthesized locally on-device via quantized language model.",
    badgeClass: "bg-[#FBF3DB] text-[#8A5A00] border-[#EFE0B4]",
  },
};

function formatPercent(value: number | null, decimals = 1): string {
  if (value === null) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

function formatRate(value: number | null): string {
  if (value === null) return "—";
  return value > 0 ? `+${(value * 100).toFixed(2)}%` : `${(value * 100).toFixed(2)}%`;
}

function formatMs(value: number | null): string {
  if (value === null) return "—";
  return value > 0 ? `+${value.toFixed(1)} ms` : `${value.toFixed(1)} ms`;
}

interface WeakBigramNudge {
  readonly bigram: string;
  readonly setLabel: string;
  readonly arm: string;
  readonly errorRate: number;
  readonly medianIkiMs: number | null;
}

export function DebriefPage({
  initialParticipantId,
  fetchImpl = fetch,
}: DebriefPageProps): React.JSX.Element {
  const [participants, setParticipants] = useState<readonly ParticipantResponse[]>([]);
  const [loadingParticipants, setLoadingParticipants] = useState(true);
  const [selectedId, setSelectedId] = useState<string>(initialParticipantId ?? "");
  const [revealed, setRevealed] = useState(true);

  const [resultsState, setResultsState] = useState<{
    readonly status: "loading" | "ok" | "not-done" | "not-found" | "error";
    readonly results: ParticipantResults | null;
    readonly message?: string;
  }>({ status: "loading", results: null });

  const [nudges, setNudges] = useState<readonly WeakBigramNudge[]>([]);

  // 1. Fetch participants on mount
  useEffect(() => {
    let cancelled = false;
    setLoadingParticipants(true);
    fetchParticipants(fetchImpl)
      .then((parts) => {
        if (cancelled) return;
        setParticipants(parts);
        setLoadingParticipants(false);

        // Determine initial participant if none explicitly chosen
        if (!initialParticipantId && parts.length > 0) {
          const firstDone = parts.find((p) => p.status === "done");
          const defaultPid = firstDone ? firstDone.id : parts[0]?.id;
          if (defaultPid) {
            setSelectedId(defaultPid);
            window.location.hash = `#/results/${encodeURIComponent(defaultPid)}`;
          }
        }
      })
      .catch(() => {
        if (cancelled) return;
        setLoadingParticipants(false);
      });

    return () => {
      cancelled = true;
    };
  }, [fetchImpl, initialParticipantId]);

  // Sync with prop changes
  useEffect(() => {
    if (initialParticipantId) {
      setSelectedId(initialParticipantId);
    }
  }, [initialParticipantId]);

  const handleSelectParticipant = (pid: string) => {
    setSelectedId(pid);
    window.location.hash = `#/results/${encodeURIComponent(pid)}`;
  };

  // 2. Fetch analysis results whenever selectedId changes
  useEffect(() => {
    if (!selectedId) {
      setResultsState({ status: "not-found", results: null });
      setNudges([]);
      return;
    }

    let cancelled = false;
    setResultsState({ status: "loading", results: null });
    setNudges([]);

    fetchParticipantResults(selectedId, fetchImpl).then((res) => {
      if (cancelled) return;
      if (res.status === "ok") {
        setResultsState({ status: "ok", results: res.results });

        // Fetch retest session matrices to compute diagnostic nudges (D12)
        const retestSessionIds = res.results.analyzed_retest_session_ids;
        if (retestSessionIds.length > 0) {
          Promise.all(retestSessionIds.map((sid) => fetchSessionMatrix(sid, fetchImpl)))
            .then((matrixResults) => {
              if (cancelled) return;
              const completedMatrices = matrixResults
                .filter((mr) => mr.status === "ok")
                .map(
                  (mr) =>
                    (
                      mr as {
                        status: "ok";
                        matrix: {
                          cells: readonly {
                            bigram: string;
                            attempts: number;
                            errors: number;
                            error_rate: number | null;
                            iki_median_ms: number | null;
                          }[];
                        };
                      }
                    ).matrix,
                );

              const bigramStats = new Map<
                string,
                { attempts: number; errors: number; ikiValues: number[] }
              >();
              for (const m of completedMatrices) {
                for (const cell of m.cells) {
                  const existing = bigramStats.get(cell.bigram) ?? {
                    attempts: 0,
                    errors: 0,
                    ikiValues: [],
                  };
                  existing.attempts += cell.attempts;
                  existing.errors += cell.errors;
                  if (cell.iki_median_ms !== null) existing.ikiValues.push(cell.iki_median_ms);
                  bigramStats.set(cell.bigram, existing);
                }
              }

              const foundNudges: WeakBigramNudge[] = [];
              for (const set of res.results.sets) {
                for (const bg of set.retained_bigrams) {
                  const stat = bigramStats.get(bg);
                  if (stat && stat.attempts > 0) {
                    const errRate = stat.errors / stat.attempts;
                    const medIki = stat.ikiValues.length > 0 ? (stat.ikiValues[0] ?? null) : null;
                    if (errRate > 0.05 || (medIki !== null && medIki > 250)) {
                      foundNudges.push({
                        bigram: bg,
                        setLabel: set.set_label,
                        arm: set.arm,
                        errorRate: errRate,
                        medianIkiMs: medIki,
                      });
                    }
                  }
                }
              }
              setNudges(foundNudges);
            })
            .catch(() => {
              // Graceful fallback: ignore diagnostic fetch error
            });
        }
      } else if (res.status === "not-done") {
        setResultsState({ status: "not-done", results: null, message: res.message });
      } else if (res.status === "not-found") {
        setResultsState({ status: "not-found", results: null });
      } else {
        setResultsState({ status: "error", results: null, message: res.message });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [selectedId, fetchImpl]);

  if (loadingParticipants) {
    return (
      <div className="p-8 max-w-6xl mx-auto text-center text-gray-500 animate-pulse">
        Loading debrief participants...
      </div>
    );
  }

  const currentParticipant = participants.find((p) => p.id === selectedId);

  return (
    <div className="px-6 py-8 max-w-6xl mx-auto space-y-6" data-testid="debrief-page">
      {/* Top Header & Participant Dropdown */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-[#EAEAEA] pb-5">
        <div>
          <h1 className="text-2xl font-semibold text-[#111111]">Study Debrief</h1>
          <p className="text-xs text-[#666560] mt-1">
            Participant debrief, experimental unblinding, and targeting outcomes (§11.3).
          </p>
        </div>

        {participants.length > 0 ? (
          <div className="flex items-center gap-3">
            <label
              htmlFor="debrief-participant-select"
              className="text-xs font-medium text-[#666560] shrink-0"
            >
              Participant:
            </label>
            <select
              id="debrief-participant-select"
              aria-label="Participant selector"
              value={selectedId}
              onChange={(e) => handleSelectParticipant(e.target.value)}
              className="text-xs border border-[#D9D7D0] rounded-lg px-3 py-1.5 bg-white text-[#111111] focus:outline-none focus:border-[#111111] font-mono"
            >
              {participants.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.alias} ({p.status}){p.is_builder ? " [Builder]" : ""}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="text-xs text-[#666560]">No participants enrolled.</div>
        )}
      </div>

      {/* Participant Identity Banner */}
      {currentParticipant && (
        <div className="typist-card p-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="text-sm font-semibold text-[#111111]">{currentParticipant.alias}</div>
            <span
              className={`inline-block px-2 py-0.5 rounded-md border text-[11px] uppercase font-medium ${
                currentParticipant.status === "done"
                  ? "bg-[#EDF3EC] text-[#2B5930] border-[#D7E6D5]"
                  : "bg-[#FBF3DB] text-[#8A5A00] border-[#EFE0B4]"
              }`}
            >
              Status: {currentParticipant.status}
            </span>
            <span
              className={`inline-block px-2 py-0.5 rounded-md border text-[11px] font-medium ${
                currentParticipant.is_builder
                  ? "bg-[#F3F2EE] text-[#4A4945] border-[#E4E2DC]"
                  : "bg-[#EBF3FA] text-[#1F5E8B] border-[#CEE2F4]"
              }`}
            >
              {currentParticipant.is_builder ? "Builder (Unblinded)" : "Peer (Blinded)"}
            </span>
          </div>
          <div className="text-xs text-[#8A8883] font-mono">ID: {currentParticipant.id}</div>
        </div>
      )}

      {/* Main Content Area: Locked vs. Revealed */}
      {resultsState.status === "loading" && (
        <div className="p-8 text-center text-[#666560]">Loading debrief analysis...</div>
      )}

      {resultsState.status === "not-done" && (
        <div className="typist-card p-8 space-y-5" data-testid="debrief-locked">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-[#FBF3DB] border border-[#EFE0B4] text-[#8A5A00] flex items-center justify-center shrink-0">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
                <rect
                  x="3.5"
                  y="8"
                  width="11"
                  height="7.5"
                  rx="2"
                  stroke="currentColor"
                  strokeWidth="1.5"
                />
                <path
                  d="M6 8V5.5C6 3.84315 7.34315 2.5 9 2.5C10.6569 2.5 12 3.84315 12 5.5V8"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-[#111111]">
                Study Debrief Locked (Experimental Blinding Active)
              </h2>
              <p className="text-sm text-[#666560] mt-1">
                To preserve scientific validity (D18), arm mappings and targeted drill outcomes
                remain strictly blinded until all post-practice retest sessions have concluded.
              </p>
            </div>
          </div>

          <div className="p-4 bg-[#FBF3DB] rounded-lg border border-[#EFE0B4] text-xs text-[#8A5A00] space-y-1">
            <div className="font-semibold">
              Current Phase: {currentParticipant?.status ?? "in progress"}
            </div>
            <div>{resultsState.message ?? "Retest sessions have not yet concluded."}</div>
            <div className="text-[#666560] mt-2">
              Check back here after completing Retest Day 2. Your arm assignments (Block 1–4 to
              generators) and detailed diagnostic improvements will unlock immediately.
            </div>
          </div>
        </div>
      )}

      {resultsState.status === "not-found" && (
        <div className="p-6 bg-red-50 border border-red-200 rounded text-red-800 text-sm">
          Participant results not found.
        </div>
      )}

      {resultsState.status === "error" && (
        <div className="p-6 bg-red-50 border border-red-200 rounded text-red-800 text-sm">
          Error loading debrief: {resultsState.message ?? "Unknown error"}
        </div>
      )}

      {resultsState.status === "ok" && resultsState.results && (
        <div className="space-y-8" data-testid="debrief-revealed">
          {/* Narrative Overview Card */}
          <div className="typist-card p-6 space-y-4">
            <h2 className="text-lg font-semibold tracking-tight text-[#111111]">
              Study Debrief &amp; Progression
            </h2>
            <p className="text-xs text-[#666560] leading-relaxed">
              Welcome to your debrief! In the baseline phase, your keystrokes were analyzed to
              identify your slowest and most error-prone bigrams. These were dealt in snake order
              into balanced sets (A, B, C, D) and trained over 10 practice days using 4 distinct
              methods disguised as Blocks 1 to 4. Below is your overall performance change between
              baseline and post-practice retest.
            </p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-2">
              <div className="p-3 typist-inset">
                <div className="text-[11px] text-[#666560] font-medium">Baseline WPM</div>
                <div className="text-xl font-semibold text-[#111111] mt-1 font-mono tabular-nums">
                  {resultsState.results.baseline_wpm?.toFixed(1) ?? "—"}
                </div>
              </div>
              <div className="p-3 typist-inset">
                <div className="text-[11px] text-[#666560] font-medium">Retest WPM</div>
                <div className="text-xl font-semibold text-[#111111] mt-1 font-mono tabular-nums">
                  {resultsState.results.retest_wpm?.toFixed(1) ?? "—"}
                </div>
              </div>
              <div className="p-3 typist-inset">
                <div className="text-[11px] text-[#666560] font-medium">Baseline Accuracy</div>
                <div className="text-xl font-semibold text-[#111111] mt-1 font-mono tabular-nums">
                  {formatPercent(resultsState.results.baseline_accuracy)}
                </div>
              </div>
              <div className="p-3 typist-inset">
                <div className="text-[11px] text-[#666560] font-medium">Retest Accuracy</div>
                <div className="text-xl font-semibold text-[#111111] mt-1 font-mono tabular-nums">
                  {formatPercent(resultsState.results.retest_accuracy)}
                </div>
              </div>
            </div>
          </div>

          {/* The Arm Reveal Section */}
          <div className="typist-card p-6 space-y-5" data-testid="arm-reveal-card">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#EAEAEA] pb-4">
              <div>
                <h3 className="text-base font-semibold tracking-tight text-[#111111]">
                  The Arm Reveal: Generator Mapping (§3.2, §11.3)
                </h3>
                <p className="text-xs text-[#666560] mt-1">
                  Unmasking the experimental drill generators assigned to each block during your 10
                  practice sessions.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setRevealed(!revealed)}
                className="typist-btn-secondary shrink-0"
                data-testid="toggle-reveal-btn"
              >
                {revealed ? "Mask Arm Identities" : "Reveal Arm Identities"}
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {resultsState.results.sets.map((set, idx) => {
                const meta = ARM_METADATA[set.arm] ?? {
                  name: set.arm,
                  badge: set.arm,
                  description: "Experimental generator.",
                  badgeClass: "bg-[#F3F2EE] text-[#666560] border-[#EAEAEA]",
                };
                return (
                  <div
                    key={set.set_label}
                    className="p-4 typist-inset flex flex-col justify-between space-y-3"
                    data-testid={`arm-card-${set.set_label}`}
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold font-mono text-[#111111] uppercase">
                          Set {set.set_label} (Block {idx + 1})
                        </span>
                        {revealed && (
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase border ${meta.badgeClass}`}
                          >
                            {meta.badge}
                          </span>
                        )}
                      </div>
                      <div className="text-sm font-semibold text-[#111111]">
                        {revealed ? meta.name : `Masked (Block ${idx + 1})`}
                      </div>
                      <p className="text-xs text-[#666560] mt-1 leading-relaxed">
                        {revealed
                          ? meta.description
                          : "Identity hidden during study to ensure single-blind validity."}
                      </p>
                    </div>

                    <div className="text-[11px] text-[#666560] font-mono border-t border-[#EAEAEA] pt-2">
                      <span>{set.bigrams.length} assigned bigram(s)</span>
                      {set.dropped_bigrams.length > 0 && (
                        <span className="text-[#8A5A00] block text-[10px]">
                          ({set.dropped_bigrams.length} dropped from confirmatory test)
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Weak Bigrams by Set Section */}
          <div className="typist-card p-6 space-y-4">
            <h3 className="text-base font-semibold tracking-tight text-[#111111]">
              Assigned Weak Bigrams by Set
            </h3>
            <p className="text-xs text-[#666560]">
              Bigrams identified from baseline latency and dealt into matched sets in snake order
              (D04).
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {resultsState.results.sets.map((set) => (
                <div key={set.set_label} className="p-4 typist-inset">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-[#111111]">
                      Set {set.set_label} ({revealed ? set.arm : "Masked"})
                    </span>
                    <span className="text-xs text-[#666560] font-mono">
                      {set.retained_bigrams.length} retained
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {set.retained_bigrams.map((bg) => (
                      <span
                        key={bg}
                        className="px-2 py-0.5 bg-white border border-[#EAEAEA] rounded text-xs font-mono font-medium text-[#111111]"
                      >
                        "{bg}"
                      </span>
                    ))}
                    {set.dropped_bigrams.map((bg) => (
                      <span
                        key={bg}
                        className="px-2 py-0.5 bg-[#FBF3DB] border border-[#EFE0B4] rounded text-xs font-mono text-[#8A5A00] line-through"
                        title="Dropped: fewer than 20 retest observations (D23c)"
                      >
                        "{bg}"
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Primary Confirmatory Outcomes: Error Rate */}
          <div className="typist-card p-6 space-y-5">
            <div>
              <h3 className="text-base font-semibold tracking-tight text-[#111111]">
                Primary Confirmatory Outcome: Error Rate Targeting Effect E(s)
              </h3>
              <p className="text-xs text-[#666560] mt-1">
                E(s) = d(s) - d(control) under Jeffreys Beta posterior sampling. Negative targeting
                effect denotes error reduction beyond normal practice.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-[#111111]">
                <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
                  <tr>
                    <th className="py-2.5 px-3">Set</th>
                    <th className="py-2.5 px-3">Arm</th>
                    <th className="py-2.5 px-3">Baseline Error</th>
                    <th className="py-2.5 px-3">Retest Error</th>
                    <th className="py-2.5 px-3">d(s) Change</th>
                    <th className="py-2.5 px-3">Targeting Effect E(s)</th>
                    <th className="py-2.5 px-3">95% Credible Interval</th>
                    <th className="py-2.5 px-3">P(E &lt; 0)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EAEAEA]">
                  {resultsState.results.sets.map((set) => {
                    const isControl = set.arm === "control";
                    return (
                      <tr key={set.set_label} className={isControl ? "bg-[#FBFBFA]" : undefined}>
                        <td className="py-2 px-3 font-semibold text-[#111111]">{set.set_label}</td>
                        <td className="py-2 px-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                              isControl
                                ? "bg-[#F3F2EE] text-[#666560]"
                                : "bg-[#EBF3FA] text-[#1D5A8A]"
                            }`}
                          >
                            {revealed ? (isControl ? "Control Set" : set.arm) : `Block (Masked)`}
                          </span>
                        </td>
                        <td className="py-2 px-3 font-mono tabular-nums">
                          {formatPercent(set.baseline_error_rate)}
                        </td>
                        <td className="py-2 px-3 font-mono tabular-nums">
                          {formatPercent(set.retest_error_rate)}
                        </td>
                        <td className="py-2 px-3 font-mono tabular-nums">
                          {formatRate(set.error_rate_change)}
                        </td>
                        <td className="py-2 px-3 font-mono font-semibold tabular-nums">
                          {isControl ? "—" : formatRate(set.targeting_effect)}
                        </td>
                        <td className="py-2 px-3 font-mono text-[#666560] tabular-nums">
                          {isControl ||
                          set.posterior_effect_ci_lower === null ||
                          set.posterior_effect_ci_upper === null
                            ? "—"
                            : `[${(set.posterior_effect_ci_lower * 100).toFixed(2)}%, ${(set.posterior_effect_ci_upper * 100).toFixed(2)}%]`}
                        </td>
                        <td className="py-2 px-3 font-mono font-semibold tabular-nums">
                          {isControl ? "—" : formatPercent(set.share_below_zero)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Error Rate Whisker Forest Plot */}
            <div className="pt-3 border-t border-[#EAEAEA] space-y-1">
              <h4 className="text-xs font-medium text-[#666560] mb-2">
                Targeting Effect Whisker Plot (Error Rate)
              </h4>
              {resultsState.results.sets
                .filter((s) => s.arm !== "control")
                .map((s) => (
                  <IntervalPlot
                    key={s.set_label}
                    label={`Set ${s.set_label} (${revealed ? s.arm : "Masked"})`}
                    sublabel="95% Credible Interval"
                    estimate={s.posterior_effect_median}
                    lower={s.posterior_effect_ci_lower}
                    upper={s.posterior_effect_ci_upper}
                    unit=""
                    minRange={-0.12}
                    maxRange={0.12}
                    higherIsBetter={false}
                  />
                ))}
            </div>
          </div>

          {/* Key Secondary Confirmatory Outcomes: Timing */}
          <div className="typist-card p-6 space-y-5">
            <div>
              <h3 className="text-base font-semibold tracking-tight text-[#111111]">
                Key Secondary Outcome: Median IKI Targeting Effect F(s)
              </h3>
              <p className="text-xs text-[#666560] mt-1">
                F(s) = c(s) - c(control) on clean keystroke intervals (ms) with 95% bootstrap
                confidence intervals.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-[#111111]">
                <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
                  <tr>
                    <th className="py-2.5 px-3">Set</th>
                    <th className="py-2.5 px-3">Arm</th>
                    <th className="py-2.5 px-3">Baseline Median IKI</th>
                    <th className="py-2.5 px-3">Retest Median IKI</th>
                    <th className="py-2.5 px-3">c(s) Change</th>
                    <th className="py-2.5 px-3">Targeting Effect F(s)</th>
                    <th className="py-2.5 px-3">95% Bootstrap CI</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EAEAEA]">
                  {resultsState.results.sets.map((set) => {
                    const isControl = set.arm === "control";
                    return (
                      <tr key={set.set_label} className={isControl ? "bg-[#FBFBFA]" : undefined}>
                        <td className="py-2 px-3 font-semibold text-[#111111]">{set.set_label}</td>
                        <td className="py-2 px-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                              isControl
                                ? "bg-[#F3F2EE] text-[#666560]"
                                : "bg-[#EBF3FA] text-[#1D5A8A]"
                            }`}
                          >
                            {revealed ? (isControl ? "Control Set" : set.arm) : `Block (Masked)`}
                          </span>
                        </td>
                        <td className="py-2 px-3 font-mono tabular-nums">
                          {set.baseline_iki_median_ms !== null
                            ? `${set.baseline_iki_median_ms.toFixed(1)} ms`
                            : "—"}
                        </td>
                        <td className="py-2 px-3 font-mono tabular-nums">
                          {set.retest_iki_median_ms !== null
                            ? `${set.retest_iki_median_ms.toFixed(1)} ms`
                            : "—"}
                        </td>
                        <td className="py-2 px-3 font-mono tabular-nums">
                          {formatMs(set.iki_change_ms)}
                        </td>
                        <td className="py-2 px-3 font-mono font-semibold tabular-nums">
                          {isControl ? "—" : formatMs(set.iki_targeting_effect_ms)}
                        </td>
                        <td className="py-2 px-3 font-mono text-[#666560] tabular-nums">
                          {isControl ||
                          set.iki_bootstrap_ci_lower_ms === null ||
                          set.iki_bootstrap_ci_upper_ms === null
                            ? "—"
                            : `[${set.iki_bootstrap_ci_lower_ms.toFixed(1)}, ${set.iki_bootstrap_ci_upper_ms.toFixed(1)}] ms`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* IKI Whisker Forest Plot */}
            <div className="pt-3 border-t border-[#EAEAEA] space-y-1">
              <h4 className="text-xs font-medium text-[#666560] mb-2">
                Targeting Effect Whisker Plot (Median IKI)
              </h4>
              {resultsState.results.sets
                .filter((s) => s.arm !== "control")
                .map((s) => (
                  <IntervalPlot
                    key={s.set_label}
                    label={`Set ${s.set_label} (${revealed ? s.arm : "Masked"})`}
                    sublabel="95% Bootstrap CI"
                    estimate={s.iki_bootstrap_median_ms}
                    lower={s.iki_bootstrap_ci_lower_ms}
                    upper={s.iki_bootstrap_ci_upper_ms}
                    unit=" ms"
                    minRange={-60}
                    maxRange={60}
                    higherIsBetter={false}
                  />
                ))}
            </div>
          </div>

          {/* Targeting Diagnostic & Next Steps (D12) */}
          <div className="typist-card p-6 space-y-4" data-testid="diagnostic-nudges-card">
            <div>
              <h3 className="text-base font-semibold tracking-tight text-[#111111]">
                Targeting Diagnostic &amp; Next Steps (D12)
              </h3>
              <p className="text-xs text-[#666560] mt-1">
                Post-retest coaching feedback on bigrams that remained slow or error-prone at
                retest.
              </p>
            </div>

            {nudges.length > 0 ? (
              <div className="space-y-3">
                <p className="text-xs text-[#666560]">
                  The following assigned bigrams exhibited residual elevated error rates (&gt;5%) or
                  latency at retest:
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {nudges.map((n) => (
                    <div
                      key={n.bigram}
                      className="p-3 bg-[#FBF3DB] border border-[#EFE0B4] rounded-md text-xs space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-semibold text-[#111111] text-sm">
                          "{n.bigram}"
                        </span>
                        <span className="text-[#8A5A00] font-semibold font-mono tabular-nums">
                          {formatPercent(n.errorRate)} error rate
                          {n.medianIkiMs !== null ? ` · ${n.medianIkiMs.toFixed(0)}ms` : ""}
                        </span>
                      </div>
                      <p className="text-[#666560]">
                        Assigned to Set {n.setLabel} ({revealed ? n.arm : "Masked"}). Continued
                        focus recommended on finger transition cadence and conscious slowing.
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="p-4 bg-[#EDF3EC] border border-[#D4E4D2] rounded-md text-xs text-[#2B6E3F]">
                <span className="font-semibold">Excellent typing precision!</span> All assigned weak
                bigrams achieved high accuracy (&lt;5% error rate) during post-practice retest.
              </div>
            )}
          </div>

          {/* Pre-registered Exclusions Card */}
          <div className="typist-card p-6 space-y-4">
            <h3 className="text-base font-semibold tracking-tight text-[#111111]">
              Pre-registered Exclusions Report (D20, D23)
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs text-[#666560]">
              <div>
                <h4 className="font-medium text-[#666560] mb-2">Excluded Sessions</h4>
                {resultsState.results.exclusions?.excluded_sessions &&
                resultsState.results.exclusions.excluded_sessions.length > 0 ? (
                  <ul className="divide-y divide-[#EAEAEA]">
                    {resultsState.results.exclusions.excluded_sessions.map((exc) => (
                      <li key={exc.session_id} className="py-1.5 flex justify-between">
                        <span className="font-mono">{exc.session_id.slice(0, 8)}...</span>
                        <span>
                          Day {exc.day_index} ({exc.phase}) —{" "}
                          <span className="font-medium text-[#8A5A00]">{exc.reason}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[#666560]">No sessions excluded.</p>
                )}
              </div>

              <div>
                <h4 className="font-medium text-[#666560] mb-2">
                  Dropped Bigrams (&lt;20 Retest Attempts)
                </h4>
                {resultsState.results.exclusions?.dropped_bigrams &&
                resultsState.results.exclusions.dropped_bigrams.length > 0 ? (
                  <ul className="divide-y divide-[#EAEAEA]">
                    {resultsState.results.exclusions.dropped_bigrams.map((drp) => (
                      <li key={drp.bigram} className="py-1.5 flex justify-between">
                        <span className="font-mono font-semibold text-[#111111]">
                          "{drp.bigram}"
                        </span>
                        <span>
                          Set {drp.set_label} ({revealed ? drp.arm : "Masked"}) —{" "}
                          <span className="text-[#8A5A00] font-medium">
                            {drp.retest_attempts} attempts
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[#666560]">
                    No bigrams dropped (all had ≥20 retest attempts).
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
