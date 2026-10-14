import { describe, expect, it } from "vitest";
import { type KeyInput, KeystrokeRecorder } from "../KeystrokeRecorder";
import type { KeystrokeRow, KeystrokeSink, KeyUpUpdate } from "../types";

// T1.4 acceptance: "Tests with synthetic KeyboardEvents cover repeat, modifiers, overlapping
// keys". Events are plain objects typed as KeyInput, the subset of KeyboardEvent the recorder
// reads (owner answer 9); no DOM environment. The golden fixture is not used (T1.2 answer 1).
// Times are whole numbers or halves so every subtraction is exact in floating point.

/** Block start on the fake performance clock. Event timestamps are START + the test's time. */
const START = 1000;
/** Fake dispatch lag: during a keydown the harness clock reads START + at + LAG. */
const LAG = 1.5;

type Modifiers = Pick<KeyInput, "repeat" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey">;

function keyEvent(
  key: string,
  code: string,
  timeStamp: number,
  modifiers: Partial<Modifiers> = {},
): KeyInput {
  return {
    key,
    code,
    timeStamp,
    repeat: false,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    ...modifiers,
  };
}

interface Collector {
  readonly sink: KeystrokeSink;
  readonly rows: KeystrokeRow[];
  readonly keyUps: KeyUpUpdate[];
}

function collector(): Collector {
  const rows: KeystrokeRow[] = [];
  const keyUps: KeyUpUpdate[] = [];
  return {
    rows,
    keyUps,
    sink: {
      onRow: (row) => {
        rows.push({ ...row });
      },
      onKeyUp: (update) => {
        keyUps.push({ ...update });
      },
    },
  };
}

interface Harness extends Collector {
  readonly recorder: KeystrokeRecorder;
  /** Keydown at START + at; the clock reads START + at + LAG for the whole handler. */
  down(key: string, code: string, at: number, modifiers?: Partial<Modifiers>): void;
  /** Keyup at START + at. */
  up(key: string, code: string, at: number, modifiers?: Partial<Modifiers>): void;
}

/** A recorder with block start START and a clock that makes handler_ms 0, dispatch_lag_ms LAG. */
function setup(targetText: string): Harness {
  let clock = 0;
  const output = collector();
  const recorder = new KeystrokeRecorder({
    targetText,
    blockStartMs: START,
    sink: output.sink,
    now: () => clock,
  });
  return {
    ...output,
    recorder,
    down(key, code, at, modifiers) {
      clock = START + at + LAG;
      recorder.onKeyDown(keyEvent(key, code, START + at, modifiers));
    },
    up(key, code, at, modifiers) {
      recorder.onKeyUp(keyEvent(key, code, START + at, modifiers));
    },
  };
}

function pick<K extends keyof KeystrokeRow>(
  rows: readonly KeystrokeRow[],
  field: K,
): Array<KeystrokeRow[K]> {
  return rows.map((row) => row[field]);
}

