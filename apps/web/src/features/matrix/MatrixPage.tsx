import { Fragment, useEffect, useState } from "react";
import { type BigramMatrix, fetchSessionMatrix, type MatrixCell } from "../../api/analysis";

const LETTERS = "abcdefghijklmnopqrstuvwxyz".split("");

/** Which metric the heatmap colours. */
type Metric = "error" | "iki";

interface LoadState {
  readonly status: "loading" | "ok" | "not-found" | "not-completed" | "error";
  readonly matrix?: BigramMatrix;
  readonly message?: string;
}

/** The value a cell contributes to the active metric, or null when the cell has no data. */
function cellValue(cell: MatrixCell | undefined, metric: Metric): number | null {
  if (cell === undefined) {
    return null;
  }
  if (metric === "error") {
    return cell.error_rate;
  }
  return cell.iki_n > 0 ? cell.iki_median_ms : null;
}

/** White->red (error) or white->blue (IKI), scaled to max; empty cells are transparent (A5). */
function colorFor(value: number | null, metric: Metric, max: number): string {
  if (value === null) {
    return "transparent";
  }
  const ratio = max > 0 ? value / max : 0;
  const channel = Math.round(255 * (1 - ratio));
  return metric === "error"
    ? `rgb(255, ${channel}, ${channel})`
    : `rgb(${channel}, ${channel}, 255)`;
}

function cellTitle(bigram: string, cell: MatrixCell | undefined): string {
  if (cell === undefined) {
    return `${bigram}: no data`;
  }
  const iki =
    cell.iki_median_ms === null ? "no timing" : `${cell.iki_median_ms} ms (n=${cell.iki_n})`;
  return `${bigram}: ${cell.errors}/${cell.attempts} errors; IKI ${iki}`;
}

interface BigramHeatmapProps {
  readonly cells: readonly MatrixCell[];
  readonly metric: Metric;
}

/** A 26x26 grid (row = first letter, column = second letter) with a-z axis labels (owner answer 6). */
function BigramHeatmap({ cells, metric }: BigramHeatmapProps): React.JSX.Element {
  const byBigram = new Map(cells.map((cell) => [cell.bigram, cell]));
  const values = LETTERS.flatMap((r) =>
    LETTERS.map((c) => cellValue(byBigram.get(`${r}${c}`), metric)),
  ).filter((value): value is number => value !== null);
  const max = values.length > 0 ? Math.max(...values) : 0;
  return (
    <div
      className="inline-grid gap-px"
      style={{ gridTemplateColumns: `1.5rem repeat(26, 1.25rem)` }}
    >
      <div />
      {LETTERS.map((c) => (
        <div key={`col-${c}`} data-axis-label="col" className="text-center text-xs">
          {c}
        </div>
      ))}
      {LETTERS.map((r) => (
        <Fragment key={`row-${r}`}>
          <div data-axis-label="row" className="text-center text-xs">
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
                className="h-5 w-5 border border-gray-200"
                style={{ backgroundColor: colorFor(value, metric, max) }}
              />
            );
          })}
        </Fragment>
      ))}
    </div>
  );
}

export interface MatrixPageProps {
  /** The session whose matrix to show (from the #/matrix/<id> route). */
  readonly sessionId: string;
  /** Injected for tests (default: global fetch). */
  readonly fetchImpl?: typeof fetch;
}

/** The M1 bigram-matrix page: session-id input, metric toggle, and the heatmap (design doc 15.2). */
export function MatrixPage({ sessionId, fetchImpl }: MatrixPageProps): React.JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [metric, setMetric] = useState<Metric>("error");
  const [draft, setDraft] = useState(sessionId);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetchSessionMatrix(sessionId, fetchImpl).then((result) => {
      if (cancelled) {
        return;
      }
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
  }, [sessionId, fetchImpl]);

  return (
    <section className="mx-auto max-w-5xl px-6 py-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-[#EAEAEA] pb-5">
        <div>
          <h1 className="text-2xl font-semibold text-[#111111]">Bigram matrix</h1>
          <p className="text-xs text-[#666560] mt-1">
            26×26 letter-pair error rate and median inter-key interval heatmap (§15.2).
          </p>
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            window.location.hash = `#/matrix/${encodeURIComponent(draft)}`;
          }}
          className="flex items-center gap-2"
        >
          <label className="flex items-center gap-2 text-xs text-[#666560]">
            <span>Session id</span>
            <input
              className="border border-[#D9D7D0] rounded-lg px-3 py-1.5 text-xs font-mono bg-white text-[#111111] focus:outline-none focus:border-[#111111]"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
          </label>
          <button type="submit" className="typist-btn-primary px-3.5 py-1.5 text-xs">
            Load
          </button>
        </form>
      </div>

      <div className="typist-card p-6 space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div className="inline-flex rounded-lg bg-[#F5F4F0] p-1 border border-[#EAEAEA]">
            <button
              type="button"
              data-active={metric === "error"}
              onClick={() => setMetric("error")}
              className={`px-3 py-1 rounded-md text-xs font-medium typist-fluid ${
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
              className={`px-3 py-1 rounded-md text-xs font-medium typist-fluid ${
                metric === "iki"
                  ? "bg-white text-[#111111] border border-[#EAEAEA]"
                  : "text-[#666560] hover:text-[#111111]"
              }`}
            >
              Median IKI
            </button>
          </div>
        </div>

        {state.status === "loading" && <p className="text-sm text-[#666560]">Loading…</p>}
        {state.status === "not-found" && (
          <p className="text-sm text-[#9F2F2D]">Session not found.</p>
        )}
        {state.status === "not-completed" && (
          <p className="text-sm text-[#8A5A00]">Session is not completed yet.</p>
        )}
        {state.status === "error" && (
          <p className="text-sm text-[#9F2F2D]">Could not load the matrix: {state.message}</p>
        )}
        {state.status === "ok" && state.matrix !== undefined && (
          <div className="overflow-x-auto">
            <BigramHeatmap cells={state.matrix.cells} metric={metric} />
          </div>
        )}
      </div>
    </section>
  );
}
