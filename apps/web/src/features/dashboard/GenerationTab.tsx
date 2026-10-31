import type { GenerationOverview } from "../../api/analysis";

export interface GenerationTabProps {
  readonly generation: GenerationOverview | null;
}

export function GenerationTab({ generation }: GenerationTabProps): React.JSX.Element {
  if (!generation) {
    return (
      <div className="p-8 text-center bg-gray-50 border border-gray-200 rounded-lg text-gray-500">
        No generation audit data available.
      </div>
    );
  }

  const llmArm = generation.arms.find((a) => a.arm === "llm");

  return (
    <div className="space-y-6">
      {/* Overview Stat Badges */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
          <div className="text-xs text-gray-500 font-medium">Total Drills Generated</div>
          <div className="text-2xl font-bold text-gray-900 mt-1 font-mono">
            {generation.total_drills}
          </div>
        </div>
        <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
          <div className="text-xs text-gray-500 font-medium">Total Generation Attempts</div>
          <div className="text-2xl font-bold text-gray-900 mt-1 font-mono">
            {generation.total_attempts}
          </div>
        </div>
        <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
          <div className="text-xs text-gray-500 font-medium">Density Calibration (D30)</div>
          <div className="mt-1 flex items-center gap-2">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">
              Valid Window [0.10, 0.40]
            </span>
          </div>
        </div>
      </div>

      {/* Per-Arm Audit Table */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold text-gray-900">Drill Generation by Arm</h3>
            <p className="text-xs text-gray-500">
              Fairness metrics, acceptance rates, and model efficiency across experimental arms.
            </p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-gray-700">
            <thead className="bg-gray-50 text-gray-700 uppercase font-semibold border-b border-gray-200">
              <tr>
                <th className="py-2.5 px-3">Arm</th>
                <th className="py-2.5 px-3">Drills</th>
                <th className="py-2.5 px-3">Attempts</th>
                <th className="py-2.5 px-3">Acceptance Rate</th>
                <th className="py-2.5 px-3">Attempts / Drill</th>
                <th className="py-2.5 px-3">Target Density</th>
                <th className="py-2.5 px-3">Mean Word Length</th>
                <th className="py-2.5 px-3">Real-Word Ratio</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 font-mono">
              {generation.arms.map((arm) => {
                const isTargeted = arm.arm !== "control";
                const isCalibrated =
                  arm.mean_target_density !== null &&
                  arm.mean_target_density >= 0.1 &&
                  arm.mean_target_density <= 0.4;

                return (
                  <tr key={arm.arm} className="hover:bg-gray-50/50">
                    <td className="py-2.5 px-3 font-semibold text-gray-900 font-sans">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          arm.arm === "control"
                            ? "bg-purple-100 text-purple-800"
                            : "bg-blue-100 text-blue-800"
                        }`}
                      >
                        {arm.arm}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">{arm.drills_count}</td>
                    <td className="py-2.5 px-3">{arm.attempts_count}</td>
                    <td className="py-2.5 px-3">
                      {arm.acceptance_rate !== null
                        ? `${(arm.acceptance_rate * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                    <td className="py-2.5 px-3">
                      {arm.attempts_per_drill !== null ? arm.attempts_per_drill.toFixed(2) : "—"}
                    </td>
                    <td className="py-2.5 px-3 font-sans">
                      {arm.mean_target_density !== null ? (
                        <div className="flex items-center gap-1.5 font-mono">
                          <span>{(arm.mean_target_density * 100).toFixed(1)}%</span>
                          {isTargeted && (
                            <span
                              className={`text-[10px] px-1.5 py-0.2 rounded font-sans font-medium ${
                                isCalibrated
                                  ? "bg-emerald-50 text-emerald-700"
                                  : "bg-amber-50 text-amber-700"
                              }`}
                            >
                              {isCalibrated ? "Calibrated" : "Uncalibrated"}
                            </span>
                          )}
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2.5 px-3">
                      {arm.mean_word_length !== null ? arm.mean_word_length.toFixed(2) : "—"}
                    </td>
                    <td className="py-2.5 px-3">
                      {arm.mean_real_word_ratio !== null
                        ? `${(arm.mean_real_word_ratio * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* LLM Operational Performance Card */}
      {llmArm && (
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 space-y-3">
          <h3 className="text-base font-semibold text-gray-900">
            LLM Operational Performance (MLX Runtime)
          </h3>
          <p className="text-xs text-gray-500">
            Measured generation speed, latency, and memory footprint on Apple Silicon (D09, §13.5).
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
            <div className="p-3 bg-gray-50 border border-gray-100 rounded">
              <div className="text-xs text-gray-500">Tokens per Second</div>
              <div className="text-lg font-bold font-mono text-gray-900 mt-1">
                {llmArm.tokens_per_sec !== null ? `${llmArm.tokens_per_sec.toFixed(1)} tok/s` : "—"}
              </div>
            </div>
            <div className="p-3 bg-gray-50 border border-gray-100 rounded">
              <div className="text-xs text-gray-500">Mean Generation Latency</div>
              <div className="text-lg font-bold font-mono text-gray-900 mt-1">
                {llmArm.mean_gen_ms !== null ? `${llmArm.mean_gen_ms.toFixed(1)} ms` : "—"}
              </div>
            </div>
            <div className="p-3 bg-gray-50 border border-gray-100 rounded">
              <div className="text-xs text-gray-500">Peak Memory</div>
              <div className="text-lg font-bold font-mono text-gray-900 mt-1">
                {llmArm.peak_memory_mb !== null ? `${llmArm.peak_memory_mb.toFixed(1)} MB` : "—"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
