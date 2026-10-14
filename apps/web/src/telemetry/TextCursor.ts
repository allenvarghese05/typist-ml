import type { BackspaceStep, TypedStep } from "./types";

/** One key the cursor accepts through type(): a lowercase letter a to z or a space (D13, 12.1). */
const TYPED_CHAR = /^[a-z ]$/;
/** A block's target text: one or more characters, each a to z or space (D13). */
const TARGET_TEXT = /^[a-z ]+$/;

/**
 * Aligns keystrokes with one block's target text by position (design doc 12.3, Figure 5).
 *
 * A printable key is compared with target[index], reported as correct or error, and the index
 * moves forward one position either way; there is no word-based realignment (T1.2 answer 9c).
 * Backspace moves the index back one position, never below 0, and reports the position it lands
 * on (D25). The first printable key ever recorded at a position is its first attempt; retyping
 * after a Backspace is not, whether or not the erased key was correct.
 *
 * The block is done when the index reaches target.length, whatever errors remain (T1.2 answer
 * 9a). After that every key, Backspace included, is ignored and returns null, so a wrong last
 * character stays a first-attempt error (T1.2 answer 9b, T1.3 owner answer 2).
 *
 * The cursor holds no display state and computes no statistics (T1.3 owner answers 4 and 5).
 */
export class TextCursor {
  /** The block's target text. */
  readonly target: string;
  /** Position the next printable key is compared with, from 0 to target.length. */
  #index = 0;
  /** #attempted[i] is true once a printable key has been recorded at position i. Never cleared. */
  readonly #attempted: boolean[];

  /**
   * @param target The block's target text.
   * @throws RangeError if `target` is empty or has a character other than a to z or space.
   */
  constructor(target: string) {
    if (!TARGET_TEXT.test(target)) {
      throw new RangeError(
        `TextCursor target must be one or more characters a to z or space: ${JSON.stringify(target)}`,
      );
    }
    this.target = target;
    this.#attempted = Array.from({ length: target.length }, () => false);
  }

  /** Position the next printable key is compared with; only type() and backspace() move it. */
  get index(): number {
    return this.#index;
  }

  /** True when the index has reached the end of the target, regardless of errors left on screen. */
  isDone(): boolean {
    return this.#index === this.target.length;
  }

  /**
   * Records one printable key at the current index and moves the index forward by one.
   *
   * @param char The typed character (KeyboardEvent.key): exactly one of a to z or " ".
   * @returns The four row fields, or null when the block is already done (the key is ignored and
   *   must not be recorded).
   * @throws RangeError if `char` is not exactly one character a to z or space. Checked before the
   *   done check, so an invalid key throws even after the block is done.
   */
  type(char: string): TypedStep | null {
    if (!TYPED_CHAR.test(char)) {
      throw new RangeError(
        `TextCursor.type expects one character a to z or space: ${JSON.stringify(char)}`,
      );
    }
    if (this.isDone()) {
      return null;
    }
    const index = this.#index;
    const expected = this.target.charAt(index);
    const firstAttempt = this.#attempted[index] !== true;
    this.#attempted[index] = true;
    this.#index = index + 1;
    return {
      target_index: index,
      expected_char: expected,
      outcome: char === expected ? "correct" : "error",
      first_attempt: firstAttempt,
    };
  }

  /**
   * Moves the index back one position (not below 0). Never changes first-attempt state.
   *
   * @returns The row fields with target_index = the post-move index (D25; 0 for a Backspace at
   *   index 0, which is still a row), or null when the block is already done (ignored, not
   *   recorded).
   */
  backspace(): BackspaceStep | null {
    if (this.isDone()) {
      return null;
    }
    this.#index = Math.max(this.#index - 1, 0);
    return {
      target_index: this.#index,
      expected_char: null,
      outcome: "backspace",
      first_attempt: null,
    };
  }
}
