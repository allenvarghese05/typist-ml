import type {
  ArmGenerationSummary,
  Overview,
  ParticipantResults,
  SessionOverheadEntry,
  SessionTrendEntry,
  SetOutcome,
} from "../../api/analysis";
import type { ChecksResponse } from "../../api/client";

export interface PerBigramComparison {
  readonly bigram: string;
  readonly setLabel: string;
  readonly arm: string;
  readonly dropped: boolean;
  readonly baselineAttempts: number;
  readonly baselineErrors: number;
  readonly baselineErrorRate: number | null;
  readonly baselineMedianIkiMs: number | null;
  readonly retestAttempts: number;
  readonly retestErrors: number;
  readonly retestErrorRate: number | null;
  readonly retestMedianIkiMs: number | null;
}

export interface GeneratorSpecMeta {
  readonly mechanism: string;
  readonly lexicalConstraint: string;
  readonly computeProfile: string;
  readonly hypothesisRole: string;
}

export const GENERATOR_SPECS: Record<string, GeneratorSpecMeta> = {
  control: {
    mechanism: "Neutral English prose without weak-bigram oversampling",
    lexicalConstraint: "Standard corpus vocabulary; zero targeted bigram enrichment",
    computeProfile: "O(1) deterministic draw · 0 MB model footprint",
    hypothesisRole:
      "Baseline counterfactual: isolates general typing volume, keyboard warm-up, and Hawthorne familiarity from targeted motor transfer.",
  },
  heuristic: {
    mechanism: "Greedy frequency-weighted dictionary assembly",
    lexicalConstraint:
      "100% real English words filtered from corpus WordIndex; D30 density [0.10, 0.40]",
    computeProfile: "< 2 ms deterministic CPU lookup · 0 MB neural weights",
    hypothesisRole:
      "Tests whether real-word lexical repetition alone matches generative sentence context when target bigram density is held constant.",
  },
  markov: {
    mechanism: "Character-level n-gram transition sampling with target bigram boosting",
    lexicalConstraint:
      "Pronounceable orthographic sequences (real + synthetic); D30 density [0.10, 0.40]",
    computeProfile: "< 5 ms stochastic transition walk · ~1 MB transition table",
    hypothesisRole:
      "Isolates pure sub-lexical motor-transition repetition stripped of top-down word-preview or semantic anticipation.",
  },
  llm: {
    mechanism:
      "Constrained local autoregressive synthesis via quantized 1B language model (mlx-lm)",
    lexicalConstraint:
      "Coherent English clauses validated against corpus lexicon + D30 density [0.10, 0.40]",
    computeProfile: "On-device Apple Silicon Metal inference · background pool pre-generation",
    hypothesisRole:
      "Tests whether ecologically valid sentence syntax and multi-word lookahead improve transfer to unseen natural prose on Form B.",
  },
};

const SET_PALETTE: Record<string, string> = {
  A: "#1F5E8B",
  B: "#666560",
  C: "#2B6E3F",
  D: "#8A5A00",
};

function fmtPct(val: number | null, digits = 1): string {
  if (val === null) return "N/A";
  return `${(val * 100).toFixed(digits)}%`;
}

function fmtSignedPp(val: number | null, digits = 2): string {
  if (val === null) return "N/A";
  const pp = val * 100;
  return `${pp > 0 ? "+" : ""}${pp.toFixed(digits)} pp`;
}

function fmtSignedMs(val: number | null, digits = 1): string {
  if (val === null) return "N/A";
  return `${val > 0 ? "+" : ""}${val.toFixed(digits)} ms`;
}

export function classifyEvidence(shareBelowZero: number | null): {
  readonly label: string;
  readonly badgeClass: string;
} {
  if (shareBelowZero === null) {
    return {
      label: "Reference Baseline",
      badgeClass: "bg-[#F3F2EE] text-[#666560]",
    };
  }
  if (shareBelowZero >= 0.975) {
    return {
      label: "Decisive Benefit (>=97.5%)",
      badgeClass: "bg-[#EDF3EC] text-[#2B5930]",
    };
  }
  if (shareBelowZero >= 0.9) {
    return {
      label: "Strong Benefit (>=90%)",
      badgeClass: "bg-[#EDF3EC] text-[#2B6E3F]",
    };
  }
  if (shareBelowZero >= 0.75) {
    return {
      label: "Directional Benefit",
      badgeClass: "bg-[#EBF3FA] text-[#1F5E8B]",
    };
  }
  if (shareBelowZero <= 0.1) {
    return {
      label: "Counter-Productive",
      badgeClass: "bg-[#FCEBEC] text-[#9F2F2D]",
    };
  }
  return {
    label: "Indeterminate / Null",
    badgeClass: "bg-[#FBF3DB] text-[#8A5A00]",
  };
}

export interface CaseStudyAbstractProps {
  readonly results: ParticipantResults;
  readonly revealed: boolean;
  readonly totalEvents: number | null;
  readonly completedSessionsCount: number | null;
}