describe("KeystrokeRecorder rows and timing", () => {
  it("records a typed key as a row at keydown with times relative to block start", () => {
    const h = setup("ab");
    h.down("a", "KeyA", 1851);
    expect(h.rows).toStrictEqual([
      {
        seq: 0,
        key: "a",
        code: "KeyA",
        t_down_ms: 1851,
        t_up_ms: null,
        dwell_ms: null,
        iki_ms: null,
        target_index: 0,
        expected_char: "a",
        outcome: "correct",
        first_attempt: true,
        after_pause: false,
        handler_ms: 0,
        dispatch_lag_ms: 1.5,
      },
    ]);
    expect(h.keyUps).toStrictEqual([]);
  });

  it("reports the key-up as an update with dwell, without changing the row", () => {
    const h = setup("ab");
    h.down("a", "KeyA", 1851);
    h.up("a", "KeyA", 1931);
    expect(h.keyUps).toStrictEqual([{ seq: 0, t_up_ms: 1931, dwell_ms: 80 }]);
    expect(h.rows).toHaveLength(1);
    expect(h.rows[0]?.t_up_ms).toBeNull();
    expect(h.rows[0]?.dwell_ms).toBeNull();
  });

  it("computes iki from the previous recorded row, Backspace rows included", () => {
    const h = setup("abc");
    h.down("a", "KeyA", 100);
    h.up("a", "KeyA", 150);
    h.down("Backspace", "Backspace", 300);
    h.up("Backspace", "Backspace", 340);
    h.down("a", "KeyA", 450);
    h.up("a", "KeyA", 500);
    h.down("x", "KeyX", 600);
    expect(pick(h.rows, "seq")).toStrictEqual([0, 1, 2, 3]);
    expect(pick(h.rows, "key")).toStrictEqual(["a", "Backspace", "a", "x"]);
    expect(pick(h.rows, "code")).toStrictEqual(["KeyA", "Backspace", "KeyA", "KeyX"]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 200, 150, 150]);
    expect(pick(h.rows, "target_index")).toStrictEqual([0, 0, 0, 1]);
    expect(pick(h.rows, "expected_char")).toStrictEqual(["a", null, "a", "b"]);
    expect(pick(h.rows, "outcome")).toStrictEqual(["correct", "backspace", "correct", "error"]);
    expect(pick(h.rows, "first_attempt")).toStrictEqual([true, null, false, true]);
    expect(h.rows[1]).toStrictEqual({
      seq: 1,
      key: "Backspace",
      code: "Backspace",
      t_down_ms: 300,
      t_up_ms: null,
      dwell_ms: null,
      iki_ms: 200,
      target_index: 0,
      expected_char: null,
      outcome: "backspace",
      first_attempt: null,
      after_pause: false,
      handler_ms: 0,
      dispatch_lag_ms: 1.5,
    });
    expect(h.keyUps).toStrictEqual([
      { seq: 0, t_up_ms: 150, dwell_ms: 50 },
      { seq: 1, t_up_ms: 340, dwell_ms: 40 },
      { seq: 2, t_up_ms: 500, dwell_ms: 50 },
    ]);
  });

  it("records a Backspace at index 0 as seq 0 and uses it as the next key's iki anchor", () => {
    const h = setup("ab");
    h.down("Backspace", "Backspace", 1027);
    h.down("a", "KeyA", 1851);
    expect(pick(h.rows, "seq")).toStrictEqual([0, 1]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 824]);
    expect(pick(h.rows, "target_index")).toStrictEqual([0, 0]);
    expect(pick(h.rows, "outcome")).toStrictEqual(["backspace", "correct"]);
    expect(pick(h.rows, "first_attempt")).toStrictEqual([null, true]);
  });

  it("keeps times exactly as timeStamp minus block start, without rounding", () => {
    const output = collector();
    const recorder = new KeystrokeRecorder({
      targetText: "ab",
      blockStartMs: 0.1,
      sink: output.sink,
      now: () => 0.3,
    });
    recorder.onKeyDown(keyEvent("a", "KeyA", 0.3));
    recorder.onKeyUp(keyEvent("a", "KeyA", 0.7));
    expect(0.3 - 0.1).not.toBe(0.2);
    expect(output.rows[0]?.t_down_ms).toBe(0.3 - 0.1);
    expect(output.rows[0]?.dispatch_lag_ms).toBe(0);
    expect(output.keyUps).toStrictEqual([
      { seq: 0, t_up_ms: 0.7 - 0.1, dwell_ms: 0.7 - 0.1 - (0.3 - 0.1) },
    ]);
  });
});

