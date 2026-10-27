import type { ChecksResponse } from "../../api/client";

export interface DataChecksProps {
  readonly checksResponse: ChecksResponse | null;
}

export function DataChecks({ checksResponse }: DataChecksProps): React.JSX.Element {
  if (!checksResponse) {
    return (
      <div className="bg-white p-6 border border-gray-200 rounded-lg text-gray-500 text-center">
        No participant selected or data checks unavailable.
      </div>
    );
  }

  const { checks, trend } = checksResponse;

  const setKeys =
    trend.length > 0 && trend[0]
      ? Object.keys(trend[0].per_set_error_rate).sort()
      : ["A", "B", "C", "D"];

  return (
    <div className="flex flex-col gap-6" data-testid="data-checks-panel">
      {/* Overall Banner */}
      <div
        className={`p-4 rounded-lg border font-semibold flex items-center justify-between ${
          checksResponse.passed
            ? "bg-green-50 border-green-200 text-green-800"
            : "bg-red-50 border-red-200 text-red-800"
        }`}
        data-testid="checks-summary-banner"
      >
        <span>
          {checksResponse.passed ? "All 5 Data Checks Passed" : "Data Quality Issues Detected"}
        </span>
        <span className="text-xs uppercase px-2 py-0.5 rounded-full font-bold bg-white/60">
          {checksResponse.passed ? "PASSED" : "FAILED"}
        </span>
      </div>

      {/* 5 Checks Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* 1. Sequence Gaps */}
        <div
          className="p-4 bg-white border border-gray-200 rounded-lg shadow-xs flex flex-col justify-between"
          data-testid="check-card-seq-gaps"
        >
          <div>
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-gray-900 text-sm">Sequence Gaps</span>
              <span
                className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                  checks.seq_gaps.passed ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
                }`}
                data-testid="badge-seq-gaps"
              >
                {checks.seq_gaps.passed ? "PASS" : "FAIL"}
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-2">{checks.seq_gaps.count} gap(s) detected</p>
          </div>
          {checks.seq_gaps.details.length > 0 && (
            <ul className="text-xs text-red-600 bg-red-50 p-2 rounded-sm space-y-1 mt-2">
              {checks.seq_gaps.details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
        </div>

        {/* 2. Dwell Anomalies */}
        <div
          className="p-4 bg-white border border-gray-200 rounded-lg shadow-xs flex flex-col justify-between"
          data-testid="check-card-dwell-anomalies"
        >
          <div>
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-gray-900 text-sm">Dwell Anomalies</span>
              <span
                className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                  checks.dwell_anomalies.passed
                    ? "bg-green-100 text-green-800"
                    : "bg-red-100 text-red-800"
                }`}
                data-testid="badge-dwell-anomalies"
              >
                {checks.dwell_anomalies.passed ? "PASS" : "FAIL"}
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-2">
              {checks.dwell_anomalies.negative_count} negative,{" "}
              {checks.dwell_anomalies.over_1000ms_count} &gt; 1000ms
            </p>
          </div>
          {checks.dwell_anomalies.details.length > 0 && (
            <ul className="text-xs text-red-600 bg-red-50 p-2 rounded-sm space-y-1 mt-2">
              {checks.dwell_anomalies.details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
        </div>

        {/* 3. Short Blocks */}
        <div
          className="p-4 bg-white border border-gray-200 rounded-lg shadow-xs flex flex-col justify-between"
          data-testid="check-card-short-blocks"
        >
          <div>
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-gray-900 text-sm">Short Blocks</span>
              <span
                className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                  checks.short_blocks.passed
                    ? "bg-green-100 text-green-800"
                    : "bg-red-100 text-red-800"
                }`}
                data-testid="badge-short-blocks"
              >
                {checks.short_blocks.passed ? "PASS" : "FAIL"}
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-2">{checks.short_blocks.count} short block(s)</p>
          </div>
          {checks.short_blocks.details.length > 0 && (
            <ul className="text-xs text-red-600 bg-red-50 p-2 rounded-sm space-y-1 mt-2">
              {checks.short_blocks.details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
        </div>

        {/* 4. Missing Keyups */}
        <div
          className="p-4 bg-white border border-gray-200 rounded-lg shadow-xs flex flex-col justify-between"
          data-testid="check-card-missing-keyups"
        >
          <div>
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-gray-900 text-sm">Missing Keyups</span>
              <span
                className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                  checks.missing_keyups.passed
                    ? "bg-green-100 text-green-800"
                    : "bg-red-100 text-red-800"
                }`}
                data-testid="badge-missing-keyups"
              >
                {checks.missing_keyups.passed ? "PASS" : "FAIL"}
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-2">
              {checks.missing_keyups.missing_count}/{checks.missing_keyups.total_events} (
              {(checks.missing_keyups.missing_share * 100).toFixed(2)}%; limit 5%)
            </p>
          </div>
          {checks.missing_keyups.details.length > 0 && (
            <ul className="text-xs text-gray-600 bg-gray-50 p-2 rounded-sm space-y-1 mt-2">
              {checks.missing_keyups.details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
        </div>

        {/* 5. In-Progress Sessions */}
        <div
          className="p-4 bg-white border border-gray-200 rounded-lg shadow-xs flex flex-col justify-between"
          data-testid="check-card-in-progress"
        >
          <div>
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-gray-900 text-sm">In-Progress Sessions</span>
              <span
                className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                  checks.in_progress_sessions.passed
                    ? "bg-green-100 text-green-800"
                    : "bg-red-100 text-red-800"
                }`}
                data-testid="badge-in-progress"
              >
                {checks.in_progress_sessions.passed ? "PASS" : "FAIL"}
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-2">
              {checks.in_progress_sessions.count} lingering session(s)
            </p>
          </div>
          {checks.in_progress_sessions.details.length > 0 && (
            <ul className="text-xs text-red-600 bg-red-50 p-2 rounded-sm space-y-1 mt-2">
              {checks.in_progress_sessions.details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Session Trends Table */}
      <div className="bg-white p-6 border border-gray-200 rounded-lg shadow-xs">
        <h3 className="text-base font-semibold text-gray-900 mb-1">Session Trends</h3>
        <p className="text-xs text-gray-500 mb-4">
          Chronological performance and error rate progression across sets
        </p>

        {trend.length === 0 ? (
          <p className="text-sm text-gray-500">No completed sessions yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-gray-700" data-testid="trends-table">
              <thead className="text-xs uppercase bg-gray-50 text-gray-500 border-b border-gray-200">
                <tr>
                  <th className="py-2.5 px-3">Day</th>
                  <th className="py-2.5 px-3">Phase</th>
                  <th className="py-2.5 px-3">Started</th>
                  <th className="py-2.5 px-3">WPM</th>
                  <th className="py-2.5 px-3">Accuracy</th>
                  {setKeys.map((setLabel) => (
                    <th key={setLabel} className="py-2.5 px-3">
                      Set {setLabel}
                    </th>
                  ))}
                  <th className="py-2.5 px-3 text-right">Heatmap</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {trend.map((s) => (
                  <tr
                    key={s.session_id}
                    className="hover:bg-gray-50"
                    data-testid={`trend-row-${s.session_id}`}
                  >
                    <td className="py-2.5 px-3 font-medium">{s.day_index}</td>
                    <td className="py-2.5 px-3 capitalize">{s.phase}</td>
                    <td className="py-2.5 px-3 text-xs text-gray-500">
                      {new Date(s.started_at).toLocaleDateString()}
                    </td>
                    <td className="py-2.5 px-3">{s.wpm !== null ? s.wpm.toFixed(1) : "-"}</td>
                    <td className="py-2.5 px-3">
                      {s.accuracy !== null ? `${(s.accuracy * 100).toFixed(1)}%` : "-"}
                    </td>
                    {setKeys.map((setLabel) => {
                      const rate = s.per_set_error_rate[setLabel];
                      return (
                        <td key={setLabel} className="py-2.5 px-3">
                          {rate !== undefined && rate !== null
                            ? `${(rate * 100).toFixed(1)}%`
                            : "-"}
                        </td>
                      );
                    })}
                    <td className="py-2.5 px-3 text-right">
                      <a
                        href={`#/matrix/${encodeURIComponent(s.session_id)}`}
                        className="text-xs font-medium text-blue-600 hover:text-blue-800 underline"
                        data-testid={`matrix-link-${s.session_id}`}
                      >
                        View Matrix
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