export function CaseStudyAbstractSection({
  results,
  revealed,
  totalEvents,
  completedSessionsCount,
}: CaseStudyAbstractProps): React.JSX.Element {
  const wpmDelta =
    results.baseline_wpm !== null && results.retest_wpm !== null
      ? results.retest_wpm - results.baseline_wpm
      : null;
  const wpmRelGain =
    wpmDelta !== null && results.baseline_wpm !== null && results.baseline_wpm > 0
      ? wpmDelta / results.baseline_wpm
      : null;

  const accDelta =
    results.baseline_accuracy !== null && results.retest_accuracy !== null
      ? results.retest_accuracy - results.baseline_accuracy
      : null;
  const baseErr = results.baseline_accuracy !== null ? 1 - results.baseline_accuracy : null;
  const retErr = results.retest_accuracy !== null ? 1 - results.retest_accuracy : null;
  const relErrDrop =
    baseErr !== null && retErr !== null && baseErr > 0 ? (retErr - baseErr) / baseErr : null;

  const targetedSets = results.sets.filter((s) => s.arm !== "control");
  const controlSet = results.sets.find((s) => s.arm === "control") ?? null;

  const bestErrorSet: SetOutcome | null =
    targetedSets
      .filter((s) => s.targeting_effect !== null)
      .sort((a, b) => (a.targeting_effect ?? 0) - (b.targeting_effect ?? 0))[0] ?? null;

  const bestFluencySet: SetOutcome | null =
    targetedSets
      .filter((s) => s.iki_targeting_effect_ms !== null)
      .sort((a, b) => (a.iki_targeting_effect_ms ?? 0) - (b.iki_targeting_effect_ms ?? 0))[0] ??
    null;

  const totalAssignedBigrams = results.sets.reduce((acc, s) => acc + s.bigrams.length, 0);
  const totalRetainedBigrams = results.sets.reduce((acc, s) => acc + s.retained_bigrams.length, 0);
  const pooledBigramObs = results.sets.reduce(
    (acc, s) => acc + s.baseline_attempts + s.retest_attempts,
    0,
  );

  const armDisplay = (s: SetOutcome) =>
    revealed ? `Set ${s.set_label} (${s.arm})` : `Set ${s.set_label} (Masked)`;

  return (
    <section id="cs-abstract" className="typist-card p-6 space-y-5">
      {/* Study Metadata Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-4 border-b border-[#EAEAEA]">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[#111111]">
            §1 · Executive Case Study &amp; Empirical Verdict
          </h2>
          <p className="text-xs text-[#666560] mt-0.5">
            Within-subject N-of-1 longitudinal typing intervention · Pre/post transfer evaluation on
            unseen prose (Form A to Form B).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className="px-2.5 py-1 rounded bg-[#F6F5F2] text-[#4A4945]">
            <code>{results.posterior_draws.toLocaleString()}</code> Beta draws
          </span>
          <span className="px-2.5 py-1 rounded bg-[#F6F5F2] text-[#4A4945]">
            <code>{results.bootstrap_resamples.toLocaleString()}</code> bootstrap resamples
          </span>
          <span className="px-2.5 py-1 rounded bg-[#F6F5F2] text-[#4A4945]">
            PRNG seed <code>{results.seed}</code>
          </span>
        </div>
      </div>

      {/* Dynamic Research Synthesis */}
      <div className="p-4 typist-inset space-y-2.5 text-xs text-[#3D3C38] leading-relaxed">
        <p>
          <span className="font-semibold text-[#111111]">Study Objective &amp; Cohort Scope:</span>{" "}
          Participant <span className="font-semibold text-[#111111]">{results.alias}</span>{" "}
          completed{" "}
          <span className="font-semibold text-[#111111]">
            {completedSessionsCount ??
              results.analyzed_baseline_session_ids.length +
                results.analyzed_retest_session_ids.length}{" "}
            recorded sessions
          </span>
          {totalEvents !== null ? (
            <>
              {" "}
              comprising{" "}
              <span className="font-semibold text-[#111111]">
                {totalEvents.toLocaleString()} raw keystroke telemetry events
              </span>
            </>
          ) : null}
          . During Form A baseline assessment ({results.analyzed_baseline_session_ids.length}{" "}
          sessions), keystroke transitions were attributed server-side to isolate{" "}
          <span className="font-semibold text-[#111111]">
            {totalAssignedBigrams} high-friction letter bigrams
          </span>{" "}
          ({totalRetainedBigrams} meeting the pre-registered &gt;=20 retest attempt threshold across{" "}
          {pooledBigramObs.toLocaleString()} pooled target observations), which were snake-dealt
          into {results.sets.length} difficulty-matched sets.
        </p>
        <p>
          <span className="font-semibold text-[#111111]">Macro Performance Transfer:</span> Across
          the full protocol, gross prose typing speed progressed from{" "}
          <span className="font-semibold text-[#111111]">
            {results.baseline_wpm?.toFixed(1) ?? "N/A"} WPM
          </span>{" "}
          on Form A to{" "}
          <span className="font-semibold text-[#111111]">
            {results.retest_wpm?.toFixed(1) ?? "N/A"} WPM
          </span>{" "}
          on unseen Form B (
          <span className="font-semibold text-[#2B6E3F]">
            {wpmDelta !== null
              ? `${wpmDelta >= 0 ? "+" : ""}${wpmDelta.toFixed(1)} WPM${
                  wpmRelGain !== null
                    ? `, ${wpmRelGain >= 0 ? "+" : ""}${(wpmRelGain * 100).toFixed(1)}%`
                    : ""
                }`
              : "N/A"}
          </span>
          ), while whole-passage character accuracy moved from{" "}
          <span className="font-semibold text-[#111111]">
            {fmtPct(results.baseline_accuracy, 2)}
          </span>{" "}
          to{" "}
          <span className="font-semibold text-[#111111]">{fmtPct(results.retest_accuracy, 2)}</span>{" "}
          (
          <span className="font-semibold text-[#2B6E3F]">
            {fmtSignedPp(accDelta)}
            {relErrDrop !== null
              ? `, ${(Math.abs(relErrDrop) * 100).toFixed(1)}% relative reduction in corpus errors`
              : ""}
          </span>
          ).
        </p>
        {bestErrorSet && (
          <p>
            <span className="font-semibold text-[#111111]">
              Causal Difference-in-Differences Verdict:
            </span>{" "}
            Subtracting passive test-retest drift observed on the unpracticed reference set
            {controlSet
              ? ` (Set ${controlSet.set_label}: ${fmtPct(controlSet.baseline_error_rate)} to ${fmtPct(controlSet.retest_error_rate)}, d = ${fmtSignedPp(controlSet.error_rate_change)})`
              : ""}
            , the strongest targeted error reduction occurred in{" "}
            <span className="font-semibold text-[#111111]">{armDisplay(bestErrorSet)}</span> with
            net targeting effect <code>E = {fmtSignedPp(bestErrorSet.targeting_effect)}</code> (95%
            Jeffreys posterior CI{" "}
            <code>
              [
              {bestErrorSet.posterior_effect_ci_lower !== null
                ? `${(bestErrorSet.posterior_effect_ci_lower * 100).toFixed(2)}%`
                : "N/A"}
              ,{" "}
              {bestErrorSet.posterior_effect_ci_upper !== null
                ? `${(bestErrorSet.posterior_effect_ci_upper * 100).toFixed(2)}%`
                : "N/A"}
              ]
            </code>
            , posterior probability of true causal benefit{" "}
            <span className="font-semibold text-[#2B6E3F]">
              P(E &lt; 0) = {fmtPct(bestErrorSet.share_below_zero, 1)}
            </span>
            )
            {bestFluencySet
              ? ` and net inter-keystroke fluency gain F = ${fmtSignedMs(bestFluencySet.iki_targeting_effect_ms)} on ${armDisplay(bestFluencySet)}.`
              : "."}
          </p>
        )}
      </div>

      {/* 6-Card Executive Scorecard */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="p-3.5 typist-inset flex flex-col justify-between">
          <div className="text-[11px] text-[#666560] font-medium">Baseline WPM (Form A)</div>
          <div className="text-xl font-semibold text-[#111111] mt-1.5 tabular-nums">
            <code>{results.baseline_wpm?.toFixed(1) ?? "N/A"}</code>
          </div>
          <div className="text-[11px] text-[#666560] mt-1">
            {results.analyzed_baseline_session_ids.length} pooled sessions
          </div>
        </div>

        <div className="p-3.5 typist-inset flex flex-col justify-between">
          <div className="text-[11px] text-[#666560] font-medium">Retest WPM (Form B)</div>
          <div className="text-xl font-semibold text-[#111111] mt-1.5 tabular-nums">
            <code>{results.retest_wpm?.toFixed(1) ?? "N/A"}</code>
          </div>
          <div className="text-[11px] text-[#2B6E3F] font-medium mt-1 tabular-nums">
            {wpmDelta !== null
              ? `${wpmDelta >= 0 ? "+" : ""}${wpmDelta.toFixed(1)} WPM (${wpmRelGain !== null ? `${wpmRelGain >= 0 ? "+" : ""}${(wpmRelGain * 100).toFixed(1)}%` : ""})`
              : "Unseen transfer"}
          </div>
        </div>

        <div className="p-3.5 typist-inset flex flex-col justify-between">
          <div className="text-[11px] text-[#666560] font-medium">Baseline Accuracy</div>
          <div className="text-xl font-semibold text-[#111111] mt-1.5 tabular-nums">
            <code>{fmtPct(results.baseline_accuracy, 2)}</code>
          </div>
          <div className="text-[11px] text-[#666560] mt-1">
            Error {baseErr !== null ? fmtPct(baseErr, 2) : "N/A"}
          </div>
        </div>

        <div className="p-3.5 typist-inset flex flex-col justify-between">
          <div className="text-[11px] text-[#666560] font-medium">Retest Accuracy</div>
          <div className="text-xl font-semibold text-[#111111] mt-1.5 tabular-nums">
            <code>{fmtPct(results.retest_accuracy, 2)}</code>
          </div>
          <div className="text-[11px] text-[#2B6E3F] font-medium mt-1 tabular-nums">
            {fmtSignedPp(accDelta)} net shift
          </div>
        </div>

        <div className="p-3.5 typist-inset flex flex-col justify-between">
          <div className="text-[11px] text-[#666560] font-medium">Best Net Effect E(s)</div>
          <div className="text-xl font-semibold text-[#1F5E8B] mt-1.5 tabular-nums">
            <code>{bestErrorSet ? fmtSignedPp(bestErrorSet.targeting_effect) : "N/A"}</code>
          </div>
          <div className="text-[11px] text-[#666560] mt-1 truncate">
            {bestErrorSet
              ? `${armDisplay(bestErrorSet)} · P=${fmtPct(bestErrorSet.share_below_zero, 1)}`
              : "No targeted arm"}
          </div>
        </div>

        <div className="p-3.5 typist-inset flex flex-col justify-between">
          <div className="text-[11px] text-[#666560] font-medium">Best Fluency F(s)</div>
          <div className="text-xl font-semibold text-[#2B6E3F] mt-1.5 tabular-nums">
            <code>
              {bestFluencySet ? fmtSignedMs(bestFluencySet.iki_targeting_effect_ms) : "N/A"}
            </code>
          </div>
          <div className="text-[11px] text-[#666560] mt-1 truncate">
            {bestFluencySet ? armDisplay(bestFluencySet) : "Median IKI DiD"}
          </div>
        </div>
      </div>
    </section>
  );
}

export function ExperimentalDesignSection(): React.JSX.Element {
  const validityControls = [
    {
      threat: "General practice & warm-up drift",
      risk: "Typing 10 daily sessions naturally speeds up fingers even without targeted bigram coaching.",
      mitigation:
        "Within-subject held-out Control set: one difficulty-matched bigram set receives zero targeted drills, anchoring the Difference-in-Differences subtraction d(s) - d(control).",
    },
    {
      threat: "Regression to the mean on noisy bigrams",
      risk: "Rare bigrams with 1/3 errors look artificially weak (33%) at baseline and appear to 'improve' by chance at retest.",
      mitigation:
        "Candidate floor n >= 15 attempts (D28) plus Empirical-Bayes shrinkage toward the participant's global error prior p0 before ranking (§3.4).",
    },
    {
      threat: "Baseline set imbalance across arms",
      risk: "Dealing ranks 1-4 to Arm A and ranks 5-8 to Arm B would confound arm efficacy with initial difficulty.",
      mitigation:
        "Snake-draft dealing (1->A, 2->B, ..., 2k->A; D04) equalizes rank sums across sets prior to seeded PRNG arm permutation.",
    },
    {
      threat: "Passage memorization vs. motor transfer",
      risk: "Retesting on identical text conflates episodic recall of specific sentences with generalized motor-program speed.",
      mitigation:
        "Disjoint corpus forms: Baseline uses fixed Form A prose, whereas Retest composes unseen participant-balanced Form B prose (§5).",
    },
    {
      threat: "Expectancy bias & block order fatigue",
      risk: "Knowing which block is LLM-generated or always typing an arm last could skew effort and fatigue.",
      mitigation:
        "Single-blind presentation as generic 'Block 1..K' (D18) with daily counterbalanced block ordering and locked debrief until status='done'.",
    },
  ];

  return (
    <section id="cs-methodology" className="typist-card p-6 space-y-5">
      <div>
        <h3 className="text-base font-semibold tracking-tight text-[#111111]">
          §2 · Experimental Design, Causal Identification &amp; Validity Controls
        </h3>
        <p className="text-xs text-[#666560] mt-1 leading-relaxed">
          Why this protocol supports causal inference within a single participant: every typist acts
          as their own matched control across parallel bigram sets trained simultaneously over the
          same calendar days, hardware keyboard, and circadian conditions.
        </p>
      </div>

      {/* 4-Stage Pipeline */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
        <div className="p-4 typist-inset space-y-1.5">
          <div className="font-semibold text-[#111111]">Stage I · Telemetry &amp; Form A</div>
          <p className="text-[#666560] leading-relaxed">
            High-resolution browser <code>performance.now()</code> timestamps capture press{" "}
            <code>t_down</code>, release <code>t_up</code>, dwell <code>d = t_up - t_down</code>,
            and press-to-press <code>IKI</code> across two ~2,700 character Form A passages.
          </p>
        </div>
        <div className="p-4 typist-inset space-y-1.5">
          <div className="font-semibold text-[#111111]">Stage II · Empirical-Bayes Freeze</div>
          <p className="text-[#666560] leading-relaxed">
            Python server attribution pools raw transitions, filters pauses (&gt;2000 ms, D24),
            ranks bigrams via smoothed rate <code>(e_b + m*p0) / (n_b + m)</code>, snake-deals sets,
            and freezes SQLite rows via immutability trigger.
          </p>
        </div>
        <div className="p-4 typist-inset space-y-1.5">
          <div className="font-semibold text-[#111111]">Stage III · Blinded 10-Day Practice</div>
          <p className="text-[#666560] leading-relaxed">
            Background worker pre-generates drills calibrated to target density{" "}
            <code>[0.10, 0.40]</code> (D30). Daily sessions interleave arms in counterbalanced order
            under blinded block labels.
          </p>
        </div>
        <div className="p-4 typist-inset space-y-1.5">
          <div className="font-semibold text-[#111111]">Stage IV · Form B Transfer &amp; DiD</div>
          <p className="text-[#666560] leading-relaxed">
            Two post-practice sessions on unseen Form B prose measure transfer. Conjugate Jeffreys
            Beta posteriors and 10,000-resample bootstraps quantify net arm effects over control.
          </p>
        </div>
      </div>

      {/* Threats-to-Validity Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-[#111111]">
          <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
            <tr>
              <th className="py-2.5 px-3 w-1/4">Confounder / Threat to Validity</th>
              <th className="py-2.5 px-3 w-1/3">Uncontrolled Failure Mode</th>
              <th className="py-2.5 px-3">Protocol Mechanism in Typist-ML</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#EAEAEA]">
            {validityControls.map((row) => (
              <tr key={row.threat} className="align-top">
                <td className="py-2.5 px-3 font-semibold text-[#111111]">{row.threat}</td>
                <td className="py-2.5 px-3 text-[#666560] leading-relaxed">{row.risk}</td>
                <td className="py-2.5 px-3 text-[#3D3C38] leading-relaxed">{row.mitigation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export interface LongitudinalTrajectorySectionProps {
  readonly trend: readonly SessionTrendEntry[];
  readonly sets: readonly SetOutcome[];
  readonly revealed: boolean;
}

export function LongitudinalTrajectorySection({
  trend,
  sets,
  revealed,
}: LongitudinalTrajectorySectionProps): React.JSX.Element | null {
  if (trend.length === 0) return null;

  const width = 560;
  const height = 210;
  const padLeft = 42;
  const padRight = 40;
  const padTop = 20;
  const padBottom = 34;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const wpms = trend.map((s) => s.wpm ?? 0);
  const maxWpm = Math.max(60, Math.ceil((Math.max(...wpms, 0) + 10) / 10) * 10);

  const xAt = (idx: number) =>
    trend.length <= 1 ? padLeft + plotW / 2 : padLeft + (idx / (trend.length - 1)) * plotW;
  const yWpm = (val: number | null) => padTop + plotH - ((val ?? 0) / maxWpm) * plotH;
  const yAcc = (val: number | null) => {
    const clamped = Math.max(0.8, Math.min(1.0, val ?? 0.8));
    return padTop + plotH - ((clamped - 0.8) / 0.2) * plotH;
  };

  const wpmLine = trend
    .map((s, i) => (s.wpm !== null ? `${xAt(i)},${yWpm(s.wpm)}` : null))
    .filter((v): v is string => v !== null)
    .join(" ");

  const accLine = trend
    .map((s, i) => (s.accuracy !== null ? `${xAt(i)},${yAcc(s.accuracy)}` : null))
    .filter((v): v is string => v !== null)
    .join(" ");

  // Set error-rate divergence chart scaling
  const setLabels = sets.map((s) => s.set_label);
  const allSetRates = trend.flatMap((t) =>
    setLabels
      .map((lbl) => t.per_set_error_rate[lbl] ?? null)
      .filter((v): v is number => v !== null),
  );
  const maxErrRate = Math.max(0.15, Math.ceil(Math.max(...allSetRates, 0.1) * 20) / 20);
  const yErr = (val: number) => padTop + plotH - (Math.min(val, maxErrRate) / maxErrRate) * plotH;

  const shortTag = (s: SessionTrendEntry) => {
    const prefix = s.phase === "baseline" ? "B" : s.phase === "practice" ? "P" : "R";
    return `${prefix}${s.day_index}`;
  };

  return (
    <section id="cs-trajectory" className="typist-card p-6 space-y-6">
      <div>
        <h3 className="text-base font-semibold tracking-tight text-[#111111]">
          §4 · Longitudinal 14-Session Learning Trajectory &amp; Set Divergence
        </h3>
        <p className="text-xs text-[#666560] mt-1 leading-relaxed">
          Session-by-session progression across Form A Baseline (<code>B1-B2</code>), 10-Day
          Targeted Practice (<code>P1-P10</code>), and unseen Form B Retest (<code>R1-R2</code>).
        </p>
      </div>

      {/* Dual Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Left: WPM & Accuracy */}
        <div className="p-4 typist-inset space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-xs font-semibold text-[#111111]">
                Macro Speed &amp; Corpus Accuracy
              </div>
              <div className="text-[11px] text-[#666560]">
                Left axis: WPM · Right axis: Accuracy (80%-100%)
              </div>
            </div>
            <div className="flex items-center gap-3 text-[11px]">
              <span className="inline-flex items-center gap-1.5 text-[#111111] font-medium">
                <span className="w-2 h-2 rounded-full bg-[#111111] inline-block" />
                WPM
              </span>
              <span className="inline-flex items-center gap-1.5 text-[#2B6E3F] font-medium">
                <span className="w-2 h-2 rounded-full bg-[#2B6E3F] inline-block" />
                Accuracy
              </span>
            </div>
          </div>

          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto overflow-visible"
            role="img"
            aria-label="Longitudinal WPM and accuracy chart"
          >
            {[0, 0.25, 0.5, 0.75, 1].map((r) => {
              const y = padTop + plotH - r * plotH;
              const wVal = Math.round(r * maxWpm);
              const aVal = Math.round(80 + r * 20);
              return (
                <g key={r}>
                  <line
                    x1={padLeft}
                    y1={y}
                    x2={width - padRight}
                    y2={y}
                    stroke="#E4E2DC"
                    strokeWidth={1}
                  />
                  <text
                    x={padLeft - 6}
                    y={y + 3}
                    textAnchor="end"
                    className="text-[9px] fill-[#8A8883]"
                  >
                    {wVal}
                  </text>
                  <text
                    x={width - padRight + 6}
                    y={y + 3}
                    textAnchor="start"
                    className="text-[9px] fill-[#2B6E3F]"
                  >
                    {aVal}%
                  </text>
                </g>
              );
            })}

            {wpmLine && (
              <polyline
                fill="none"
                stroke="#111111"
                strokeWidth={2}
                strokeLinejoin="round"
                points={wpmLine}
              />
            )}
            {accLine && (
              <polyline
                fill="none"
                stroke="#2B6E3F"
                strokeWidth={1.75}
                strokeDasharray="4 2"
                strokeLinejoin="round"
                points={accLine}
              />
            )}

            {trend.map((s, idx) => {
              const cx = xAt(idx);
              return (
                <g key={s.session_id}>
                  {s.wpm !== null && (
                    <circle
                      cx={cx}
                      cy={yWpm(s.wpm)}
                      r={3}
                      fill={s.phase === "practice" ? "#111111" : "#1F5E8B"}
                    />
                  )}
                  {s.accuracy !== null && (
                    <circle cx={cx} cy={yAcc(s.accuracy)} r={2.5} fill="#2B6E3F" />
                  )}
                  <text
                    x={cx}
                    y={height - 10}
                    textAnchor="middle"
                    className="text-[9px] fill-[#666560]"
                  >
                    {shortTag(s)}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Right: Per-Set Error Rate Divergence */}
        <div className="p-4 typist-inset space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-xs font-semibold text-[#111111]">
                Within-Subject Set Error Divergence
              </div>
              <div className="text-[11px] text-[#666560]">
                Targeted bigram error rate vs. unpracticed reference set across sessions
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2.5 text-[11px]">
              {sets.map((s) => (
                <span
                  key={s.set_label}
                  className="inline-flex items-center gap-1 text-[#111111] font-medium"
                >
                  <span
                    className="w-2 h-2 rounded-full inline-block"
                    style={{ backgroundColor: SET_PALETTE[s.set_label] ?? "#111111" }}
                  />
                  Set {s.set_label} ({revealed ? s.arm : "Masked"})
                </span>
              ))}
            </div>
          </div>

          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto overflow-visible"
            role="img"
            aria-label="Per-set error rate divergence chart"
          >
            {[0, 0.25, 0.5, 0.75, 1].map((r) => {
              const y = padTop + plotH - r * plotH;
              const pctVal = (r * maxErrRate * 100).toFixed(0);
              return (
                <g key={r}>
                  <line
                    x1={padLeft}
                    y1={y}
                    x2={width - padRight}
                    y2={y}
                    stroke="#E4E2DC"
                    strokeWidth={1}
                  />
                  <text
                    x={padLeft - 6}
                    y={y + 3}
                    textAnchor="end"
                    className="text-[9px] fill-[#8A8883]"
                  >
                    {pctVal}%
                  </text>
                </g>
              );
            })}

            {sets.map((set) => {
              const color = SET_PALETTE[set.set_label] ?? "#111111";
              const isControl = set.arm === "control";
              const pts = trend
                .map((t, i) => {
                  const val = t.per_set_error_rate[set.set_label];
                  return val !== undefined && val !== null ? `${xAt(i)},${yErr(val)}` : null;
                })
                .filter((p): p is string => p !== null)
                .join(" ");

              return (
                <g key={set.set_label}>
                  {pts && (
                    <polyline
                      fill="none"
                      stroke={color}
                      strokeWidth={isControl ? 1.75 : 2.25}
                      strokeDasharray={isControl ? "4 3" : undefined}
                      strokeLinejoin="round"
                      points={pts}
                    />
                  )}
                  {trend.map((t, i) => {
                    const val = t.per_set_error_rate[set.set_label];
                    if (val === undefined || val === null) return null;
                    return (
                      <circle
                        key={`${set.set_label}-${t.session_id}`}
                        cx={xAt(i)}
                        cy={yErr(val)}
                        r={2.75}
                        fill={color}
                      />
                    );
                  })}
                </g>
              );
            })}

            {trend.map((s, idx) => (
              <text
                key={s.session_id}
                x={xAt(idx)}
                y={height - 10}
                textAnchor="middle"
                className="text-[9px] fill-[#666560]"
              >
                {shortTag(s)}
              </text>
            ))}
          </svg>
        </div>
      </div>

      {/* Session-by-Session Telemetry Ledger */}
      <details className="group">
        <summary className="cursor-pointer select-none text-xs font-semibold text-[#111111] flex items-center justify-between p-3 typist-inset">
          <span>
            Complete Chronological Session Ledger ({trend.length} completed sessions · click to
            toggle table)
          </span>
          <span className="text-[#666560] font-normal">Show / Hide Rows</span>
        </summary>
        <div className="overflow-x-auto mt-3">
          <table className="w-full text-left text-xs text-[#111111]">
            <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
              <tr>
                <th className="py-2 px-3">Slot</th>
                <th className="py-2 px-3">Phase &amp; Day</th>
                <th className="py-2 px-3">Session ID</th>
                <th className="py-2 px-3">WPM</th>
                <th className="py-2 px-3">Accuracy</th>
                {sets.map((s) => (
                  <th key={s.set_label} className="py-2 px-3">
                    Set {s.set_label} ({revealed ? s.arm : "Masked"}) Error
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EAEAEA] tabular-nums">
              {trend.map((t) => (
                <tr key={t.session_id}>
                  <td className="py-1.5 px-3 font-semibold">
                    <code>{shortTag(t)}</code>
                  </td>
                  <td className="py-1.5 px-3 capitalize">
                    {t.phase} · Day {t.day_index}
                  </td>
                  <td className="py-1.5 px-3 text-[#666560]">
                    <code>{t.session_id.slice(0, 8)}</code>
                  </td>
                  <td className="py-1.5 px-3 font-medium">
                    <code>{t.wpm !== null ? t.wpm.toFixed(1) : "N/A"}</code>
                  </td>
                  <td className="py-1.5 px-3">
                    <code>{fmtPct(t.accuracy, 2)}</code>
                  </td>
                  {sets.map((s) => {
                    const rate = t.per_set_error_rate[s.set_label] ?? null;
                    const att = t.per_set_attempts[s.set_label] ?? 0;
                    const err = t.per_set_errors[s.set_label] ?? 0;
                    return (
                      <td key={s.set_label} className="py-1.5 px-3">
                        <code>
                          {rate !== null ? `${(rate * 100).toFixed(1)}% (${err}/${att})` : "N/A"}
                        </code>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

export interface PerBigramForensicsProps {
  readonly rows: readonly PerBigramComparison[];
  readonly sets: readonly SetOutcome[];
  readonly revealed: boolean;
}

export function PerBigramForensicsSection({
  rows,
  sets,
  revealed,
}: PerBigramForensicsProps): React.JSX.Element {
  return (
    <section id="cs-bigrams" className="typist-card p-6 space-y-5">
      <div>
        <h3 className="text-base font-semibold tracking-tight text-[#111111]">
          §7 · Assigned Weak Bigrams &amp; Per-Transition Micro-Forensics
        </h3>
        <p className="text-xs text-[#666560] mt-1 leading-relaxed">
          Individual transition-level breakdown across snake-dealt weak bigrams (D04), comparing
          pooled Form A baseline observations against post-practice Form B retest transfer.
        </p>
      </div>

      {/* Set Pills Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {sets.map((set) => (
          <div key={set.set_label} className="p-4 typist-inset">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-[#111111]">
                Set {set.set_label} ({revealed ? set.arm : "Masked"})
              </span>
              <span className="text-xs text-[#666560]">
                <code>{set.retained_bigrams.length}</code> retained /{" "}
                <code>{set.bigrams.length}</code> assigned
              </span>
            </div>

            <div className="flex flex-wrap gap-1.5 mt-2">
              {set.retained_bigrams.map((bg) => (
                <span
                  key={bg}
                  className="px-2 py-0.5 bg-white border border-[#EAEAEA] rounded text-xs font-medium text-[#111111]"
                >
                  <code>"{bg}"</code>
                </span>
              ))}
              {set.dropped_bigrams.map((bg) => (
                <span
                  key={bg}
                  className="px-2 py-0.5 bg-[#FBF3DB] border border-[#EFE0B4] rounded text-xs text-[#8A5A00] line-through"
                  title="Dropped: fewer than 20 retest observations (D23c)"
                >
                  <code>"{bg}"</code>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Per-Bigram Longitudinal Table */}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-[#111111]">
            <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
              <tr>
                <th className="py-2.5 px-3">Bigram</th>
                <th className="py-2.5 px-3">Assigned Set &amp; Arm</th>
                <th className="py-2.5 px-3">Baseline (Err / Att)</th>
                <th className="py-2.5 px-3">Retest (Err / Att)</th>
                <th className="py-2.5 px-3">Error Shift</th>
                <th className="py-2.5 px-3">Baseline IKI</th>
                <th className="py-2.5 px-3">Retest IKI</th>
                <th className="py-2.5 px-3">IKI Shift</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EAEAEA] tabular-nums">
              {rows.map((r) => {
                const errDelta =
                  r.baselineErrorRate !== null && r.retestErrorRate !== null
                    ? r.retestErrorRate - r.baselineErrorRate
                    : null;
                const ikiDelta =
                  r.baselineMedianIkiMs !== null && r.retestMedianIkiMs !== null
                    ? r.retestMedianIkiMs - r.baselineMedianIkiMs
                    : null;
                return (
                  <tr
                    key={`${r.setLabel}-${r.bigram}`}
                    className={r.dropped ? "opacity-60" : undefined}
                  >
                    <td className="py-2 px-3 font-semibold text-[#111111]">
                      <code>"{r.bigram}"</code>
                      {r.dropped && (
                        <span className="ml-1.5 text-[10px] text-[#8A5A00]">(dropped &lt;20)</span>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      Set {r.setLabel} ({revealed ? r.arm : "Masked"})
                    </td>
                    <td className="py-2 px-3">
                      <code>
                        {r.baselineErrorRate !== null
                          ? `${(r.baselineErrorRate * 100).toFixed(1)}% (${r.baselineErrors}/${r.baselineAttempts})`
                          : "N/A"}
                      </code>
                    </td>
                    <td className="py-2 px-3">
                      <code>
                        {r.retestErrorRate !== null
                          ? `${(r.retestErrorRate * 100).toFixed(1)}% (${r.retestErrors}/${r.retestAttempts})`
                          : "N/A"}
                      </code>
                    </td>
                    <td
                      className={`py-2 px-3 font-medium ${
                        errDelta !== null && errDelta < 0
                          ? "text-[#2B6E3F]"
                          : errDelta !== null && errDelta > 0
                            ? "text-[#9F2F2D]"
                            : "text-[#666560]"
                      }`}
                    >
                      <code>{fmtSignedPp(errDelta, 1)}</code>
                    </td>
                    <td className="py-2 px-3">
                      <code>
                        {r.baselineMedianIkiMs !== null
                          ? `${r.baselineMedianIkiMs.toFixed(0)} ms`
                          : "N/A"}
                      </code>
                    </td>
                    <td className="py-2 px-3">
                      <code>
                        {r.retestMedianIkiMs !== null
                          ? `${r.retestMedianIkiMs.toFixed(0)} ms`
                          : "N/A"}
                      </code>
                    </td>
                    <td
                      className={`py-2 px-3 font-medium ${
                        ikiDelta !== null && ikiDelta < 0
                          ? "text-[#2B6E3F]"
                          : ikiDelta !== null && ikiDelta > 0
                            ? "text-[#9F2F2D]"
                            : "text-[#666560]"
                      }`}
                    >
                      <code>{fmtSignedMs(ikiDelta, 0)}</code>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export interface SystemVerificationProps {
  readonly participantId: string;
  readonly overview: Overview | null;
  readonly checks: ChecksResponse | null;
  readonly revealed: boolean;
  readonly activeArms: readonly string[];
}

export function SystemVerificationSection({
  participantId,
  overview,
  checks,
  revealed,
  activeArms,
}: SystemVerificationProps): React.JSX.Element | null {
  const participantOverhead: readonly SessionOverheadEntry[] = overview
    ? overview.overhead.filter((o) => o.participant_id === participantId)
    : [];
  const totalParticipantEvents = participantOverhead.reduce((acc, r) => acc + r.events, 0);
  const worstHandlerP95 =
    participantOverhead.length > 0
      ? Math.max(...participantOverhead.map((r) => r.handler?.p95 ?? 0))
      : null;
  const medianHandlerP50 =
    participantOverhead.length > 0
      ? participantOverhead.reduce((acc, r) => acc + (r.handler?.p50 ?? 0), 0) /
        participantOverhead.length
      : null;
  const worstDispatchP95 =
    participantOverhead.length > 0
      ? Math.max(...participantOverhead.map((r) => r.dispatch?.p95 ?? 0))
      : null;

  const relevantGenArms: readonly ArmGenerationSummary[] = overview
    ? overview.generation.arms.filter((a) => activeArms.includes(a.arm) && a.drills_count > 0)
    : [];

  if (!checks && participantOverhead.length === 0 && relevantGenArms.length === 0) {
    return null;
  }

  return (
    <section id="cs-engineering" className="typist-card p-6 space-y-5">
      <div>
        <h3 className="text-base font-semibold tracking-tight text-[#111111]">
          §8 · Instrumentation Overhead, Generator Fairness &amp; Data Quality Audit
        </h3>
        <p className="text-xs text-[#666560] mt-1 leading-relaxed">
          Verification that browser capture stayed below the 1.000 ms synchronous handler budget
          (§12.5), drill generators satisfied D30 lexical density bounds, and all 5 SQLite telemetry
          invariants passed.
        </p>
      </div>

      {/* Hardware / Telemetry Metrics + 5 Quality Gates */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 typist-inset space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#111111]">
              Keystroke Capture Overhead (§12.5)
            </span>
            {worstHandlerP95 !== null && (
              <span
                className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                  worstHandlerP95 < 1.0
                    ? "bg-[#EDF3EC] text-[#2B5930]"
                    : "bg-[#FBF3DB] text-[#8A5A00]"
                }`}
              >
                {worstHandlerP95 < 1.0 ? "PASS (< 1.0 ms budget)" : "ABOVE BUDGET"}
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="p-2.5 bg-white rounded border border-[#EAEAEA]">
              <div className="text-[10px] text-[#666560]">Events Audited</div>
              <div className="font-semibold text-[#111111] mt-0.5 tabular-nums">
                <code>
                  {(
                    checks?.checks.missing_keyups.total_events ?? totalParticipantEvents
                  ).toLocaleString()}
                </code>
              </div>
            </div>
            <div className="p-2.5 bg-white rounded border border-[#EAEAEA]">
              <div className="text-[10px] text-[#666560]">Handler p50 / max p95</div>
              <div className="font-semibold text-[#111111] mt-0.5 tabular-nums">
                <code>
                  {medianHandlerP50 !== null && worstHandlerP95 !== null
                    ? `${medianHandlerP50.toFixed(2)} / ${worstHandlerP95.toFixed(2)} ms`
                    : "N/A"}
                </code>
              </div>
            </div>
            <div className="p-2.5 bg-white rounded border border-[#EAEAEA]">
              <div className="text-[10px] text-[#666560]">Dispatch max p95</div>
              <div className="font-semibold text-[#111111] mt-0.5 tabular-nums">
                <code>
                  {worstDispatchP95 !== null ? `${worstDispatchP95.toFixed(2)} ms` : "N/A"}
                </code>
              </div>
            </div>
          </div>
        </div>

        {checks && (
          <div className="p-4 typist-inset space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-[#111111]">
                5-Gate Telemetry Integrity Checks (§12.6)
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                  checks.passed ? "bg-[#EDF3EC] text-[#2B5930]" : "bg-[#FCEBEC] text-[#9F2F2D]"
                }`}
              >
                {checks.passed ? "5 / 5 GATES PASSED" : "CHECK WARNING"}
              </span>
            </div>
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-xs text-[#3D3C38]">
              <li className="flex items-center justify-between bg-white px-2.5 py-1.5 rounded border border-[#EAEAEA]">
                <span>Sequence continuity</span>
                <code>{checks.checks.seq_gaps.count} gaps</code>
              </li>
              <li className="flex items-center justify-between bg-white px-2.5 py-1.5 rounded border border-[#EAEAEA]">
                <span>Dwell bounds [0, 1000 ms]</span>
                <code>
                  {checks.checks.dwell_anomalies.negative_count +
                    checks.checks.dwell_anomalies.over_1000ms_count}{" "}
                  anomalies
                </code>
              </li>
              <li className="flex items-center justify-between bg-white px-2.5 py-1.5 rounded border border-[#EAEAEA]">
                <span>Block completeness</span>
                <code>{checks.checks.short_blocks.count} short</code>
              </li>
              <li className="flex items-center justify-between bg-white px-2.5 py-1.5 rounded border border-[#EAEAEA]">
                <span>Missing key-ups (&lt;=5%)</span>
                <code>{(checks.checks.missing_keyups.missing_share * 100).toFixed(2)}%</code>
              </li>
            </ul>
          </div>
        )}
      </div>

      {/* Generator Calibration Audit */}
      {relevantGenArms.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-[#111111]">
            <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
              <tr>
                <th className="py-2 px-3">Generator Arm</th>
                <th className="py-2 px-3">Drills Accepted</th>
                <th className="py-2 px-3">Acceptance Rate</th>
                <th className="py-2 px-3">Mean Target Density (D30: 10%-40%)</th>
                <th className="py-2 px-3">Mean Word Length</th>
                <th className="py-2 px-3">Real-Word Ratio</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EAEAEA] tabular-nums">
              {relevantGenArms.map((g, i) => (
                <tr key={g.arm}>
                  <td className="py-2 px-3 font-semibold">
                    {revealed ? g.arm : `Masked Generator ${i + 1}`}
                  </td>
                  <td className="py-2 px-3">
                    <code>
                      {g.drills_count} / {g.attempts_count}
                    </code>
                  </td>
                  <td className="py-2 px-3">
                    <code>{fmtPct(g.acceptance_rate, 1)}</code>
                  </td>
                  <td className="py-2 px-3">
                    <code>{fmtPct(g.mean_target_density, 1)}</code>
                  </td>
                  <td className="py-2 px-3">
                    <code>
                      {g.mean_word_length !== null
                        ? `${g.mean_word_length.toFixed(2)} chars`
                        : "N/A"}
                    </code>
                  </td>
                  <td className="py-2 px-3">
                    <code>{fmtPct(g.mean_real_word_ratio, 1)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
