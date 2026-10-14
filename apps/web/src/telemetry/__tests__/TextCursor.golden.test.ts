import { describe, expect, it } from "vitest";
import goldenText from "../../../../../services/api/tests/fixtures/golden_session.json?raw";
import { TextCursor } from "../TextCursor";
import type { CursorStep, Outcome } from "../types";

// T1.3 acceptance: "All fixture outcomes match". Replays every keystroke row of the golden
// fixture through one TextCursor and compares the four cursor-owned fields with exact equality
// (T1.2 owner answers 2, 4, 13b). The fixture is read in place from services/api as text through
// Vite's ?raw import (typed by vite/client); it is never copied (T1.2 answer 20). Nothing
// session-level and no bigram stats are checked here (T1.3 owner answer 4; CLAUDE.md).

const ROW_COUNT = 89;
// Row 88's note: "Index 64 < 65, so isDone is false."
const FINAL_INDEX = 64;

interface GoldenRow {
  readonly seq: number;
  readonly key: string;
  readonly target_index: number;
  readonly expected_char: string | null;
  readonly outcome: Outcome;
  readonly first_attempt: boolean | null;
}

interface Golden {
  readonly targetText: string;
  readonly rows: readonly GoldenRow[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isOutcome(value: unknown): value is Outcome {
  return value === "correct" || value === "error" || value === "backspace";
}

/** Narrows one fixture row to the fields the replay reads. Checks types only, never values. */
function parseRow(value: unknown, position: number): GoldenRow {
  if (!isRecord(value)) {
    throw new Error(`golden fixture: keystrokes[${position}] is not an object`);
  }
  const { seq, key, target_index, expected_char, outcome, first_attempt } = value;
  if (
    typeof seq !== "number" ||
    typeof key !== "string" ||
    typeof target_index !== "number" ||
    !(typeof expected_char === "string" || expected_char === null) ||
    !isOutcome(outcome) ||
    !(typeof first_attempt === "boolean" || first_attempt === null)
  ) {
    throw new Error(`golden fixture: keystrokes[${position}] has an unexpected field type`);
  }
  return { seq, key, target_index, expected_char, outcome, first_attempt };
}

/** Parses the fixture text into the target text and the keystroke rows, in file order. */
function parseGolden(text: string): Golden {
  const root: unknown = JSON.parse(text);
  if (!isRecord(root)) {
    throw new Error("golden fixture: the root is not an object");
  }
  const session = root.session;
  const targetText = isRecord(session) ? session.target_text : undefined;
  const keystrokes = root.keystrokes;
  if (typeof targetText !== "string" || !Array.isArray(keystrokes)) {
    throw new Error("golden fixture: session.target_text or keystrokes is missing");
  }
  const rawRows: readonly unknown[] = keystrokes;
  return { targetText, rows: rawRows.map((row, position) => parseRow(row, position)) };
}

const golden = parseGolden(goldenText);

/** Replays every row through a fresh cursor: "Backspace" rows call backspace(), others type(key). */
function replay(): { cursor: TextCursor; steps: Array<CursorStep | null> } {
  const cursor = new TextCursor(golden.targetText);
  const steps = golden.rows.map((row) =>
    row.key === "Backspace" ? cursor.backspace() : cursor.type(row.key),
  );
  return { cursor, steps };
}

describe("TextCursor against the golden fixture", () => {
  it("reads all 89 rows in seq order", () => {
    expect(golden.rows).toHaveLength(ROW_COUNT);
    expect(golden.rows.map((row) => row.seq)).toStrictEqual(
      Array.from({ length: ROW_COUNT }, (_, position) => position),
    );
  });

  it("reproduces target_index, expected_char, outcome and first_attempt on every row", () => {
    const { steps } = replay();
    const expected = golden.rows.map((row) => ({
      target_index: row.target_index,
      expected_char: row.expected_char,
      outcome: row.outcome,
      first_attempt: row.first_attempt,
    }));
    expect(steps).toStrictEqual(expected);
  });

  it("ends at index 64 with the block unfinished", () => {
    const { cursor } = replay();
    expect(cursor.index).toBe(FINAL_INDEX);
    expect(cursor.isDone()).toBe(false);
  });
});
