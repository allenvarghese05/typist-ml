import type { ParticipantResults } from "../../api/analysis";
import { IntervalPlot } from "./IntervalPlot";

export interface OutcomesTabProps {
  readonly results: ParticipantResults | null;
  readonly loadState: {
    readonly status: "loading" | "ok" | "not-done" | "not-found" | "error";
    readonly message?: string;
  };
}

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

export function OutcomesTab({ results, loadState }: OutcomesTabProps): React.JSX.Element {
  if (loadState.status === "loading") {
    return (
      <div className="p-8 text-center text-gray-500 animate-pulse">
        Loading participant study outcomes...
      </div>
    );
  }

  if (loadState.status === "not-done") {
    return (
      <div className="p-4 bg-amber-50 border border-amber-200 rounded text-amber-800 font-medium">
        Outcomes unlock after study completion; current phase has not concluded (
        {loadState.message ?? "participant not done"}).
      </div>
    );
  }

  if (loadState.status === "not-found") {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded text-red-800">
        Participant not found.
      </div>
    );
  }

  if (loadState.status === "error" || !results) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded text-red-800">
        Error loading outcomes: {loadState.message ?? "Unknown error"}
      </div>
    );
  }

  const targetedSets = results.sets.filter((s) => s.arm !== "control");

  return (
    <div className="space-y-8">
      {/* Exploratory Notice */}
      <div className="p-3 bg-[#F6F5F2] border border-[#EAEAEA] rounded-lg text-xs text-[#666560]">
        <span className="font-semibold text-[#111111]">Pre-registration note:</span> Primary
        confirmatory comparisons are each targeted arm vs. the held-out control set. Secondary
        comparisons between active arms are exploratory (§15.1).
      </div>

      {/* Primary Outcomes Section: Error Rates */}
      <div className="typist-card p-5 space-y-4">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-[#111111]">
            Primary Outcome: Error Rate Targeting Effect E(s) = d(s) - d(control)
          </h3>
          <p className="text-xs text-[#666560] mt-1">
            Posterior median difference-in-differences with 95% Jeffreys Beta credible intervals.
            Negative effect indicates error reduction beyond control practice.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-[#111111]">
            <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
              <tr>
                <th className="py-2.5 px-3">Set</th>
                <th className="py-2.5 px-3">Arm</th>
                <th className="py-2.5 px-3">Bigrams</th>
                <th className="py-2.5 px-3">Baseline (95% CI)</th>
                <th className="py-2.5 px-3">Retest (95% CI)</th>
                <th className="py-2.5 px-3">d(s)</th>
                <th className="py-2.5 px-3">E(s)</th>
                <th className="py-2.5 px-3">Posterior Median</th>
                <th className="py-2.5 px-3">95% Credible Interval</th>
                <th className="py-2.5 px-3">P(E &lt; 0)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EAEAEA]">
              {results.sets.map((set) => {
                const isControl = set.arm === "control";
                return (
                  <tr key={set.set_label} className={isControl ? "bg-[#FBFBFA]" : undefined}>
                    <td className="py-2 px-3 font-semibold text-[#111111]">{set.set_label}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          isControl ? "bg-[#F3F2EE] text-[#666560]" : "bg-[#EBF3FA] text-[#1D5A8A]"
                        }`}
                      >
                        {isControl ? "Control Set (Held-out)" : set.arm}
                      </span>
                    </td>
                    <td className="py-2 px-3 tabular-nums">
                      {set.retained_bigrams.length}
                      {set.dropped_bigrams.length > 0 && (
                        <span className="text-[#8A5A00] ml-1">
                          ({set.dropped_bigrams.length} dropped)
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 tabular-nums">
                      <div>{formatPercent(set.baseline_error_rate)}</div>
                      <div className="text-[10px] text-[#9A9992] font-mono">
                        [{formatPercent(set.baseline_beta_ci_lower)},{" "}
                        {formatPercent(set.baseline_beta_ci_upper)}]
                      </div>
                    </td>
                    <td className="py-2 px-3 tabular-nums">
                      <div>{formatPercent(set.retest_error_rate)}</div>
                      <div className="text-[10px] text-[#9A9992] font-mono">
                        [{formatPercent(set.retest_beta_ci_lower)},{" "}
                        {formatPercent(set.retest_beta_ci_upper)}]
                      </div>
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {formatRate(set.error_rate_change)}
                    </td>
                    <td className="py-2 px-3 font-mono font-medium tabular-nums">
                      {isControl ? "—" : formatRate(set.targeting_effect)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {isControl ? "—" : formatRate(set.posterior_effect_median)}
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

        {/* Error Rate Whisker Plots */}
        <div className="mt-4 pt-4 border-t border-[#EAEAEA]">
          <h4 className="text-xs font-medium text-[#666560] mb-2">
            Targeting Effect Forest Plot (Error Rate)
          </h4>
          <div className="space-y-1">
            {targetedSets.map((s) => (
              <IntervalPlot
                key={s.set_label}
                label={`Set ${s.set_label} (${s.arm})`}
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
      </div>

      {/* Key Secondary Outcomes Section: Timing / IKI */}
      <div className="typist-card p-5 space-y-4">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-[#111111]">
            Key Secondary Outcome: Median IKI Targeting Effect F(s) = c(s) - c(control)
          </h3>
          <p className="text-xs text-[#666560] mt-1">
            Difference-in-differences on clean adjacent keystroke intervals (ms) with 95%
            non-parametric bootstrap confidence intervals.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-[#111111]">
            <thead className="bg-[#F6F5F2] text-[#666560] font-medium border-b border-[#EAEAEA]">
              <tr>
                <th className="py-2.5 px-3">Set</th>
                <th className="py-2.5 px-3">Arm</th>
                <th className="py-2.5 px-3">Samples (Base / Retest)</th>
                <th className="py-2.5 px-3">Baseline Median (IQR)</th>
                <th className="py-2.5 px-3">Retest Median (IQR)</th>
                <th className="py-2.5 px-3">c(s)</th>
                <th className="py-2.5 px-3">F(s)</th>
                <th className="py-2.5 px-3">Bootstrap Median</th>
                <th className="py-2.5 px-3">95% Bootstrap CI</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EAEAEA]">
              {results.sets.map((set) => {
                const isControl = set.arm === "control";
                return (
                  <tr key={set.set_label} className={isControl ? "bg-[#FBFBFA]" : undefined}>
                    <td className="py-2 px-3 font-semibold text-[#111111]">{set.set_label}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          isControl ? "bg-[#F3F2EE] text-[#666560]" : "bg-[#EBF3FA] text-[#1D5A8A]"
                        }`}
                      >
                        {isControl ? "Control Set (Held-out)" : set.arm}
                      </span>
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {set.baseline_iki_n} / {set.retest_iki_n}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {set.baseline_iki_median_ms !== null
                        ? `${set.baseline_iki_median_ms.toFixed(1)} ms`
                        : "—"}
                      {set.baseline_iki_iqr_ms !== null && (
                        <span className="text-[10px] text-[#9A9992] ml-1">
                          (IQR {set.baseline_iki_iqr_ms.toFixed(1)})
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {set.retest_iki_median_ms !== null
                        ? `${set.retest_iki_median_ms.toFixed(1)} ms`
                        : "—"}
                      {set.retest_iki_iqr_ms !== null && (
                        <span className="text-[10px] text-[#9A9992] ml-1">
                          (IQR {set.retest_iki_iqr_ms.toFixed(1)})
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {formatMs(set.iki_change_ms)}
                    </td>
                    <td className="py-2 px-3 font-mono font-medium tabular-nums">
                      {isControl ? "—" : formatMs(set.iki_targeting_effect_ms)}
                    </td>
                    <td className="py-2 px-3 font-mono tabular-nums">
                      {isControl ? "—" : formatMs(set.iki_bootstrap_median_ms)}
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

        {/* IKI Whisker Plots */}
        <div className="mt-4 pt-4 border-t border-[#EAEAEA]">
          <h4 className="text-xs font-medium text-[#666560] mb-2">
            Targeting Effect Forest Plot (Median IKI)
          </h4>
          <div className="space-y-1">
            {targetedSets.map((s) => (
              <IntervalPlot
                key={s.set_label}
                label={`Set ${s.set_label} (${s.arm})`}
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
      </div>

      {/* Pre-registered Exclusions Card */}
      <div className="typist-card p-5 space-y-4">
        <h3 className="text-base font-semibold tracking-tight text-[#111111]">
          Pre-registered Exclusions Report (D20, D23)
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Excluded Sessions */}
          <div>
            <h4 className="text-xs font-medium text-[#666560] mb-2">Excluded Sessions</h4>
            {results.exclusions?.excluded_sessions &&
            results.exclusions.excluded_sessions.length > 0 ? (
              <ul className="divide-y divide-[#EAEAEA] text-xs text-[#666560]">
                {results.exclusions.excluded_sessions.map((exc) => (
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
              <p className="text-xs text-[#666560]">No sessions excluded.</p>
            )}
          </div>

          {/* Dropped Bigrams */}
          <div>
            <h4 className="text-xs font-medium text-[#666560] mb-2">
              Dropped Bigrams (&lt;20 Retest Attempts)
            </h4>
            {results.exclusions?.dropped_bigrams &&
            results.exclusions.dropped_bigrams.length > 0 ? (
              <ul className="divide-y divide-[#EAEAEA] text-xs text-[#666560]">
                {results.exclusions.dropped_bigrams.map((drp) => (
                  <li key={drp.bigram} className="py-1.5 flex justify-between">
                    <span className="font-mono font-semibold text-[#111111]">"{drp.bigram}"</span>
                    <span>
                      Set {drp.set_label} ({drp.arm}) —{" "}
                      <span className="text-[#8A5A00] font-medium">
                        {drp.retest_attempts} attempts
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-[#666560]">
                No bigrams dropped (all had ≥20 retest attempts).
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
