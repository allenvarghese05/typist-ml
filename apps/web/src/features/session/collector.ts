import type { KeystrokeRow, KeystrokeSink, KeyUpUpdate } from "../../telemetry/types";
import type { BlockLifecycleEvent } from "./TypingSurface";

/** An in-memory sink standing in for T1.6's EventBuffer (owner answer 7). Keeps everything it sees. */
export interface CollectorSink extends KeystrokeSink {
  readonly rows: KeystrokeRow[];
  readonly keyUps: KeyUpUpdate[];
  readonly lifecycle: BlockLifecycleEvent[];
  /** Pass as TypingSurface's onLifecycle to record block events alongside rows. */
  readonly recordLifecycle: (event: BlockLifecycleEvent) => void;
}

/** Builds a fresh collector. Cheap, never throws, holds no React (callable from a handler). */
export function createCollectorSink(): CollectorSink {
  const rows: KeystrokeRow[] = [];
  const keyUps: KeyUpUpdate[] = [];
  const lifecycle: BlockLifecycleEvent[] = [];
  return {
    rows,
    keyUps,
    lifecycle,
    onRow: (row) => {
      rows.push(row);
    },
    onKeyUp: (update) => {
      keyUps.push(update);
    },
    recordLifecycle: (event) => {
      lifecycle.push(event);
    },
  };
}
