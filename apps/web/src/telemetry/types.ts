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
