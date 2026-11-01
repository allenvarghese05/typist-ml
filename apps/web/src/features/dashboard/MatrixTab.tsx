import { Fragment, useEffect, useState } from "react";
import { type BigramMatrix, fetchSessionMatrix, type MatrixCell } from "../../api/analysis";

const LETTERS = "abcdefghijklmnopqrstuvwxyz".split("");

type Metric = "error" | "iki";

interface LoadState {
  readonly status: "idle" | "loading" | "ok" | "not-found" | "not-completed" | "error";
  readonly matrix?: BigramMatrix;
  readonly message?: string;
}

function cellValue(cell: MatrixCell | undefined, metric: Metric): number | null {
  if (cell === undefined) return null;
  if (metric === "error") return cell.error_rate;
  return cell.iki_n > 0 ? cell.iki_median_ms : null;
}

function colorFor(value: number | null, metric: Metric, max: number): string {
  if (value === null) return "transparent";
  const ratio = max > 0 ? value / max : 0;
  const channel = Math.round(255 * (1 - ratio));
  return metric === "error"
    ? `rgb(255, ${channel}, ${channel})`
    : `rgb(${channel}, ${channel}, 255)`;
}

function cellTitle(bigram: string, cell: MatrixCell | undefined): string {
  if (cell === undefined) return `${bigram}: no data`;
  const iki =
    cell.iki_median_ms === null ? "no timing" : `${cell.iki_median_ms} ms (n=${cell.iki_n})`;
  return `${bigram}: ${cell.errors}/${cell.attempts} errors; IKI ${iki}`;
}

export interface MatrixTabProps {
  readonly sessions: readonly { id: string; phase: string; day_index: number }[];
  readonly fetchImpl?: typeof fetch;
}

