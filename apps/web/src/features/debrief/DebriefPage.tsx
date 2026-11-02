import { useEffect, useState } from "react";
import {
  type BigramMatrix,
  fetchOverview,
  fetchParticipantResults,
  fetchParticipantTrend,
  fetchSessionMatrix,
  type Overview,
  type ParticipantResults,
  type SessionTrendEntry,
} from "../../api/analysis";
import {
  type ChecksResponse,
  fetchChecks,
  fetchParticipants,
  type ParticipantResponse,
} from "../../api/client";
import { IntervalPlot } from "../dashboard/IntervalPlot";
import {
  CaseStudyAbstractSection,
  classifyEvidence,
  ExperimentalDesignSection,
  GENERATOR_SPECS,
  LongitudinalTrajectorySection,
  type PerBigramComparison,
  PerBigramForensicsSection,
  SystemVerificationSection,
} from "./DebriefCaseStudySections";

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
  if (value === null) return "N/A";
  return `${(value * 100).toFixed(decimals)}%`;
}

function formatRate(value: number | null): string {
  if (value === null) return "N/A";
  return value > 0 ? `+${(value * 100).toFixed(2)}%` : `${(value * 100).toFixed(2)}%`;
}

function formatMs(value: number | null): string {
  if (value === null) return "N/A";
  return value > 0 ? `+${value.toFixed(1)} ms` : `${value.toFixed(1)} ms`;
}

interface PooledMatrixEntry {
  attempts: number;
  errors: number;
  weightedIkiSum: number;
  ikiWeight: number;
}