describe("KeystrokeRecorder filters: repeat and modifiers", () => {
  it("drops auto-repeat keydowns: one row, one key-up, dwell over the whole hold", () => {
    const h = setup("ab");
    h.down("a", "KeyA", 100);
    h.down("a", "KeyA", 600, { repeat: true });
    h.down("a", "KeyA", 633, { repeat: true });
    h.down("a", "KeyA", 666, { repeat: true });
    h.up("a", "KeyA", 900);
    h.down("b", "KeyB", 1000);
    expect(pick(h.rows, "seq")).toStrictEqual([0, 1]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 900]);
    expect(h.keyUps).toStrictEqual([{ seq: 0, t_up_ms: 900, dwell_ms: 800 }]);
  });

  it("drops a held Backspace's repeats, so it erases one character", () => {
    const h = setup("abc");
    h.down("a", "KeyA", 100);
    h.up("a", "KeyA", 150);
    h.down("b", "KeyB", 200);
    h.up("b", "KeyB", 250);
    h.down("Backspace", "Backspace", 300);
    h.down("Backspace", "Backspace", 800, { repeat: true });
    h.down("Backspace", "Backspace", 833, { repeat: true });
    h.up("Backspace", "Backspace", 900);
    h.down("b", "KeyB", 1000);
    expect(pick(h.rows, "outcome")).toStrictEqual(["correct", "correct", "backspace", "correct"]);
    expect(pick(h.rows, "target_index")).toStrictEqual([0, 1, 1, 1]);
    expect(pick(h.rows, "first_attempt")).toStrictEqual([true, true, null, false]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 100, 100, 700]);
    expect(h.keyUps).toStrictEqual([
      { seq: 0, t_up_ms: 150, dwell_ms: 50 },
      { seq: 1, t_up_ms: 250, dwell_ms: 50 },
      { seq: 2, t_up_ms: 900, dwell_ms: 600 },
    ]);
    expect(h.recorder.isDone()).toBe(false);
  });

  it("ignores modifier-only keys and their key-ups", () => {
    const h = setup("ab");
    const modifierKeys: ReadonlyArray<readonly [string, string, Partial<Modifiers>]> = [
      ["Shift", "ShiftLeft", { shiftKey: true }],
      ["Control", "ControlLeft", { ctrlKey: true }],
      ["Alt", "AltLeft", { altKey: true }],
      ["Meta", "MetaLeft", { metaKey: true }],
      ["CapsLock", "CapsLock", {}],
      ["Fn", "Fn", {}],
    ];
    for (const [i, [key, code, modifiers]] of modifierKeys.entries()) {
      h.down(key, code, 10 + 10 * i, modifiers);
      h.up(key, code, 15 + 10 * i);
    }
    h.down("a", "KeyA", 100);
    expect(pick(h.rows, "seq")).toStrictEqual([0]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null]);
    expect(h.keyUps).toStrictEqual([]);
  });

  it("drops every key while Ctrl, Meta or Alt is held, space and Backspace included", () => {
    const h = setup("ab");
    const chords: ReadonlyArray<readonly [string, string, Partial<Modifiers>]> = [
      ["a", "KeyA", { ctrlKey: true }],
      ["a", "KeyA", { metaKey: true }],
      ["å", "KeyA", { altKey: true }],
      [" ", "Space", { ctrlKey: true }],
      ["Backspace", "Backspace", { altKey: true }],
      ["Backspace", "Backspace", { metaKey: true }],
      ["a", "KeyA", { ctrlKey: true, shiftKey: true }],
    ];
    for (const [i, [key, code, modifiers]] of chords.entries()) {
      h.down(key, code, 100 + 10 * i, modifiers);
      // The key-up arrives after the modifier was released (brief edge case 4).
      h.up(key, code, 105 + 10 * i);
    }
    expect(h.rows).toStrictEqual([]);
    expect(h.keyUps).toStrictEqual([]);
    expect(h.recorder.isDone()).toBe(false);
    h.down("a", "KeyA", 500);
    expect(pick(h.rows, "seq")).toStrictEqual([0]);
    expect(pick(h.rows, "target_index")).toStrictEqual([0]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null]);
  });

  it("accepts space and Backspace with Shift held and drops uppercase letters", () => {
    const h = setup("a b");
    h.down("A", "KeyA", 100, { shiftKey: true });
    h.up("A", "KeyA", 150, { shiftKey: true });
    h.down("a", "KeyA", 200);
    h.up("a", "KeyA", 250);
    h.down(" ", "Space", 300, { shiftKey: true });
    h.up(" ", "Space", 350);
    h.down("Backspace", "Backspace", 400, { shiftKey: true });
    h.up("Backspace", "Backspace", 450);
    h.down("B", "KeyB", 500, { shiftKey: true });
    // Caps Lock on: uppercase without Shift is dropped too.
    h.down("B", "KeyB", 600);
    expect(pick(h.rows, "key")).toStrictEqual(["a", " ", "Backspace"]);
    expect(pick(h.rows, "outcome")).toStrictEqual(["correct", "correct", "backspace"]);
    expect(pick(h.rows, "target_index")).toStrictEqual([0, 1, 1]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 100, 100]);
    expect(h.keyUps).toStrictEqual([
      { seq: 0, t_up_ms: 250, dwell_ms: 50 },
      { seq: 1, t_up_ms: 350, dwell_ms: 50 },
      { seq: 2, t_up_ms: 450, dwell_ms: 50 },
    ]);
  });

  it("drops keys outside a to z, space and Backspace without throwing", () => {
    const h = setup("ab");
    const others: ReadonlyArray<readonly [string, string]> = [
      [".", "Period"],
      [",", "Comma"],
      ["1", "Digit1"],
      ["Enter", "Enter"],
      ["Tab", "Tab"],
      ["Escape", "Escape"],
      ["ArrowLeft", "ArrowLeft"],
      ["Delete", "Delete"],
      ["Unidentified", ""],
      ["Dead", "BracketLeft"],
      ["Process", "KeyA"],
      ["é", "KeyE"],
      ["", ""],
      ["ab", "KeyA"],
    ];
    for (const [i, [key, code]] of others.entries()) {
      expect(() => h.down(key, code, 10 + i)).not.toThrow();
      h.up(key, code, 30 + i);
    }
    expect(h.rows).toStrictEqual([]);
    h.down("a", "KeyA", 500);
    expect(pick(h.rows, "seq")).toStrictEqual([0]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null]);
    expect(h.keyUps).toStrictEqual([]);
  });
});

