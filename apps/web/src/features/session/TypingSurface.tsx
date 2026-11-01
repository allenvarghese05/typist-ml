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
    <section aria-label={blockLabel} className="mx-auto max-w-3xl px-6 py-8 sm:py-10">
      <div className="typist-card p-6 sm:p-10">
        <div className="flex items-center justify-between pb-5 border-b border-[#EAEAEA]">
          <h2 className="text-xs font-medium text-[#666560]">{blockLabel}</h2>
          <ProgressCounter store={store} />
        </div>

        <TextView store={store} probe={probe} />
        <ProgressBar store={store} />

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-[#666560]">
          <div className="flex items-center gap-2">
            <span>Errors stay highlighted until corrected with</span>
            <kbd className="typist-kbd">Backspace</kbd>
          </div>
          <span className="font-mono text-[11px] text-[#8A8883]">Lowercase a–z &amp; space</span>
        </div>

        <BlockOverlay store={store} onRestart={restart} />
      </div>
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
    <p className="mt-7 whitespace-pre-wrap break-words font-mono text-[21px] leading-[1.85] tracking-[-0.01em] select-none">
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
    status === "error"
      ? "text-[#9F2F2D] bg-[#FDEBEB] rounded-[2px]"
      : status === "correct"
        ? "text-[#111111]"
        : "text-[#9B9A95]";
  const cursor = isCursor
    ? " bg-[#111111]/8 text-[#111111] underline decoration-[#111111] decoration-2 underline-offset-4 rounded-[2px]"
    : "";
  return (
    <span className={`${color}${cursor}`} data-cell={index} data-state={state}>
      {char === " " ? "\u00a0" : char}
    </span>
  );
});

function ProgressCounter({ store }: { readonly store: TypingDisplayStore }): ReactElement {
  const typed = useSyncExternalStore(store.subscribe, store.getTypedCount);
  return (
    <span className="font-mono text-xs text-[#666560] tabular-nums">
      {typed} <span className="text-[#8A8883]">/ {store.length} chars</span>
    </span>
  );
}

function ProgressBar({ store }: { readonly store: TypingDisplayStore }): ReactElement {
  const typed = useSyncExternalStore(store.subscribe, store.getTypedCount);
  const total = store.length;
  const pct = total === 0 ? 0 : (typed / total) * 100;
  return (
    <div
      aria-valuemax={total}
      aria-valuemin={0}
      aria-valuenow={typed}
      className="mt-8 h-1.5 w-full overflow-hidden rounded-full bg-[#EFEEE9]"
      role="progressbar"
    >
      <div
        className="h-full bg-[#111111] transition-[width] duration-150 ease-out"
        style={{ width: `${pct}%` }}
      />
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
      <div
        className="mt-6 rounded-lg border border-[#D7E6D5] bg-[#EDF3EC] px-4 py-3 text-sm font-medium text-[#2B5930]"
        role="status"
      >
        Block complete.
      </div>
    );
  }
  if (phase === "abandoned") {
    return (
      <div
        className="mt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-lg border border-[#F5D0D2] bg-[#FDEBEB] px-4 py-3"
        role="alert"
      >
        <p className="text-sm font-medium text-[#9F2F2D]">
          Block abandoned after too long without typing.
        </p>
        <button
          className="typist-btn-primary px-3.5 py-1.5 text-xs shrink-0"
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
      <p
        className="mt-6 rounded-lg border border-[#EFE0B4] bg-[#FBF3DB] px-4 py-2.5 text-sm font-medium text-[#8A5A00]"
        role="alert"
      >
        Still there? Keep typing.
      </p>
    );
  }
  if (paused) {
    return (
      <p
        className="mt-6 rounded-lg border border-[#E4E2DC] bg-[#F5F4F0] px-4 py-2.5 text-sm text-[#4A4945]"
        role="status"
      >
        Paused — the window lost focus. Click anywhere in the window to resume.
      </p>
    );
  }
  return null;
}