function poolMatrices(matrices: readonly BigramMatrix[]): Map<string, PooledMatrixEntry> {
  const map = new Map<string, PooledMatrixEntry>();
  for (const m of matrices) {
    for (const cell of m.cells) {
      const prev = map.get(cell.bigram) ?? {
        attempts: 0,
        errors: 0,
        weightedIkiSum: 0,
        ikiWeight: 0,
      };
      prev.attempts += cell.attempts;
      prev.errors += cell.errors;
      if (cell.iki_median_ms !== null) {
        const w = Math.max(1, cell.iki_n);
        prev.weightedIkiSum += cell.iki_median_ms * w;
        prev.ikiWeight += w;
      }
      map.set(cell.bigram, prev);
    }
  }
  return map;
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
  const [bigramRows, setBigramRows] = useState<readonly PerBigramComparison[]>([]);
  const [trend, setTrend] = useState<readonly SessionTrendEntry[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [checks, setChecks] = useState<ChecksResponse | null>(null);

  // 1. Fetch participants on mount
  useEffect(() => {
    let cancelled = false;
    setLoadingParticipants(true);
    fetchParticipants(fetchImpl)
      .then((parts) => {
        if (cancelled) return;
        setParticipants(parts);
        setLoadingParticipants(false);

        if (!initialParticipantId && parts.length > 0) {
          const firstNonBuilderDone = parts.find((p) => p.status === "done" && !p.is_builder);
          const firstDone = firstNonBuilderDone ?? parts.find((p) => p.status === "done");
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

  useEffect(() => {
    if (initialParticipantId) {
      setSelectedId(initialParticipantId);
    }
  }, [initialParticipantId]);

  const handleSelectParticipant = (pid: string) => {
    setSelectedId(pid);
    window.location.hash = `#/results/${encodeURIComponent(pid)}`;
  };

  // 2. Fetch analysis results + supplementary case-study telemetry whenever selectedId changes
  useEffect(() => {
    if (!selectedId) {
      setResultsState({ status: "not-found", results: null });
      setNudges([]);
      setBigramRows([]);
      setTrend([]);
      setOverview(null);
      setChecks(null);
      return;
    }

    let cancelled = false;
    setResultsState({ status: "loading", results: null });
    setNudges([]);
    setBigramRows([]);
    setTrend([]);
    setOverview(null);
    setChecks(null);

    fetchParticipantResults(selectedId, fetchImpl).then((res) => {
      if (cancelled) return;
      if (res.status === "ok") {
        const participantResults = res.results;
        setResultsState({ status: "ok", results: participantResults });

        // Supplementary 1: Session progression trend
        fetchParticipantTrend(selectedId, fetchImpl)
          .then((tr) => {
            if (!cancelled && tr.status === "ok" && Array.isArray(tr.trend)) {
              setTrend(tr.trend);
            }
          })
          .catch(() => {});

        // Supplementary 2: System overhead & generator fairness overview
        fetchOverview(fetchImpl)
          .then((ov) => {
            if (
              !cancelled &&
              ov.status === "ok" &&
              Array.isArray(ov.overview?.overhead) &&
              Array.isArray(ov.overview?.generation?.arms)
            ) {
              setOverview(ov.overview);
            }
          })
          .catch(() => {});

        // Supplementary 3: 5-gate SQLite integrity checks
        fetchChecks(selectedId, fetchImpl)
          .then((chk) => {
            if (!cancelled && chk && typeof chk.checks?.missing_keyups?.total_events === "number") {
              setChecks(chk);
            }
          })
          .catch(() => {});

        // Supplementary 4: Baseline + Retest session matrices for per-bigram forensics & D12 nudges
        const baseIds = participantResults.analyzed_baseline_session_ids;
        const retestIds = participantResults.analyzed_retest_session_ids;
        Promise.all([
          Promise.all(baseIds.map((sid) => fetchSessionMatrix(sid, fetchImpl))),
          Promise.all(retestIds.map((sid) => fetchSessionMatrix(sid, fetchImpl))),
        ])
          .then(([baseMatrixResults, retestMatrixResults]) => {
            if (cancelled) return;
            const baseMatrices = baseMatrixResults
              .filter((mr): mr is { status: "ok"; matrix: BigramMatrix } => mr.status === "ok")
              .map((mr) => mr.matrix);
            const retestMatrices = retestMatrixResults
              .filter((mr): mr is { status: "ok"; matrix: BigramMatrix } => mr.status === "ok")
              .map((mr) => mr.matrix);

            const basePool = poolMatrices(baseMatrices);
            const retestPool = poolMatrices(retestMatrices);

            const comparisons: PerBigramComparison[] = [];
            const foundNudges: WeakBigramNudge[] = [];

            for (const set of participantResults.sets) {
              for (const bg of set.bigrams) {
                const isDropped = set.dropped_bigrams.includes(bg);
                const bStat = basePool.get(bg);
                const rStat = retestPool.get(bg);

                const bAtt = bStat?.attempts ?? 0;
                const bErr = bStat?.errors ?? 0;
                const bRate = bAtt > 0 ? bErr / bAtt : null;
                const bIki =
                  bStat && bStat.ikiWeight > 0 ? bStat.weightedIkiSum / bStat.ikiWeight : null;

                const rAtt = rStat?.attempts ?? 0;
                const rErr = rStat?.errors ?? 0;
                const rRate = rAtt > 0 ? rErr / rAtt : null;
                const rIki =
                  rStat && rStat.ikiWeight > 0 ? rStat.weightedIkiSum / rStat.ikiWeight : null;

                if (bAtt > 0 || rAtt > 0) {
                  comparisons.push({
                    bigram: bg,
                    setLabel: set.set_label,
                    arm: set.arm,
                    dropped: isDropped,
                    baselineAttempts: bAtt,
                    baselineErrors: bErr,
                    baselineErrorRate: bRate,
                    baselineMedianIkiMs: bIki,
                    retestAttempts: rAtt,
                    retestErrors: rErr,
                    retestErrorRate: rRate,
                    retestMedianIkiMs: rIki,
                  });
                }

                if (!isDropped && rAtt > 0 && rRate !== null) {
                  if (rRate > 0.05 || (rIki !== null && rIki > 250)) {
                    foundNudges.push({
                      bigram: bg,
                      setLabel: set.set_label,
                      arm: set.arm,
                      errorRate: rRate,
                      medianIkiMs: rIki,
                    });
                  }
                }
              }
            }

            setBigramRows(comparisons);
            setNudges(foundNudges);
          })
          .catch(() => {});
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
      <div className="p-8 max-w-6xl mx-auto text-center text-[#666560]">
        Loading debrief participants...
      </div>
    );
  }

  const currentParticipant = participants.find((p) => p.id === selectedId);

  // Dynamic symmetric bounds for forest plots so large real effects never clip
  const activeResults = resultsState.results;
  const maxAbsErrBound = activeResults
    ? Math.max(
        0.12,
        ...activeResults.sets
          .filter((s) => s.arm !== "control")
          .flatMap((s) => [
            Math.abs(s.posterior_effect_ci_lower ?? 0),
            Math.abs(s.posterior_effect_ci_upper ?? 0),
            Math.abs(s.posterior_effect_median ?? 0),
          ])
          .map((v) => Math.ceil(v * 20) / 20 + 0.02),
      )
    : 0.12;

  const maxAbsIkiBound = activeResults
    ? Math.max(
        60,
        ...activeResults.sets
          .filter((s) => s.arm !== "control")
          .flatMap((s) => [
            Math.abs(s.iki_bootstrap_ci_lower_ms ?? 0),
            Math.abs(s.iki_bootstrap_ci_upper_ms ?? 0),
            Math.abs(s.iki_bootstrap_median_ms ?? 0),
          ])
          .map((v) => Math.ceil(v / 10) * 10 + 10),
      )
    : 60;

  const totalKeystrokeEvents =
    checks?.checks.missing_keyups.total_events ??
    (overview
      ? overview.overhead
          .filter((o) => o.participant_id === selectedId)
          .reduce((acc, r) => acc + r.events, 0) || null
      : null);

  const completedSessionCount =
    trend.length > 0
      ? trend.length
      : (overview?.participants.find((p) => p.id === selectedId)?.completed_sessions ?? null);

  return (
    <div className="px-6 py-8 max-w-6xl mx-auto space-y-6" data-testid="debrief-page">
      {/* Top Header & Participant Dropdown (strictly free of arm names while blinded) */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-[#EAEAEA] pb-5">
        <div>
          <h1 className="text-2xl font-semibold text-[#111111]">
            Study Debrief &amp; Empirical Case Study
          </h1>
          <p className="text-xs text-[#666560] mt-1">
            Within-participant longitudinal analysis, experimental unblinding, and confirmatory
            statistical inference (§11.3, §15).
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
              className="text-xs border border-[#D9D7D0] rounded-lg px-3 py-1.5 bg-white text-[#111111] focus:outline-none focus:border-[#111111]"
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
          <div className="flex flex-wrap items-center gap-2.5">
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
            {currentParticipant.keyboard_label && (
              <span className="inline-block px-2 py-0.5 rounded-md border border-[#E4E2DC] bg-[#F6F5F2] text-[11px] text-[#4A4945]">
                Keyboard: {currentParticipant.keyboard_label}
              </span>
            )}
          </div>
          <div className="text-xs text-[#8A8883]">
            Participant ID: <code>{currentParticipant.id}</code>
          </div>
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
              Return here after completing Retest Day 2. Block-to-generator mappings and full
              confirmatory statistical tables become available immediately upon completion.
            </div>
          </div>
        </div>
      )}

      {resultsState.status === "not-found" && (
        <div className="p-6 bg-[#FCEBEC] border border-[#F3C8CA] rounded text-[#9F2F2D] text-sm">
          Participant results not found.
        </div>
      )}

      {resultsState.status === "error" && (
        <div className="p-6 bg-[#FCEBEC] border border-[#F3C8CA] rounded text-[#9F2F2D] text-sm">
          Error loading debrief: {resultsState.message ?? "Unknown error"}
        </div>
      )}

      {resultsState.status === "ok" && resultsState.results && (
        <div className="space-y-8" data-testid="debrief-revealed">
          {/* Case Study Section Index Bar */}
          <nav
            aria-label="Case study sections"
            className="typist-card px-4 py-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-[#666560]"
          >
            <span className="font-semibold text-[#111111]">Case Study Index:</span>
            <a href="#cs-abstract" className="hover:text-[#111111]">
              §1 Verdict
            </a>
            <a href="#cs-methodology" className="hover:text-[#111111]">
              §2 Methodology
            </a>
            <a href="#cs-generators" className="hover:text-[#111111]">
              §3 Arm Unblinding
            </a>
            {trend.length > 0 && (
              <a href="#cs-trajectory" className="hover:text-[#111111]">
                §4 Trajectory
              </a>
            )}
            <a href="#cs-primary" className="hover:text-[#111111]">
              §5 Error Rate E(s)
            </a>
            <a href="#cs-secondary" className="hover:text-[#111111]">
              §6 Fluency F(s)
            </a>
            <a href="#cs-bigrams" className="hover:text-[#111111]">
              §7 Bigram Breakdown
            </a>
            <a href="#cs-exclusions" className="hover:text-[#111111]">
              §8 Audit &amp; Exclusions
            </a>
          </nav>

          {/* §1: Executive Case Study Abstract & Scorecard */}
          <CaseStudyAbstractSection
            results={resultsState.results}
            revealed={revealed}
            totalEvents={totalKeystrokeEvents}
            completedSessionsCount={completedSessionCount}
          />

          {/* §2: Experimental Design & Threats-to-Validity Matrix */}
          <ExperimentalDesignSection />

          {/* §3: The Arm Reveal & Generator Architecture */}
          <section
            id="cs-generators"
            className="typist-card p-6 space-y-5"
            data-testid="arm-reveal-card"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#EAEAEA] pb-4">
              <div>
                <h3 className="text-base font-semibold tracking-tight text-[#111111]">
                  §3 · The Arm Reveal: Generator Architecture &amp; Trade-offs (§3.2, §6, §11.3)
                </h3>
                <p className="text-xs text-[#666560] mt-1">
                  Unmasking the experimental drill synthesis engines assigned to each bigram set
                  during the 10-day practice intervention.
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
                const spec = GENERATOR_SPECS[set.arm];
                return (
                  <div
                    key={set.set_label}
                    className="p-4 typist-inset flex flex-col justify-between space-y-3"
                    data-testid={`arm-card-${set.set_label}`}
                  >
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-[#111111] uppercase">
                          <code>
                            Set {set.set_label} (Block {idx + 1})
                          </code>
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
                      <p className="text-xs text-[#666560] leading-relaxed">
                        {revealed
                          ? meta.description
                          : "Identity hidden during study to ensure single-blind validity."}
                      </p>

                      {revealed && spec && (
                        <div className="pt-2 border-t border-[#EAEAEA] space-y-1.5 text-[11px] text-[#4A4945]">
                          <div>
                            <span className="font-semibold text-[#111111]">Mechanism: </span>
                            {spec.mechanism}
                          </div>
                          <div>
                            <span className="font-semibold text-[#111111]">Constraint: </span>
                            {spec.lexicalConstraint}
                          </div>
                          <div>
                            <span className="font-semibold text-[#111111]">Compute: </span>
                            {spec.computeProfile}
                          </div>
                          <div>
                            <span className="font-semibold text-[#111111]">Design Role: </span>
                            {spec.hypothesisRole}
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="text-[11px] text-[#666560] border-t border-[#EAEAEA] pt-2">
                      <span>
                        <code>{set.bigrams.length}</code> assigned bigram(s):{" "}
                        <code>{set.bigrams.join(", ")}</code>
                      </span>
                      {set.dropped_bigrams.length > 0 && (
                        <span className="text-[#8A5A00] block text-[10px] mt-0.5">
                          ({set.dropped_bigrams.length} dropped from confirmatory test)
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* §4: Longitudinal 14-Session Learning Trajectory */}
          <LongitudinalTrajectorySection
            trend={trend}
            sets={resultsState.results.sets}
            revealed={revealed}
          />

          {/* §5: Primary Confirmatory Outcomes: Error Rate */}
          <section id="cs-primary" className="typist-card p-6 space-y-5">
            <div>
              <h3 className="text-base font-semibold tracking-tight text-[#111111]">
                Primary Confirmatory Outcome: Error Rate Targeting Effect E(s)
              </h3>
              <p className="text-xs text-[#666560] mt-1 leading-relaxed">
                Difference-in-Differences estimation under independent non-informative Jeffreys{" "}
                <code>Beta(1/2, 1/2)</code> conjugate posteriors (
                {resultsState.results.posterior_draws.toLocaleString()} Monte Carlo draws, seed{" "}
                <code>{resultsState.results.seed}</code>). Negative <code>E(s)</code> indicates
                causal error reduction exceeding general typing practice.
              </p>
            </div>

            {/* Mathematical Model Callout */}
            <div className="p-3.5 typist-inset grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-[#3D3C38]">
              <div>
                <div className="font-semibold text-[#111111]">1. Conjugate Cell Posterior</div>
                <div className="mt-1 text-[#666560]">
                  <code>p_(s,t) | (e, n) ~ Beta(e + 0.5, n - e + 0.5)</code>
                </div>
              </div>
              <div>
                <div className="font-semibold text-[#111111]">2. Within-Set Longitudinal Shift</div>
                <div className="mt-1 text-[#666560]">
                  <code>d(s) = p_(s,retest) - p_(s,baseline)</code>
                </div>
              </div>
              <div>
                <div className="font-semibold text-[#111111]">
                  3. Counterfactual Targeting Effect
                </div>
                <div className="mt-1 text-[#666560]">
                  <code>E(s) = d(s) - d(ref) · P_benefit = Pr(E(s) &lt; 0)</code>
                </div>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-[#111111]">
                <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
                  <tr>
                    <th className="py-2.5 px-3">Set</th>
                    <th className="py-2.5 px-3">Arm</th>
                    <th className="py-2.5 px-3">Baseline (e / n &amp; 95% CI)</th>
                    <th className="py-2.5 px-3">Retest (e / n &amp; 95% CI)</th>
                    <th className="py-2.5 px-3">d(s) Shift</th>
                    <th className="py-2.5 px-3">Effect E(s)</th>
                    <th className="py-2.5 px-3">95% Posterior CI</th>
                    <th className="py-2.5 px-3">P(E &lt; 0)</th>
                    <th className="py-2.5 px-3">Inference</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EAEAEA] tabular-nums">
                  {resultsState.results.sets.map((set) => {
                    const isControl = set.arm === "control";
                    const evidence = classifyEvidence(set.share_below_zero);
                    return (
                      <tr key={set.set_label} className={isControl ? "bg-[#FBFBFA]" : undefined}>
                        <td className="py-2.5 px-3 font-semibold text-[#111111]">
                          {set.set_label}
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                              isControl
                                ? "bg-[#F3F2EE] text-[#666560]"
                                : "bg-[#EBF3FA] text-[#1D5A8A]"
                            }`}
                          >
                            {revealed ? (isControl ? "Control Set" : set.arm) : "Block (Masked)"}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">
                            <code>
                              {formatPercent(set.baseline_error_rate)} ({set.baseline_errors}/
                              {set.baseline_attempts})
                            </code>
                          </div>
                          {set.baseline_beta_ci_lower !== null &&
                            set.baseline_beta_ci_upper !== null && (
                              <div className="text-[10px] text-[#666560]">
                                <code>
                                  [{(set.baseline_beta_ci_lower * 100).toFixed(1)}%,{" "}
                                  {(set.baseline_beta_ci_upper * 100).toFixed(1)}%]
                                </code>
                              </div>
                            )}
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">
                            <code>
                              {formatPercent(set.retest_error_rate)} ({set.retest_errors}/
                              {set.retest_attempts})
                            </code>
                          </div>
                          {set.retest_beta_ci_lower !== null &&
                            set.retest_beta_ci_upper !== null && (
                              <div className="text-[10px] text-[#666560]">
                                <code>
                                  [{(set.retest_beta_ci_lower * 100).toFixed(1)}%,{" "}
                                  {(set.retest_beta_ci_upper * 100).toFixed(1)}%]
                                </code>
                              </div>
                            )}
                        </td>
                        <td className="py-2.5 px-3">
                          <code>{formatRate(set.error_rate_change)}</code>
                        </td>
                        <td className="py-2.5 px-3 font-semibold">
                          <code>{isControl ? "Ref" : formatRate(set.targeting_effect)}</code>
                        </td>
                        <td className="py-2.5 px-3 text-[#666560]">
                          <code>
                            {isControl ||
                            set.posterior_effect_ci_lower === null ||
                            set.posterior_effect_ci_upper === null
                              ? "N/A"
                              : `[${(set.posterior_effect_ci_lower * 100).toFixed(2)}%, ${(set.posterior_effect_ci_upper * 100).toFixed(2)}%]`}
                          </code>
                        </td>
                        <td className="py-2.5 px-3 font-semibold">
                          <code>{isControl ? "N/A" : formatPercent(set.share_below_zero)}</code>
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium ${evidence.badgeClass}`}
                          >
                            {evidence.label}
                          </span>
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
                Posterior Forest Plot: Error Rate Effect E(s) vs. Zero-Effect Null
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
                    minRange={-maxAbsErrBound}
                    maxRange={maxAbsErrBound}
                    higherIsBetter={false}
                  />
                ))}
            </div>
          </section>

          {/* §6: Key Secondary Confirmatory Outcomes: Timing */}
          <section id="cs-secondary" className="typist-card p-6 space-y-5">
            <div>
              <h3 className="text-base font-semibold tracking-tight text-[#111111]">
                Key Secondary Outcome: Median IKI Targeting Effect F(s)
              </h3>
              <p className="text-xs text-[#666560] mt-1 leading-relaxed">
                Non-parametric Difference-in-Differences on pooled, unpaused (&lt;= 2000 ms, D24),
                adjacent clean inter-keystroke intervals (<code>IKI = t_down[j] - t_down[j-1]</code>
                ) with {resultsState.results.bootstrap_resamples.toLocaleString()} bootstrap
                resamples. Negative <code>F(s)</code> denotes faster motor transition execution
                beyond passive practice.
              </p>
            </div>

            {/* Timing Methodology Callout */}
            <div className="p-3.5 typist-inset grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-[#3D3C38]">
              <div>
                <div className="font-semibold text-[#111111]">1. Raw Sample Pooling (A.6)</div>
                <div className="mt-1 text-[#666560]">
                  Clean samples are concatenated across blocks before taking one exact median (never
                  a median-of-medians).
                </div>
              </div>
              <div>
                <div className="font-semibold text-[#111111]">2. Skew-Resistant Dispersion</div>
                <div className="mt-1 text-[#666560]">
                  Sample medians and interquartile ranges (<code>IQR = Q75 - Q25</code>) guard
                  against heavy right-tail hesitations.
                </div>
              </div>
              <div>
                <div className="font-semibold text-[#111111]">3. Bootstrap Fluency Contrast</div>
                <div className="mt-1 text-[#666560]">
                  <code>c(s) = med_retest - med_base · F(s) = c(s) - c(ref)</code>
                </div>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-[#111111]">
                <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
                  <tr>
                    <th className="py-2.5 px-3">Set</th>
                    <th className="py-2.5 px-3">Arm</th>
                    <th className="py-2.5 px-3">Baseline Median (IQR, n)</th>
                    <th className="py-2.5 px-3">Retest Median (IQR, n)</th>
                    <th className="py-2.5 px-3">c(s) Shift</th>
                    <th className="py-2.5 px-3">Effect F(s)</th>
                    <th className="py-2.5 px-3">95% Bootstrap CI</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EAEAEA] tabular-nums">
                  {resultsState.results.sets.map((set) => {
                    const isControl = set.arm === "control";
                    return (
                      <tr key={set.set_label} className={isControl ? "bg-[#FBFBFA]" : undefined}>
                        <td className="py-2.5 px-3 font-semibold text-[#111111]">
                          {set.set_label}
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                              isControl
                                ? "bg-[#F3F2EE] text-[#666560]"
                                : "bg-[#EBF3FA] text-[#1D5A8A]"
                            }`}
                          >
                            {revealed ? (isControl ? "Control Set" : set.arm) : "Block (Masked)"}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">
                            <code>
                              {set.baseline_iki_median_ms !== null
                                ? `${set.baseline_iki_median_ms.toFixed(1)} ms`
                                : "N/A"}
                            </code>
                          </div>
                          <div className="text-[10px] text-[#666560]">
                            <code>
                              IQR{" "}
                              {set.baseline_iki_iqr_ms !== null
                                ? `${set.baseline_iki_iqr_ms.toFixed(1)} ms`
                                : "N/A"}{" "}
                              · n={set.baseline_iki_n}
                            </code>
                          </div>
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="font-medium">
                            <code>
                              {set.retest_iki_median_ms !== null
                                ? `${set.retest_iki_median_ms.toFixed(1)} ms`
                                : "N/A"}
                            </code>
                          </div>
                          <div className="text-[10px] text-[#666560]">
                            <code>
                              IQR{" "}
                              {set.retest_iki_iqr_ms !== null
                                ? `${set.retest_iki_iqr_ms.toFixed(1)} ms`
                                : "N/A"}{" "}
                              · n={set.retest_iki_n}
                            </code>
                          </div>
                        </td>
                        <td className="py-2.5 px-3">
                          <code>{formatMs(set.iki_change_ms)}</code>
                        </td>
                        <td className="py-2.5 px-3 font-semibold">
                          <code>{isControl ? "Ref" : formatMs(set.iki_targeting_effect_ms)}</code>
                        </td>
                        <td className="py-2.5 px-3 text-[#666560]">
                          <code>
                            {isControl ||
                            set.iki_bootstrap_ci_lower_ms === null ||
                            set.iki_bootstrap_ci_upper_ms === null
                              ? "N/A"
                              : `[${set.iki_bootstrap_ci_lower_ms.toFixed(1)}, ${set.iki_bootstrap_ci_upper_ms.toFixed(1)}] ms`}
                          </code>
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
                Bootstrap Forest Plot: Median IKI Effect F(s) (ms)
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
                    minRange={-maxAbsIkiBound}
                    maxRange={maxAbsIkiBound}
                    higherIsBetter={false}
                  />
                ))}
            </div>
          </section>

          {/* §7: Assigned Weak Bigrams & Per-Transition Micro-Forensics */}
          <PerBigramForensicsSection
            rows={bigramRows}
            sets={resultsState.results.sets}
            revealed={revealed}
          />

          {/* Targeting Diagnostic & Next Steps (D12) */}
          <section className="typist-card p-6 space-y-4" data-testid="diagnostic-nudges-card">
            <div>
              <h3 className="text-base font-semibold tracking-tight text-[#111111]">
                Post-Retest Transition Coaching Diagnostics (D12)
              </h3>
              <p className="text-xs text-[#666560] mt-1">
                Actionable post-study feedback on transitions exhibiting residual error rate
                (&gt;5%) or hesitation (&gt;250 ms) on unseen Form B prose.
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
                      className="p-3.5 bg-[#FBF3DB] border border-[#EFE0B4] rounded-md text-xs space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[#111111] text-sm">
                          <code>"{n.bigram}"</code>
                        </span>
                        <span className="text-[#8A5A00] font-semibold tabular-nums">
                          <code>
                            {formatPercent(n.errorRate)} error rate
                            {n.medianIkiMs !== null ? ` · ${n.medianIkiMs.toFixed(0)} ms` : ""}
                          </code>
                        </span>
                      </div>
                      <p className="text-[#4A4945] leading-relaxed">
                        Assigned to Set {n.setLabel} ({revealed ? n.arm : "Masked"}). Notice whether{" "}
                        {n.arm === "control" && revealed
                          ? "this transition belonged to the unpracticed reference set and never received targeted drills: scheduling dedicated dictionary or LLM drills on this pair is the highest-yield next step."
                          : "same-hand or adjacent-finger crowding triggers premature keystrokes: practice deliberate 85%-tempo rhythmic release before accelerating."}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="p-4 bg-[#EDF3EC] border border-[#D4E4D2] rounded-md text-xs text-[#2B6E3F]">
                <span className="font-semibold">Clean post-study transfer!</span> Every retained
                bigram achieved &lt;=5% error rate and &lt;=250 ms median transition latency on
                unseen Form B retest passages.
              </div>
            )}
          </section>

          {/* §8: Instrumentation Overhead, Generator Fairness & 5-Gate Integrity Audit */}
          <SystemVerificationSection
            participantId={resultsState.results.participant_id}
            overview={overview}
            checks={checks}
            revealed={revealed}
            activeArms={resultsState.results.sets.map((s) => s.arm)}
          />

          {/* Pre-registered Exclusions & Reproducibility Manifest */}
          <section id="cs-exclusions" className="typist-card p-6 space-y-5">
            <div>
              <h3 className="text-base font-semibold tracking-tight text-[#111111]">
                Pre-registered Exclusions Report (D20, D23)
              </h3>
              <p className="text-xs text-[#666560] mt-1">
                Pre-committed data filtering rules applied identically across all arms before
                posterior sampling, plus deterministic session and PRNG audit identifiers.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 text-xs text-[#666560]">
              <div className="p-4 typist-inset space-y-2">
                <h4 className="font-semibold text-[#111111]">Excluded Sessions (D20)</h4>
                {resultsState.results.exclusions?.excluded_sessions &&
                resultsState.results.exclusions.excluded_sessions.length > 0 ? (
                  <ul className="divide-y divide-[#EAEAEA]">
                    {resultsState.results.exclusions.excluded_sessions.map((exc) => (
                      <li key={exc.session_id} className="py-1.5 flex justify-between gap-2">
                        <span>
                          <code>{exc.session_id.slice(0, 8)}...</code>
                        </span>
                        <span>
                          Day {exc.day_index} ({exc.phase}) ·{" "}
                          <span className="font-medium text-[#8A5A00]">{exc.reason}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[#666560]">
                    No sessions excluded (0 abandoned or superseded).
                  </p>
                )}
              </div>

              <div className="p-4 typist-inset space-y-2">
                <h4 className="font-semibold text-[#111111]">
                  Dropped Bigrams (&lt;20 Retest Attempts, D23c)
                </h4>
                {resultsState.results.exclusions?.dropped_bigrams &&
                resultsState.results.exclusions.dropped_bigrams.length > 0 ? (
                  <ul className="divide-y divide-[#EAEAEA]">
                    {resultsState.results.exclusions.dropped_bigrams.map((drp) => (
                      <li key={drp.bigram} className="py-1.5 flex justify-between gap-2">
                        <span className="font-semibold text-[#111111]">
                          <code>"{drp.bigram}"</code>
                        </span>
                        <span>
                          Set {drp.set_label} ({revealed ? drp.arm : "Masked"}) ·{" "}
                          <span className="text-[#8A5A00] font-medium">
                            {drp.retest_attempts} attempts
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[#666560]">
                    No bigrams dropped (all achieved &gt;=20 retest attempts).
                  </p>
                )}
              </div>

              <div className="p-4 typist-inset space-y-2">
                <h4 className="font-semibold text-[#111111]">Pause-Filtered Intervals (D24)</h4>
                {resultsState.results.exclusions?.pause_counts &&
                Object.keys(resultsState.results.exclusions.pause_counts).length > 0 ? (
                  <ul className="divide-y divide-[#EAEAEA]">
                    {Object.entries(resultsState.results.exclusions.pause_counts).map(
                      ([cellKey, cnt]) => (
                        <li key={cellKey} className="py-1.5 flex justify-between gap-2">
                          <span>
                            <code>{cellKey}</code>
                          </span>
                          <span className="font-medium text-[#111111]">
                            <code>{cnt}</code> paused (&gt;2000 ms)
                          </span>
                        </li>
                      ),
                    )}
                  </ul>
                ) : (
                  <p className="text-[#666560]">
                    0 transitions exceeded the strict 2000 ms pause threshold.
                  </p>
                )}
              </div>
            </div>

            {/* Reproducibility Audit Footer */}
            <div className="p-3.5 typist-inset flex flex-wrap items-center justify-between gap-3 text-[11px] text-[#666560]">
              <div>
                <span className="font-semibold text-[#111111]">Baseline Form A Sessions: </span>
                <code>
                  {resultsState.results.analyzed_baseline_session_ids
                    .map((s) => s.slice(0, 8))
                    .join(", ")}
                </code>
              </div>
              <div>
                <span className="font-semibold text-[#111111]">Retest Form B Sessions: </span>
                <code>
                  {resultsState.results.analyzed_retest_session_ids
                    .map((s) => s.slice(0, 8))
                    .join(", ")}
                </code>
              </div>
              <div>
                <span className="font-semibold text-[#111111]">Reproducibility Seed: </span>
                <code>
                  seed={resultsState.results.seed} · draws={resultsState.results.posterior_draws} ·
                  boot={resultsState.results.bootstrap_resamples}
                </code>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