describe("KeystrokeRecorder overlapping keys: pairing by code", () => {
  it("pairs key-ups by code under rollover", () => {
    const h = setup("th");
    h.down("t", "KeyT", 2675);
    h.down("h", "KeyH", 2765);
    h.up("t", "KeyT", 2795);
    h.up("h", "KeyH", 2850);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 90]);
    expect(h.keyUps).toStrictEqual([
      { seq: 0, t_up_ms: 2795, dwell_ms: 120 },
      { seq: 1, t_up_ms: 2850, dwell_ms: 85 },
    ]);
  });

  it("pairs nested key-ups that arrive in reverse order", () => {
    const h = setup("er");
    h.down("e", "KeyE", 15930.5);
    h.down("r", "KeyR", 15990.5);
    h.up("r", "KeyR", 16040.5);
    h.up("e", "KeyE", 16090.5);
    expect(pick(h.rows, "t_down_ms")).toStrictEqual([15930.5, 15990.5]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 60]);
    expect(h.keyUps).toStrictEqual([
      { seq: 1, t_up_ms: 16040.5, dwell_ms: 50 },
      { seq: 0, t_up_ms: 16090.5, dwell_ms: 160 },
    ]);
  });

  it("pairs by code, not by key, when the key-up reports a different key", () => {
    const h = setup("ab");
    h.down("a", "KeyA", 100);
    h.up("A", "KeyA", 180, { shiftKey: true });
    expect(h.keyUps).toStrictEqual([{ seq: 0, t_up_ms: 180, dwell_ms: 80 }]);
  });

  it("leaves a lost key-up's row unreleased and pairs the next key-up with the newest press", () => {
    const h = setup("nn");
    h.down("n", "KeyN", 100);
    h.down("n", "KeyN", 400);
    h.up("n", "KeyN", 470);
    expect(pick(h.rows, "seq")).toStrictEqual([0, 1]);
    expect(h.keyUps).toStrictEqual([{ seq: 1, t_up_ms: 470, dwell_ms: 70 }]);
  });

  it("lets a filtered press of the same key take its key-up, so no false dwell", () => {
    const h = setup("ab");
    h.down("a", "KeyA", 100);
    h.down("Control", "ControlLeft", 290, { ctrlKey: true });
    h.down("a", "KeyA", 300, { ctrlKey: true });
    h.up("Control", "ControlLeft", 340);
    h.up("a", "KeyA", 350);
    expect(pick(h.rows, "seq")).toStrictEqual([0]);
    expect(h.keyUps).toStrictEqual([]);
  });

  it("ignores key-ups with no open press, including a duplicate key-up", () => {
    const h = setup("ab");
    h.up("b", "KeyB", 50);
    h.down("a", "KeyA", 100);
    h.up("a", "KeyA", 150);
    h.up("a", "KeyA", 160);
    expect(h.keyUps).toStrictEqual([{ seq: 0, t_up_ms: 150, dwell_ms: 50 }]);
  });

  it("reports late key-ups whenever they arrive, after the block is done too", () => {
    const h = setup("abc");
    h.down("a", "KeyA", 100);
    h.down("b", "KeyB", 300);
    h.up("b", "KeyB", 350);
    h.down("c", "KeyC", 400);
    expect(h.recorder.isDone()).toBe(true);
    h.up("a", "KeyA", 2600);
    expect(h.keyUps).toStrictEqual([
      { seq: 1, t_up_ms: 350, dwell_ms: 50 },
      { seq: 0, t_up_ms: 2600, dwell_ms: 2500 },
    ]);
  });
});

