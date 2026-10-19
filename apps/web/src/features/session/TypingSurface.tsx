import {
  memo,
  type ReactElement,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { KeystrokeRecorder } from "../../telemetry/KeystrokeRecorder";
import type { KeystrokeSink } from "../../telemetry/types";
import { TypingDisplayStore } from "./displayStore";
import { IDLE_ABANDON_MS, IDLE_WARNING_MS } from "./sessionConfig";

/**
 * A block lifecycle signal the surface reports to its caller (owner answer 1). The caller's sink
 * is for rows (T1.6's EventBuffer later); these are the block-level events. A restart is observable
 * as abandon(attempt n) then start(attempt n+1); attempt is the owner's flagged future
 * block-identity signal, recorded now, not persisted.
 */
export type BlockLifecycleEvent =
  | { readonly kind: "start"; readonly attempt: number; readonly blockStartMs: number }
  | { readonly kind: "complete"; readonly attempt: number }
  | { readonly kind: "abandon"; readonly attempt: number };

/** Test-only render counters (owner answer 8). Undefined in production. */
export interface RenderProbe {
  readonly onSurfaceRender?: () => void;
  readonly onTextRender?: () => void;
}

/** Props for one block. Text and sink come from the caller (owner answer 3); no API. */
export interface TypingSurfaceProps {
  /** Shown as "Block N"; the arm is never named (3.3). */
  readonly blockLabel: string;
  /** The block's target text, a to z or space (validated by the recorder). */
  readonly targetText: string;
  /** Receives recorded rows and key-ups (collector now, EventBuffer later). */
  readonly sink: KeystrokeSink;
  /** Receives block start/complete/abandon events. */
  readonly onLifecycle?: (event: BlockLifecycleEvent) => void;
  /** Idle warning threshold (default IDLE_WARNING_MS). */
  readonly idleWarningMs?: number;
  /** Idle abandon threshold (default IDLE_ABANDON_MS). */
  readonly idleAbandonMs?: number;
  /** Performance clock for the block-start origin (default () => performance.now()). */
  readonly now?: () => number;
  /** Test-only render probes. */
  readonly probe?: RenderProbe;
}

/** The recorder's recorded set minus Backspace: used for preventDefault and detection. */
const HANDLED_CHAR = /^[a-z ]$/;

/**
 * The typing block screen (design doc 11.3). Attaches the window key/blur/focus listeners, drives
 * one KeystrokeRecorder per attempt, fans rows into the display store and the caller's sink, and
 * renders text/cursor/error-highlight/progress/overlay. It subscribes to nothing per key, so it
 * renders once per block; only changed CharCells re-render (acceptance; 9.2).
 */
export function TypingSurface(props: TypingSurfaceProps): ReactElement {
  props.probe?.onSurfaceRender?.();
  const {
    blockLabel,
    targetText,
    idleWarningMs = IDLE_WARNING_MS,
    idleAbandonMs = IDLE_ABANDON_MS,
    probe,
  } = props;

  const [attempt, setAttempt] = useState(0);

  // Latest callbacks via refs so the store/effect do not depend on their identity.
  const lifecycleRef = useRef(props.onLifecycle);
  lifecycleRef.current = props.onLifecycle;
  const sinkRef = useRef(props.sink);
  sinkRef.current = props.sink;
  const nowRef = useRef(props.now);
  nowRef.current = props.now;

  // One store per (targetText, attempt). Idle timers are armed in the effect, not here, so a
  // discarded useMemo (StrictMode/concurrent) leaks no timer.
  const store = useMemo(
    () =>
      new TypingDisplayStore({
        targetText,
        idleWarningMs,
        idleAbandonMs,
        onComplete: () => lifecycleRef.current?.({ kind: "complete", attempt }),
        onAbandon: () => lifecycleRef.current?.({ kind: "abandon", attempt }),
      }),
    [targetText, attempt, idleWarningMs, idleAbandonMs],
  );

  useEffect(() => {
    const clock = nowRef.current ?? (() => performance.now());
    const blockStartMs = clock();
    const fanOut: KeystrokeSink = {
      onRow: (row) => {
        store.applyRow(row);
        sinkRef.current.onRow(row);
      },
      onKeyUp: (update) => {
        sinkRef.current.onKeyUp(update);
      },
    };
    const recorder = new KeystrokeRecorder({ targetText, blockStartMs, sink: fanOut });
    if (!document.hasFocus()) {
      recorder.onBlur();
      store.pause();
    }
    store.start();
    lifecycleRef.current?.({ kind: "start", attempt, blockStartMs });

    const onKeyDown = (e: KeyboardEvent): void => {
      if (store.getPhase() === "abandoned") {
        return;
      }
      const handled =
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        (e.key === "Backspace" || HANDLED_CHAR.test(e.key));
      if (handled) {
        e.preventDefault();
      }
      recorder.onKeyDown(e);
    };
    const onKeyUp = (e: KeyboardEvent): void => {
      recorder.onKeyUp(e);
    };
    const onBlur = (): void => {
      recorder.onBlur();
      store.pause();
    };
    const onFocus = (): void => {
      recorder.onFocus();
      store.resume();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      store.dispose();
    };
  }, [store, targetText, attempt]);

  const restart = (): void => {
    setAttempt((a) => a + 1);
  };

  return (
    <section aria-label={blockLabel} className="mx-auto max-w-3xl p-8">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">{blockLabel}</h2>
      <TextView store={store} probe={probe} />
      <ProgressBar store={store} />
      <BlockOverlay store={store} onRestart={restart} />
    </section>
  );
}

const TextView = memo(function TextView({
  store,
  probe,
}: {
  readonly store: TypingDisplayStore;
  readonly probe?: RenderProbe;
}): ReactElement {
  probe?.onTextRender?.();
  // Keys are built off the map (not the JSX index arg) so noArrayIndexKey is not triggered.
  const cells = useMemo(
    () => Array.from(store.target, (char, index) => ({ char, index, key: `${index}:${char}` })),
    [store],
  );
  return (
    <p className="mt-4 whitespace-pre-wrap break-words font-mono text-xl leading-relaxed">
      {cells.map((cell) => (
        <CharCell key={cell.key} store={store} index={cell.index} char={cell.char} />
      ))}
    </p>
  );
});

const CharCell = memo(function CharCell({
  store,
  index,
  char,
}: {
  readonly store: TypingDisplayStore;
  readonly index: number;
  readonly char: string;
}): ReactElement {
  const state = useSyncExternalStore(store.subscribe, () => store.getCellSnapshot(index));
  const isCursor = state.endsWith("-cursor");
  const status = isCursor ? state.slice(0, -"-cursor".length) : state;
  const color =
    status === "error" ? "text-red-600" : status === "correct" ? "text-gray-900" : "text-gray-400";
  const cursor = isCursor ? " underline decoration-2" : "";
  return (
    <span className={`${color}${cursor}`} data-cell={index} data-state={state}>
      {char === " " ? "\u00a0" : char}
    </span>
  );
});

function ProgressBar({ store }: { readonly store: TypingDisplayStore }): ReactElement {
  const typed = useSyncExternalStore(store.subscribe, store.getTypedCount);
  const total = store.length;
  const pct = total === 0 ? 0 : (typed / total) * 100;
  return (
    <div
      aria-valuemax={total}
      aria-valuemin={0}
      aria-valuenow={typed}
      className="mt-6 h-2 w-full overflow-hidden rounded bg-gray-200"
      role="progressbar"
    >
      <div className="h-full bg-gray-800" style={{ width: `${pct}%` }} />
    </div>
  );
}

function BlockOverlay({
  store,
  onRestart,
}: {
  readonly store: TypingDisplayStore;
  readonly onRestart: () => void;
}): ReactElement | null {
  const phase = useSyncExternalStore(store.subscribe, store.getPhase);
  const paused = useSyncExternalStore(store.subscribe, store.isPaused);
  if (phase === "done") {
    return (
      <p className="mt-4 text-green-700" role="status">
        Block complete.
      </p>
    );
  }
  if (phase === "abandoned") {
    return (
      <div className="mt-4" role="alert">
        <p className="text-red-700">Block abandoned after too long without typing.</p>
        <button
          className="mt-2 rounded bg-gray-800 px-3 py-1 text-white"
          onClick={onRestart}
          type="button"
        >
          Restart block
        </button>
      </div>
    );
  }
  if (phase === "warning") {
    return (
      <p className="mt-4 text-amber-700" role="alert">
        Still there? Keep typing.
      </p>
    );
  }
  if (paused) {
    return (
      <p className="mt-4 text-gray-600" role="status">
        Paused — the window lost focus.
      </p>
    );
  }
  return null;
}
