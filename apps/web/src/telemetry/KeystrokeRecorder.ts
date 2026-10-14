import { TextCursor } from "./TextCursor";
import type { CursorStep, KeystrokeRow, KeystrokeSink } from "./types";

/**
 * The KeyboardEvent fields the recorder reads (T1.4 owner answer 9). A real KeyboardEvent is
 * assignable; tests pass plain objects. shiftKey is part of the shape but not read: the
 * character decides (T1.4 owner answer 7).
 */
export type KeyInput = Pick<
  KeyboardEvent,
  "key" | "code" | "repeat" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey" | "timeStamp"
>;

/** Everything a KeystrokeRecorder needs; one recorder per block. */
export interface KeystrokeRecorderOptions {
  /** The block's target text; TextCursor rules apply (one or more characters a to z or space). */
  readonly targetText: string;
  /**
   * Block start on the browser's performance clock, the same clock as KeyboardEvent.timeStamp
   * (T1.4 owner answer 3). Every stored time is event.timeStamp minus this value.
   */
  readonly blockStartMs: number;
  /** Receives rows at keydown and key-up updates (T1.6's EventBuffer). */
  readonly sink: KeystrokeSink;
  /**
   * High-resolution clock for handler_ms and dispatch_lag_ms. Defaults to performance.now().
   * Tests inject a fake clock so overhead values are exact.
   */
  readonly now?: () => number;
}

/** A key the cursor's type() accepts: one lowercase letter a to z or a space (D13, 12.1). */
const TYPED_KEY = /^[a-z ]$/;
const BACKSPACE = "Backspace";

/** A recorded keydown still waiting for its key-up. */
interface OpenPress {
  readonly seq: number;
  readonly tDownMs: number;
}

/** KeystrokeRow while it is being built, so handler_ms can be written last. */
type WritableRow = { -readonly [K in keyof KeystrokeRow]: KeystrokeRow[K] };

/**
 * Turns one block's keyboard events into keystroke_events rows (design doc 12.1, 12.2, Figure 5).
 *
 * The caller attaches the window listeners and forwards keydown, keyup, blur and focus; the
 * recorder never touches window or document (T1.4 owner answer 5). A keydown becomes a row only
 * when it is not a repeat, no Ctrl, Meta or Alt is held, the page is not blurred, its key is a to
 * z, space or Backspace (Shift does not matter, uppercase is dropped; owner answer 7), and the
 * TextCursor does not ignore it because the block is done. The row is sent to the sink at once
 * with t_up_ms and dwell_ms null. Its key-up is paired by code with the most recent press of that
 * physical key and sent as a KeyUpUpdate whenever it arrives (owner answers 4 and 8).
 *
 * No statistics, no 2000 ms pause rule, no release-to-press, no randomness.
 */
export class KeystrokeRecorder {
  readonly #cursor: TextCursor;
  readonly #blockStartMs: number;
  readonly #sink: KeystrokeSink;
  readonly #now: () => number;
  /** Open presses by KeyboardEvent.code. */
  readonly #open = new Map<string, OpenPress>();
  /** seq of the next recorded row. */
  #nextSeq = 0;
  /** t_down_ms of the previous recorded row; null before the first row. */
  #lastDownMs: number | null = null;
  /** True between onBlur() and onFocus(); keydowns are dropped. */
  #blurred = false;
  /** True from a blur until the next recorded row takes the after_pause flag. */
  #pausePending = false;

  /**
   * @throws RangeError if `blockStartMs` is not a finite number, or (from TextCursor) if
   *   `targetText` is empty or has a character other than a to z or space.
   */
  constructor(options: KeystrokeRecorderOptions) {
    if (!Number.isFinite(options.blockStartMs)) {
      throw new RangeError(
        `KeystrokeRecorder blockStartMs must be a finite number: ${String(options.blockStartMs)}`,
      );
    }
    this.#cursor = new TextCursor(options.targetText);
    this.#blockStartMs = options.blockStartMs;
    this.#sink = options.sink;
    // An arrow, not performance.now itself: calling the method unbound throws in browsers.
    this.#now = options.now ?? (() => performance.now());
  }

  /** True once the cursor has reached the end of the target; later keys are ignored. */
  isDone(): boolean {
    return this.#cursor.isDone();
  }

  /**
   * Handles one keydown. Records at most one row and sends it to the sink.
   *
   * handler_ms spans from the first statement to just before sink.onRow (cursor call and row
   * creation included); dispatch_lag_ms is the clock at the first statement minus
   * event.timeStamp (owner answer 1). Filtered and ignored keydowns produce nothing.
   */
  onKeyDown(e: KeyInput): void {
    const start = this.#now();
    if (e.repeat) {
      // Auto-repeat of a key that is still held: same press, keep its open entry.
      return;
    }
    // A new press of this physical key: an older press still open has lost its key-up, and the
    // next key-up belongs to this press, recorded or not (owner answer 8).
    this.#open.delete(e.code);
    if (this.#blurred || e.ctrlKey || e.metaKey || e.altKey) {
      return;
    }
    let step: CursorStep | null;
    if (e.key === BACKSPACE) {
      step = this.#cursor.backspace();
    } else if (TYPED_KEY.test(e.key)) {
      step = this.#cursor.type(e.key);
    } else {
      return;
    }
    if (step === null) {
      // The block is done: not recorded (T1.2 answer 9b, T1.3 contract).
      return;
    }
    const tDownMs = e.timeStamp - this.#blockStartMs;
    const seq = this.#nextSeq;
    const row: WritableRow = {
      seq,
      key: e.key,
      code: e.code,
      t_down_ms: tDownMs,
      t_up_ms: null,
      dwell_ms: null,
      iki_ms: this.#lastDownMs === null ? null : tDownMs - this.#lastDownMs,
      target_index: step.target_index,
      expected_char: step.expected_char,
      outcome: step.outcome,
      first_attempt: step.first_attempt,
      after_pause: this.#pausePending,
      handler_ms: 0,
      dispatch_lag_ms: start - e.timeStamp,
    };
    this.#pausePending = false;
    this.#nextSeq = seq + 1;
    this.#lastDownMs = tDownMs;
    this.#open.set(e.code, { seq, tDownMs });
    row.handler_ms = this.#now() - start;
    this.#sink.onRow(row);
  }

  /**
   * Handles one keyup. If its code has an open press, sends that row's key-up time and dwell to
   * the sink. Never filtered and never timed: a release is real whenever it arrives, including
   * after the block is done or while blurred (owner answers 1 and 4).
   */
  onKeyUp(e: KeyInput): void {
    const open = this.#open.get(e.code);
    if (open === undefined) {
      return;
    }
    this.#open.delete(e.code);
    const tUpMs = e.timeStamp - this.#blockStartMs;
    this.#sink.onKeyUp({ seq: open.seq, t_up_ms: tUpMs, dwell_ms: tUpMs - open.tDownMs });
  }

  /** The window lost focus: drop keydowns until onFocus(); flag the next recorded row (D24). */
  onBlur(): void {
    this.#blurred = true;
    this.#pausePending = true;
  }

  /** The window regained focus: keydowns are recorded again. */
  onFocus(): void {
    this.#blurred = false;
  }
}
