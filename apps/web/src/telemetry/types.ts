/**
 * Per-keystroke values produced by TextCursor (design doc 12.3, Figure 5). Field names are the
 * keystroke_events column names (snake_case), the one naming scheme across the TypeScript/Python
 * boundary (T1.2 owner answer 3, T1.3 owner answer 7).
 */

/** keystroke_events.outcome. A string union, not an enum (tsconfig erasableSyntaxOnly). */
export type Outcome = "correct" | "error" | "backspace";

/** What TextCursor.type() reports for a printable key (a to z or space). */
export interface TypedStep {
  /** Position the key was compared with: the cursor index before the key moved it. */
  readonly target_index: number;
  /** target[target_index], a to z or " ". */
  readonly expected_char: string;
  /** "correct" when the key equals expected_char, otherwise "error". */
  readonly outcome: Exclude<Outcome, "backspace">;
  /** True when no earlier printable key was recorded at target_index (12.3). */
  readonly first_attempt: boolean;
}

/** What TextCursor.backspace() reports. */
export interface BackspaceStep {
  /** Post-move cursor position, max(index - 1, 0) (D25). */
  readonly target_index: number;
  readonly expected_char: null;
  readonly outcome: "backspace";
  readonly first_attempt: null;
}

/** Either step: the four cursor-owned fields of one keystroke_events row. */
export type CursorStep = TypedStep | BackspaceStep;

/**
 * One keystroke_events row as the browser produces it (design doc 8.1, 12.1, 12.2; T1.4 owner
 * answers 1 to 8). Field names are the column names. id and block_id are not the recorder's
 * (T1.6 adds block_id); release_to_press_ms is never a row field (T1.2 answer 10a). Every time
 * is in milliseconds, exactly KeyboardEvent.timeStamp minus the block start, never rounded.
 */
export interface KeystrokeRow {
  /** Order within the block, contiguous from 0; one per recorded keydown. */
  readonly seq: number;
  /** KeyboardEvent.key: a to z, " " or "Backspace". */
  readonly key: string;
  /** KeyboardEvent.code (the physical key), stored as given. */
  readonly code: string;
  /** Key-down time relative to the block start. */
  readonly t_down_ms: number;
  /** Null in the row the recorder emits; T1.6 fills it from a KeyUpUpdate (or the server does). */
  readonly t_up_ms: number | null;
  /** t_up_ms minus t_down_ms; null while t_up_ms is null. */
  readonly dwell_ms: number | null;
  /** t_down_ms minus the previous recorded row's t_down_ms (Backspace rows count); null at seq 0. */
  readonly iki_ms: number | null;
  /** From TextCursor (T1.3). */
  readonly target_index: number;
  /** From TextCursor; null for Backspace. */
  readonly expected_char: string | null;
  /** From TextCursor. */
  readonly outcome: Outcome;
  /** From TextCursor; null for Backspace. */
  readonly first_attempt: boolean | null;
  /** True only on the first row recorded after a blur (D24; T1.4 owner answer 6). */
  readonly after_pause: boolean;
  /** Clock at the end of the keydown handler minus clock at its start (T1.4 owner answer 1). */
  readonly handler_ms: number;
  /** Clock at the keydown handler's start minus KeyboardEvent.timeStamp (T1.4 owner answer 1). */
  readonly dispatch_lag_ms: number;
}

/** A key-up paired by code with the row it releases; sent whenever it arrives (T1.4 answer 4). */
export interface KeyUpUpdate {
  /** seq of the row this key-up belongs to. */
  readonly seq: number;
  /** Key-up time relative to the block start. */
  readonly t_up_ms: number;
  /** t_up_ms minus that row's t_down_ms. */
  readonly dwell_ms: number;
}

/**
 * Where KeystrokeRecorder sends its output (implemented by T1.6's EventBuffer). Calls are
 * synchronous, from inside the key handlers, so implementations must be cheap and must not throw.
 */
export interface KeystrokeSink {
  /** A new row, created at keydown, with t_up_ms and dwell_ms null. Never mutated afterwards. */
  onRow(row: KeystrokeRow): void;
  /** The key-up for an earlier row, early or late. */
  onKeyUp(update: KeyUpUpdate): void;
}
