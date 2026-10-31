export interface IntervalPlotProps {
  readonly label: string;
  readonly sublabel?: string;
  readonly estimate: number | null;
  readonly lower: number | null;
  readonly upper: number | null;
  readonly minRange?: number;
  readonly maxRange?: number;
  readonly zeroLine?: boolean;
  readonly unit?: string;
  readonly higherIsBetter?: boolean;
}

/**
 * Pure SVG horizontal whisker / forest plot:
 * Displays point estimate (circle) with interval whiskers [lower, upper] and zero reference line.
 */
export function IntervalPlot({
  label,
  sublabel,
  estimate,
  lower,
  upper,
  minRange = -0.15,
  maxRange = 0.15,
  zeroLine = true,
  unit = "",
  higherIsBetter = false,
}: IntervalPlotProps): React.JSX.Element {
  if (estimate === null || lower === null || upper === null) {
    return (
      <div className="flex items-center justify-between py-1 text-sm text-gray-400">
        <span className="font-medium text-gray-700">{label}</span>
        <span>N/A</span>
      </div>
    );
  }

  const width = 280;
  const height = 36;
  const paddingX = 16;
  const scale = (val: number) => {
    const clamped = Math.max(minRange, Math.min(maxRange, val));
    const ratio = (clamped - minRange) / (maxRange - minRange);
    return paddingX + ratio * (width - 2 * paddingX);
  };

  const xZero = scale(0);
  const xEstimate = scale(estimate);
  const xLower = scale(lower);
  const xUpper = scale(upper);

  // If higherIsBetter is false (error rate & IKI: negative means improvement):
  const isImproved = higherIsBetter ? estimate > 0 : estimate < 0;
  const colorClass = isImproved
    ? "text-emerald-600 stroke-emerald-600 fill-emerald-600"
    : "text-amber-600 stroke-amber-600 fill-amber-600";

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between py-2 border-b border-gray-100 gap-2">
      <div className="w-44 shrink-0">
        <div className="font-medium text-sm text-gray-900">{label}</div>
        {sublabel && <div className="text-xs text-gray-500">{sublabel}</div>}
      </div>
      <div className="flex items-center gap-3">
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`${label} effect: ${estimate.toFixed(3)}${unit} with 95% interval [${lower.toFixed(3)}, ${upper.toFixed(3)}]`}
          className="overflow-visible"
        >
          {zeroLine && (
            <line
              x1={xZero}
              y1={4}
              x2={xZero}
              y2={height - 4}
              stroke="#9ca3af"
              strokeWidth={1.5}
              strokeDasharray="3 3"
            />
          )}
          {/* Horizontal whisker line */}
          <line
            x1={xLower}
            y1={height / 2}
            x2={xUpper}
            y2={height / 2}
            stroke="currentColor"
            strokeWidth={2}
            className={colorClass}
          />
          {/* Whisker caps */}
          <line
            x1={xLower}
            y1={height / 2 - 5}
            x2={xLower}
            y2={height / 2 + 5}
            stroke="currentColor"
            strokeWidth={2}
            className={colorClass}
          />
          <line
            x1={xUpper}
            y1={height / 2 - 5}
            x2={xUpper}
            y2={height / 2 + 5}
            stroke="currentColor"
            strokeWidth={2}
            className={colorClass}
          />
          {/* Estimate point */}
          <circle cx={xEstimate} cy={height / 2} r={4.5} className={colorClass} />
        </svg>
        <div className="text-right text-xs font-mono w-28 shrink-0">
          <span className="font-semibold text-gray-900">
            {estimate > 0 ? `+${estimate.toFixed(3)}` : estimate.toFixed(3)}
            {unit}
          </span>
          <div className="text-gray-500">
            [{lower.toFixed(3)}, {upper.toFixed(3)}]
          </div>
        </div>
      </div>
    </div>
  );
}