export function MatrixTab({ sessions, fetchImpl }: MatrixTabProps): React.JSX.Element {
  const [selectedSessionId, setSelectedSessionId] = useState<string>(() => {
    const first = sessions[0];
    return first ? first.id : "";
  });
  const [metric, setMetric] = useState<Metric>("error");
  const [state, setState] = useState<LoadState>({ status: "idle" });

  // Update selectedSessionId if sessions prop changes and selected is not in list
  useEffect(() => {
    const first = sessions[0];
    if (first && !sessions.some((s) => s.id === selectedSessionId)) {
      setSelectedSessionId(first.id);
    }
  }, [sessions, selectedSessionId]);

  useEffect(() => {
    if (!selectedSessionId) {
      setState({ status: "idle" });
      return;
    }
    let cancelled = false;
    setState({ status: "loading" });
    fetchSessionMatrix(selectedSessionId, fetchImpl).then((result) => {
      if (cancelled) return;
      if (result.status === "ok") {
        setState({ status: "ok", matrix: result.matrix });
      } else if (result.status === "error") {
        setState({ status: "error", message: result.message });
      } else {
        setState({ status: result.status });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [selectedSessionId, fetchImpl]);

  if (sessions.length === 0) {
    return (
      <div className="p-8 text-center bg-gray-50 border border-gray-200 rounded-lg text-gray-500">
        No completed sessions available to display bigram matrix.
      </div>
    );
  }

  const cells = state.matrix?.cells ?? [];
  const byBigram = new Map(cells.map((c) => [c.bigram, c]));
  const values = LETTERS.flatMap((r) =>
    LETTERS.map((c) => cellValue(byBigram.get(`${r}${c}`), metric)),
  ).filter((v): v is number => v !== null);
  const max = values.length > 0 ? Math.max(...values) : 0;

  return (
    <div className="typist-card p-5 space-y-6">
      {/* Controls: Session selector & Metric toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#EAEAEA] pb-4">
        <div className="flex items-center gap-3">
          <label htmlFor="matrix-session-select" className="text-xs font-medium text-[#666560]">
            Session:
          </label>
          <select
            id="matrix-session-select"
            aria-label="Session selector"
            value={selectedSessionId}
            onChange={(e) => setSelectedSessionId(e.target.value)}
            className="text-xs font-mono border border-[#EAEAEA] rounded-lg px-2.5 py-1.5 bg-white text-[#111111] focus:outline-none focus:border-[#111111]"
          >
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                Day {s.day_index} ({s.phase}) — {s.id.slice(0, 8)}...
              </option>
            ))}
          </select>
        </div>

        <div className="inline-flex items-center p-0.5 rounded-lg bg-[#F3F2EE] border border-[#EAEAEA]">
          <button
            type="button"
            data-active={metric === "error"}
            onClick={() => setMetric("error")}
            className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
              metric === "error"
                ? "bg-white text-[#111111] border border-[#EAEAEA]"
                : "text-[#666560] hover:text-[#111111]"
            }`}
          >
            Error rate
          </button>
          <button
            type="button"
            data-active={metric === "iki"}
            onClick={() => setMetric("iki")}
            className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
              metric === "iki"
                ? "bg-white text-[#111111] border border-[#EAEAEA]"
                : "text-[#666560] hover:text-[#111111]"
            }`}
          >
            Median IKI
          </button>
        </div>
      </div>

      {/* Headline session stats if available */}
      {state.status === "ok" && state.matrix && (
        <div className="flex flex-wrap items-center gap-6 text-xs text-[#666560] typist-inset px-3.5 py-2.5 tabular-nums">
          <div>
            <span className="text-[#9A9992]">Phase:</span>{" "}
            <span className="font-semibold uppercase text-[#111111]">{state.matrix.phase}</span>
          </div>
          <div>
            <span className="text-[#9A9992]">WPM:</span>{" "}
            <span className="font-semibold text-[#111111]">
              {state.matrix.wpm?.toFixed(1) ?? "—"}
            </span>
          </div>
          <div>
            <span className="text-[#9A9992]">Accuracy:</span>{" "}
            <span className="font-semibold text-[#111111]">
              {state.matrix.accuracy !== null
                ? `${(state.matrix.accuracy * 100).toFixed(1)}%`
                : "—"}
            </span>
          </div>
          <div>
            <span className="text-[#9A9992]">Recorded Bigrams:</span>{" "}
            <span className="font-semibold text-[#111111]">{cells.length}</span>
          </div>
        </div>
      )}

      {/* State messages */}
      {state.status === "loading" && (
        <div className="p-8 text-center text-gray-500 animate-pulse">Loading matrix cells...</div>
      )}
      {state.status === "not-found" && (
        <div className="p-4 bg-red-50 border border-red-200 rounded text-xs text-red-800">
          Session not found.
        </div>
      )}
      {state.status === "not-completed" && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
          Session is not completed yet.
        </div>
      )}
      {state.status === "error" && (
        <div className="p-4 bg-red-50 border border-red-200 rounded text-xs text-red-800">
          Could not load the matrix: {state.message}
        </div>
      )}

      {/* 26x26 Grid */}
      {state.status === "ok" && (
        <div className="overflow-x-auto pb-2">
          <div
            className="inline-grid gap-px bg-gray-100 p-2 rounded"
            style={{ gridTemplateColumns: `1.5rem repeat(26, 1.25rem)` }}
          >
            <div />
            {LETTERS.map((c) => (
              <div
                key={`col-${c}`}
                data-axis-label="col"
                className="text-center text-[10px] font-mono font-bold text-gray-500"
              >
                {c}
              </div>
            ))}
            {LETTERS.map((r) => (
              <Fragment key={`row-${r}`}>
                <div
                  data-axis-label="row"
                  className="text-center text-[10px] font-mono font-bold text-gray-500 leading-5"
                >
                  {r}
                </div>
                {LETTERS.map((c) => {
                  const bigram = `${r}${c}`;
                  const cell = byBigram.get(bigram);
                  const value = cellValue(cell, metric);
                  return (
                    <div
                      key={bigram}
                      data-cell-bigram={bigram}
                      data-metric={metric}
                      data-value={value === null ? "" : String(value)}
                      data-empty={value === null ? "true" : "false"}
                      title={cellTitle(bigram, cell)}
                      className="h-5 w-5 border border-gray-200 rounded-[1px] hover:border-gray-900 transition-colors"
                      style={{ backgroundColor: colorFor(value, metric, max) }}
                    />
                  );
                })}
              </Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
