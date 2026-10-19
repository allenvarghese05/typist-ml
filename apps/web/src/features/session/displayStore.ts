import type { KeystrokeRow } from "../../telemetry/types";

/** How one target position should render (design doc 11.3). */
export type CellStatus = "untyped" | "correct" | "error";

/** Where the block is in its lifecycle (D26). */
export type BlockPhase = "active" | "warning" | "abandoned" | "done";

/** Everything a TypingDisplayStore needs; one store per block attempt. */
export interface TypingDisplayStoreOptions {
  /** The block's target text (a to z or space); the store only paints it, never validates it. */
  readonly targetText: string;
  /** Milliseconds of no recorded row before the idle warning (D26). */
  readonly idleWarningMs: number;
  /** Milliseconds of no recorded row before the block is abandoned (D26). */
  readonly idleAbandonMs: number;
  /** Called once when the last position is reached (phase becomes "done"). */
  readonly onComplete?: () => void;
  /** Called once when the abandon timer fires (phase becomes "abandoned"). */
  readonly onAbandon?: () => void;
}

/**
 * The live display state for one block attempt, observing the recorder's row stream (owner answer
 * 2). It is a plain class with no React import (6.1): React reads it through useSyncExternalStore
 * and the snapshots are primitives, so getSnapshot never allocates a fresh reference.
 *
 * It owns three things: the per-position status array and cursor index (painted from each recorded
 * row), the blur "paused" flag, and the D26 idle rule. The idle timers are wall-clock setTimeouts
 * reset only by applyRow (a recorded row), never by blur or focus, so a long blur still abandons
 * (owner answer 10). No statistics, no network, no randomness.
 */
export class TypingDisplayStore {
  /** The block's target text. */
  readonly target: string;
  /** target.length; the cursor is "done" when it reaches this. */
  readonly length: number;
  readonly #idleWarningMs: number;
  readonly #idleAbandonMs: number;
  readonly #onComplete: (() => void) | undefined;
  readonly #onAbandon: (() => void) | undefined;
  readonly #listeners = new Set<() => void>();
  readonly #statuses: CellStatus[];
  #cursorIndex = 0;
  #phase: BlockPhase = "active";
  #paused = false;
  #warningTimer: ReturnType<typeof setTimeout> | null = null;
  #abandonTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(options: TypingDisplayStoreOptions) {
    this.target = options.targetText;
    this.length = options.targetText.length;
    this.#idleWarningMs = options.idleWarningMs;
    this.#idleAbandonMs = options.idleAbandonMs;
    this.#onComplete = options.onComplete;
    this.#onAbandon = options.onAbandon;
    this.#statuses = Array.from({ length: this.length }, () => "untyped" as CellStatus);
  }

  /** Subscribe for useSyncExternalStore. Returns an unsubscribe. Arrow so the reference is stable. */
  subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener);
    return () => {
      this.#listeners.delete(listener);
    };
  };

  /** Current cursor index (0 to length). Arrow for a stable getSnapshot. */
  getCursorIndex = (): number => this.#cursorIndex;

  /** Characters committed so far, for the progress bar. Equals the cursor index. */
  getTypedCount = (): number => this.#cursorIndex;

  /** Current lifecycle phase. Arrow for a stable getSnapshot. */
  getPhase = (): BlockPhase => this.#phase;

  /** True while the window is blurred. Arrow for a stable getSnapshot. */
  isPaused = (): boolean => this.#paused;

  /**
   * One cell's render state as a primitive string: its status, plus "-cursor" when the cursor is
   * on it. A primitive keeps useSyncExternalStore from looping (equal strings are Object.is-equal).
   */
  getCellSnapshot(index: number): string {
    const status = this.#statuses[index] ?? "untyped";
    return index === this.#cursorIndex ? `${status}-cursor` : status;
  }

  /** Begin the idle timers (called when the block becomes active, from the surface effect). */
  start(): void {
    this.#armIdle();
  }

  /**
   * Paint one recorded keystroke row and reset the idle timer. A correct/error row marks its
   * position and advances the cursor; a backspace row clears the position it lands on (11.3: wrong
   * characters are left in place until Backspace) and moves the cursor back. Reaching the last
   * position ends the block. Ignored once abandoned or done.
   */
  applyRow(row: KeystrokeRow): void {
    if (this.#phase === "abandoned" || this.#phase === "done") {
      return;
    }
    switch (row.outcome) {
      case "correct":
        this.#statuses[row.target_index] = "correct";
        this.#cursorIndex = row.target_index + 1;
        break;
      case "error":
        this.#statuses[row.target_index] = "error";
        this.#cursorIndex = row.target_index + 1;
        break;
      case "backspace":
        this.#statuses[row.target_index] = "untyped";
        this.#cursorIndex = row.target_index;
        break;
    }
    if (this.#cursorIndex >= this.length) {
      this.#clearIdle();
      this.#phase = "done";
      this.#emit();
      this.#onComplete?.();
      return;
    }
    this.#armIdle();
    this.#emit();
  }

  /** Window blurred: show paused. Does not touch the idle timers (owner answer 10). */
  pause(): void {
    if (this.#paused) {
      return;
    }
    this.#paused = true;
    this.#emit();
  }

  /** Window focused: clear paused. Does not reset the idle timers. */
  resume(): void {
    if (!this.#paused) {
      return;
    }
    this.#paused = false;
    this.#emit();
  }

  /** Clear timers and drop subscribers (effect cleanup / restart). */
  dispose(): void {
    this.#clearIdle();
    this.#listeners.clear();
  }

  #armIdle(): void {
    this.#clearIdle();
    if (this.#phase === "abandoned" || this.#phase === "done") {
      return;
    }
    if (this.#phase === "warning") {
      this.#phase = "active";
    }
    this.#warningTimer = setTimeout(() => {
      if (this.#phase === "active") {
        this.#phase = "warning";
        this.#emit();
      }
    }, this.#idleWarningMs);
    this.#abandonTimer = setTimeout(() => {
      this.#clearIdle();
      this.#phase = "abandoned";
      this.#emit();
      this.#onAbandon?.();
    }, this.#idleAbandonMs);
  }

  #clearIdle(): void {
    if (this.#warningTimer !== null) {
      clearTimeout(this.#warningTimer);
      this.#warningTimer = null;
    }
    if (this.#abandonTimer !== null) {
      clearTimeout(this.#abandonTimer);
      this.#abandonTimer = null;
    }
  }

  #emit(): void {
    for (const listener of this.#listeners) {
      listener();
    }
  }
}