describe("KeystrokeRecorder blur, focus and after_pause", () => {
  it("flags only the first recorded row after a blur", () => {
    const h = setup("abc");
    h.down("a", "KeyA", 100);
    h.up("a", "KeyA", 150);
    h.recorder.onBlur();
    h.recorder.onFocus();
    h.down("b", "KeyB", 5000);
    h.up("b", "KeyB", 5050);
    h.down("c", "KeyC", 5100);
    expect(pick(h.rows, "after_pause")).toStrictEqual([false, true, false]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 4900, 100]);
  });

  it("drops keydowns between blur and focus", () => {
    const h = setup("abc");
    h.down("a", "KeyA", 100);
    h.recorder.onBlur();
    h.down("b", "KeyB", 200);
    expect(h.rows).toHaveLength(1);
    h.recorder.onFocus();
    h.down("b", "KeyB", 300);
    h.up("b", "KeyB", 350);
    expect(pick(h.rows, "seq")).toStrictEqual([0, 1]);
    expect(pick(h.rows, "after_pause")).toStrictEqual([false, true]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 200]);
    expect(pick(h.rows, "target_index")).toStrictEqual([0, 1]);
    expect(pick(h.rows, "first_attempt")).toStrictEqual([true, true]);
    expect(h.keyUps).toStrictEqual([{ seq: 1, t_up_ms: 350, dwell_ms: 50 }]);
  });

  it("flags a Backspace when it is the first key after the pause, and not the next key", () => {
    const h = setup("abc");
    h.down("a", "KeyA", 100);
    h.down("b", "KeyB", 200);
    h.recorder.onBlur();
    h.recorder.onFocus();
    h.down("Backspace", "Backspace", 3000);
    h.down("b", "KeyB", 3100);
    expect(pick(h.rows, "after_pause")).toStrictEqual([false, false, true, false]);
    expect(pick(h.rows, "outcome")).toStrictEqual(["correct", "correct", "backspace", "correct"]);
    expect(pick(h.rows, "target_index")).toStrictEqual([0, 1, 1, 1]);
  });

  it("keeps the flag until a row is actually recorded", () => {
    const h = setup("abc");
    h.down("a", "KeyA", 100);
    h.recorder.onBlur();
    h.recorder.onFocus();
    h.down("Meta", "MetaLeft", 3000, { metaKey: true });
    h.down("a", "KeyA", 3010, { repeat: true });
    h.down("Shift", "ShiftLeft", 3020, { shiftKey: true });
    h.down("B", "KeyB", 3030, { shiftKey: true });
    h.down("b", "KeyB", 3040, { metaKey: true });
    h.down("b", "KeyB", 3100);
    expect(pick(h.rows, "seq")).toStrictEqual([0, 1]);
    expect(pick(h.rows, "after_pause")).toStrictEqual([false, true]);
    expect(pick(h.rows, "iki_ms")).toStrictEqual([null, 3000]);
  });

  it("sets one flag for several blurs, on seq 0 when no key came before", () => {
    const h = setup("abc");
    h.recorder.onBlur();
    h.recorder.onFocus();
    h.recorder.onBlur();
    h.recorder.onFocus();
    h.down("a", "KeyA", 100);
    h.down("b", "KeyB", 200);
    expect(pick(h.rows, "after_pause")).toStrictEqual([true, false]);
  });

  it("still pairs key-ups that arrive while blurred or after focus returns", () => {
    const h = setup("abc");
    h.down("a", "KeyA", 100);
    h.recorder.onBlur();
    h.up("a", "KeyA", 300);
    h.down("b", "KeyB", 400);
    h.recorder.onFocus();
    h.up("b", "KeyB", 450);
    h.down("b", "KeyB", 500);
    h.recorder.onBlur();
    h.recorder.onFocus();
    h.up("b", "KeyB", 2000);
    expect(pick(h.rows, "seq")).toStrictEqual([0, 1]);
    expect(h.keyUps).toStrictEqual([
      { seq: 0, t_up_ms: 300, dwell_ms: 200 },
      { seq: 1, t_up_ms: 2000, dwell_ms: 1500 },
    ]);
  });
});

