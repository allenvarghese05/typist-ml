import type { Percentiles, SessionOverheadEntry } from "../../api/analysis";

export interface OverheadTabProps {
  readonly overhead: readonly SessionOverheadEntry[] | null;
}

function formatPercentiles(p: Percentiles | null): string {
  if (p === null) return "— / — / —";
  return `${p.p50.toFixed(3)} / ${p.p95.toFixed(3)} / ${p.p99.toFixed(3)}`;
}

export function OverheadTab({ overhead }: OverheadTabProps): React.JSX.Element {
  if (!overhead || overhead.length === 0) {
    return (
      <div className="p-8 text-center bg-gray-50 border border-gray-200 rounded-lg text-gray-500">
        No overhead latency records found.
      </div>
    );
  }

  const allRow = overhead.find((r) => r.session_id === "all");
  const p95Handler = allRow?.handler?.p95 ?? null;
  const passesTarget = p95Handler !== null ? p95Handler < 1.0 : true;

  return (
    <div className="space-y-6">
      {/* Engineering Target Validation Banner */}
      <div
        className={`p-4 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
          passesTarget ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"
        }`}
      >
        <div className="flex items-center gap-3">
          <span
            className={`px-2.5 py-1 rounded text-xs font-bold uppercase tracking-wider ${
              passesTarget ? "bg-emerald-600 text-white" : "bg-amber-600 text-white"
            }`}
          >
            {passesTarget ? "PASS" : "WARN"}
          </span>
          <div>
            <div
              className={`text-sm font-semibold ${
                passesTarget ? "text-emerald-900" : "text-amber-900"
              }`}
            >
              Handler Latency Budget (Target: p95 &lt; 1.0 ms)
            </div>
            <div
              className={`text-xs mt-0.5 ${passesTarget ? "text-emerald-700" : "text-amber-700"}`}
            >
              {p95Handler !== null
                ? `Measured pooled handler p95 is ${p95Handler.toFixed(3)} ms (§12.5).`
                : "No telemetry events recorded yet."}
            </div>
          </div>
        </div>

        <div className="text-right text-xs font-mono">
          <span className="text-gray-500">Target: </span>
          <span className="font-semibold text-gray-900">&lt; 1.000 ms</span>
        </div>
      </div>

      {/* Latency Table Card */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 space-y-4">
        <div>
          <h3 className="text-base font-semibold text-gray-900">
            Keystroke Telemetry Overhead Percentiles
          </h3>
          <p className="text-xs text-gray-500">
            Inclusive quantiles (p50 / p95 / p99 in milliseconds) for synchronous handler execution
            and async dispatch lag (§14.1, T1.10).
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-gray-700">
            <thead className="bg-gray-50 text-gray-700 uppercase font-semibold border-b border-gray-200">
              <tr>
                <th className="py-2.5 px-3">Session</th>
                <th className="py-2.5 px-3">Participant</th>
                <th className="py-2.5 px-3">Events</th>
                <th className="py-2.5 px-3">Handler (p50 / p95 / p99 ms)</th>
                <th className="py-2.5 px-3">Dispatch Lag (p50 / p95 / p99 ms)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 font-mono">
              {overhead.map((row) => {
                const isAll = row.session_id === "all";
                return (
                  <tr
                    key={`${row.session_id}-${row.participant_id}`}
                    className={
                      isAll
                        ? "bg-blue-50/70 font-semibold text-blue-950 border-t-2 border-blue-200"
                        : "hover:bg-gray-50/50 text-gray-800"
                    }
                  >
                    <td className="py-2 px-3 font-sans">
                      {isAll ? (
                        <span className="font-bold uppercase tracking-wider text-xs text-blue-800">
                          Pooled (All Sessions)
                        </span>
                      ) : (
                        <span title={row.session_id}>{row.session_id.slice(0, 8)}...</span>
                      )}
                    </td>
                    <td className="py-2 px-3 font-sans">
                      {isAll ? "—" : row.participant_id.slice(0, 8) + "..."}
                    </td>
                    <td className="py-2 px-3">{row.events.toLocaleString()}</td>
                    <td className="py-2 px-3">{formatPercentiles(row.handler)}</td>
                    <td className="py-2 px-3">{formatPercentiles(row.dispatch)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
