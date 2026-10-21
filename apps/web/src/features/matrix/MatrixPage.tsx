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
    <section className="space-y-4 p-6">
      <h1 className="text-xl font-semibold">Bigram matrix</h1>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          window.location.hash = `#/matrix/${encodeURIComponent(draft)}`;
        }}
        className="flex gap-2"
      >
        <label className="flex items-center gap-2">
          <span>Session id</span>
          <input
            className="border px-2 py-1"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        <button type="submit" className="border px-3 py-1">
          Load
        </button>
      </form>
      <div className="flex gap-2">
        <button
          type="button"
          data-active={metric === "error"}
          onClick={() => setMetric("error")}
          className="border px-3 py-1"
        >
          Error rate
        </button>
        <button
          type="button"
          data-active={metric === "iki"}
          onClick={() => setMetric("iki")}
          className="border px-3 py-1"
        >
          Median IKI
        </button>
      </div>
      {state.status === "loading" && <p>Loading…</p>}
      {state.status === "not-found" && <p>Session not found.</p>}
      {state.status === "not-completed" && <p>Session is not completed yet.</p>}
      {state.status === "error" && <p>Could not load the matrix: {state.message}</p>}
      {state.status === "ok" && state.matrix !== undefined && (
        <BigramHeatmap cells={state.matrix.cells} metric={metric} />
      )}
    </section>
  );
}