describe("KeystrokeRecorder after the block is done", () => {
  it("records no row for keys after isDone but still pairs the last key's key-up", () => {
    const h = setup("ab");
    expect(h.recorder.isDone()).toBe(false);
    h.down("a", "KeyA", 100);
    h.down("b", "KeyB", 200);
    expect(h.recorder.isDone()).toBe(true);
    h.down("x", "KeyX", 300);
    h.down("Backspace", "Backspace", 400);
    h.up("x", "KeyX", 380);
    h.up("Backspace", "Backspace", 420);
    h.up("b", "KeyB", 450);
    expect(pick(h.rows, "seq")).toStrictEqual([0, 1]);
    expect(h.keyUps).toStrictEqual([{ seq: 1, t_up_ms: 450, dwell_ms: 250 }]);
    expect(h.recorder.isDone()).toBe(true);
  });
});

describe("KeystrokeRecorder overhead fields", () => {
  it("reads the clock twice per recorded keydown, once per filtered keydown, never on keyup", () => {
    const ticks = [1001.25, 1001.75, 1500, 2003, 2003.25];
    const output = collector();
    const recorder = new KeystrokeRecorder({
      targetText: "ab",
      blockStartMs: 0,
      sink: output.sink,
      now: () => {
        const tick = ticks.shift();
        if (tick === undefined) {
          throw new Error("clock read more often than expected");
        }
        return tick;
      },
    });
    recorder.onKeyDown(keyEvent("a", "KeyA", 1000));
    recorder.onKeyUp(keyEvent("a", "KeyA", 1080));
    recorder.onKeyDown(keyEvent("Shift", "ShiftLeft", 1400, { shiftKey: true }));
    recorder.onKeyDown(keyEvent("b", "KeyB", 2000));
    expect(ticks).toHaveLength(0);
    expect(pick(output.rows, "t_down_ms")).toStrictEqual([1000, 2000]);
    expect(pick(output.rows, "handler_ms")).toStrictEqual([0.5, 0.25]);
    expect(pick(output.rows, "dispatch_lag_ms")).toStrictEqual([1.25, 3]);
    expect(output.keyUps).toStrictEqual([{ seq: 0, t_up_ms: 1080, dwell_ms: 80 }]);
  });

  it("uses performance.now() when no clock is given", () => {
    const output = collector();
    const recorder = new KeystrokeRecorder({ targetText: "a", blockStartMs: 0, sink: output.sink });
    recorder.onKeyDown(keyEvent("a", "KeyA", performance.now()));
    const row = output.rows[0];
    expect(row).toBeDefined();
    expect(Number.isFinite(row?.handler_ms)).toBe(true);
    expect(row?.handler_ms).toBeGreaterThanOrEqual(0);
    expect(Number.isFinite(row?.dispatch_lag_ms)).toBe(true);
    expect(row?.dispatch_lag_ms).toBeGreaterThanOrEqual(0);
  });
});

describe("KeystrokeRecorder construction", () => {
  it("rejects a block start that is not a finite number", () => {
    const { sink } = collector();
    for (const blockStartMs of [Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => new KeystrokeRecorder({ targetText: "ab", blockStartMs, sink })).toThrow(
        RangeError,
      );
    }
  });

  it("rejects a target text that TextCursor rejects", () => {
    const { sink } = collector();
    expect(() => new KeystrokeRecorder({ targetText: "The", blockStartMs: 0, sink })).toThrow(
      RangeError,
    );
  });
});
