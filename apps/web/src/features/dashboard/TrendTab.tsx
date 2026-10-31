import type { SessionTrendEntry } from "../../api/analysis";

export interface TrendTabProps {
  readonly trend: readonly SessionTrendEntry[];
  readonly loading: boolean;
}

export function TrendTab({ trend, loading }: TrendTabProps): React.JSX.Element {
  if (loading) {
    return (
      <div className="p-8 text-center text-gray-500 animate-pulse">
        Loading session progression trend...
      </div>
    );
  }

  if (trend.length === 0) {
    return (
      <div className="p-8 text-center bg-gray-50 border border-gray-200 rounded-lg text-gray-500">
        No completed sessions for this participant yet.
      </div>
    );
  }

  // Determine all set labels (e.g. A, B, C, D) across all entries
  const setLabels = Array.from(
    new Set(trend.flatMap((s) => Object.keys(s.per_set_error_rate))),
  ).sort();

  // If no sets are found yet, fallback to standard A-D
  const displayedSets = setLabels.length > 0 ? setLabels : ["A", "B", "C", "D"];

  // SVG Chart Dimensions
  const width = 640;
  const height = 220;
  const padLeft = 45;
  const padRight = 45;
  const padTop = 25;
  const padBottom = 35;

  const validWpms = trend.map((s) => s.wpm ?? 0);
  const maxWpm = Math.max(60, Math.ceil((Math.max(...validWpms, 0) + 10) / 10) * 10);

  const scaleX = (index: number) => {
    if (trend.length <= 1) return (padLeft + width - padRight) / 2;
    return padLeft + (index / (trend.length - 1)) * (width - padLeft - padRight);
  };

  const scaleWpmY = (wpm: number | null) => {
    const val = wpm ?? 0;
    return height - padBottom - (val / maxWpm) * (height - padTop - padBottom);
  };

  const scaleAccY = (acc: number | null) => {
    const val = acc ?? 0; // 0.0 to 1.0
    return height - padBottom - val * (height - padTop - padBottom);
  };

  const wpmPoints = trend
    .map((s, idx) => (s.wpm !== null ? `${scaleX(idx)},${scaleWpmY(s.wpm)}` : null))
    .filter((pt): pt is string => pt !== null)
    .join(" ");

  const accPoints = trend
    .map((s, idx) => (s.accuracy !== null ? `${scaleX(idx)},${scaleAccY(s.accuracy)}` : null))
    .filter((pt): pt is string => pt !== null)
    .join(" ");

  return (
    <div className="space-y-6">
      {/* Progression Chart Card */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold text-gray-900">
              Session Performance Trajectory
            </h3>
            <p className="text-xs text-gray-500">
              Chronological WPM (left axis) and Accuracy (right axis) progression across study days.
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-full bg-blue-600 inline-block" />
              <span className="text-gray-700 font-medium">WPM</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-full bg-emerald-600 inline-block" />
              <span className="text-gray-700 font-medium">Accuracy</span>
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full max-w-2xl h-auto overflow-visible"
            role="img"
            aria-label="Performance trajectory line chart"
          >
            {/* Grid lines */}
            {[0, 0.25, 0.5, 0.75, 1.0].map((ratio) => {
              const y = height - padBottom - ratio * (height - padTop - padBottom);
              const wpmVal = Math.round(ratio * maxWpm);
              const accVal = Math.round(ratio * 100);
              return (
                <g key={ratio}>
                  <line
                    x1={padLeft}
                    y1={y}
                    x2={width - padRight}
                    y2={y}
                    stroke="#f3f4f6"
                    strokeWidth={1}
                  />
                  <text
                    x={padLeft - 8}
                    y={y + 3}
                    textAnchor="end"
                    className="text-[10px] fill-gray-400 font-mono"
                  >
                    {wpmVal}
                  </text>
                  <text
                    x={width - padRight + 8}
                    y={y + 3}
                    textAnchor="start"
                    className="text-[10px] fill-gray-400 font-mono"
                  >
                    {accVal}%
                  </text>
                </g>
              );
            })}

            {/* WPM Line */}
            {wpmPoints && (
              <polyline
                fill="none"
                stroke="#2563eb"
                strokeWidth={2.5}
                points={wpmPoints}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}

            {/* Accuracy Line */}
            {accPoints && (
              <polyline
                fill="none"
                stroke="#059669"
                strokeWidth={2.5}
                points={accPoints}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}

            {/* Data Points */}
            {trend.map((s, idx) => {
              const x = scaleX(idx);
              const yWpm = scaleWpmY(s.wpm);
              const yAcc = scaleAccY(s.accuracy);
              return (
                <g key={s.session_id}>
                  {s.wpm !== null && (
                    <circle
                      cx={x}
                      cy={yWpm}
                      r={3.5}
                      className="fill-blue-600 stroke-white stroke-2"
                    />
                  )}
                  {s.accuracy !== null && (
                    <circle
                      cx={x}
                      cy={yAcc}
                      r={3.5}
                      className="fill-emerald-600 stroke-white stroke-2"
                    />
                  )}
                  <text
                    x={x}
                    y={height - 12}
                    textAnchor="middle"
                    className="text-[10px] fill-gray-500 font-mono"
                  >
                    D{s.day_index}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* Session Progression Table */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-5 space-y-4">
        <h3 className="text-base font-semibold text-gray-900">Completed Sessions Log</h3>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-gray-700">
            <thead className="bg-gray-50 text-gray-700 uppercase font-semibold border-b border-gray-200">
              <tr>
                <th className="py-2.5 px-3">Day</th>
                <th className="py-2.5 px-3">Phase</th>
                <th className="py-2.5 px-3">Session ID</th>
                <th className="py-2.5 px-3">Started At</th>
                <th className="py-2.5 px-3">WPM</th>
                <th className="py-2.5 px-3">Accuracy</th>
                {displayedSets.map((lbl) => (
                  <th key={lbl} className="py-2.5 px-3">
                    Set {lbl} Error Rate
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 font-mono">
              {trend.map((s) => (
                <tr key={s.session_id} className="hover:bg-gray-50/50">
                  <td className="py-2 px-3 font-semibold text-gray-900">Day {s.day_index}</td>
                  <td className="py-2 px-3">
                    <span className="inline-block px-1.5 py-0.5 rounded text-[10px] uppercase font-bold bg-gray-100 text-gray-700">
                      {s.phase}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-gray-500" title={s.session_id}>
                    {s.session_id.slice(0, 8)}...
                  </td>
                  <td className="py-2 px-3 text-gray-600 font-sans">
                    {s.started_at.slice(0, 16).replace("T", " ")}
                  </td>
                  <td className="py-2 px-3 font-semibold text-gray-900">
                    {s.wpm !== null ? s.wpm.toFixed(1) : "—"}
                  </td>
                  <td className="py-2 px-3 font-semibold text-gray-900">
                    {s.accuracy !== null ? `${(s.accuracy * 100).toFixed(1)}%` : "—"}
                  </td>
                  {displayedSets.map((lbl) => {
                    const rate = s.per_set_error_rate[lbl];
                    return (
                      <td key={lbl} className="py-2 px-3">
                        {rate !== undefined && rate !== null ? `${(rate * 100).toFixed(1)}%` : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
