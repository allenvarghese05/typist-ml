import { describe, expect, it } from "vitest";
import { TextCursor } from "../TextCursor";

// Hand-written sequences for behaviour the golden fixture cannot show (T1.2 amendment F7) and for
// the throw rules (T1.3 owner answer 3). Every test builds its own cursor.

describe("TextCursor alignment", () => {
  it("starts at index 0 and is not done", () => {
    const cursor = new TextCursor("ab");
    expect(cursor.target).toBe("ab");
    expect(cursor.index).toBe(0);
    expect(cursor.isDone()).toBe(false);
  });

  it("records a correct first attempt and moves forward", () => {
    const cursor = new TextCursor("ab");
    expect(cursor.type("a")).toStrictEqual({
      target_index: 0,
      expected_char: "a",
      outcome: "correct",
      first_attempt: true,
    });
    expect(cursor.index).toBe(1);
  });

  it("records an error and still moves forward one position", () => {
    const cursor = new TextCursor("ab");
    expect(cursor.type("x")).toStrictEqual({
      target_index: 0,
      expected_char: "a",
      outcome: "error",
      first_attempt: true,
    });
    expect(cursor.type("b")).toStrictEqual({
      target_index: 1,
      expected_char: "b",
      outcome: "correct",
      first_attempt: true,
    });
    expect(cursor.index).toBe(2);
  });

  it("treats a space for a letter and a letter for a space as plain errors", () => {
    const cursor = new TextCursor("a bc");
    expect(cursor.type(" ")).toStrictEqual({
      target_index: 0,
      expected_char: "a",
      outcome: "error",
      first_attempt: true,
    });
    expect(cursor.type("x")).toStrictEqual({
      target_index: 1,
      expected_char: " ",
      outcome: "error",
      first_attempt: true,
    });
    expect(cursor.index).toBe(2);
  });
});

describe("TextCursor backspace", () => {
  it("records a Backspace at index 0 as a no-op row that leaves position 0 unattempted", () => {
    const cursor = new TextCursor("ab");
    const atZero = {
      target_index: 0,
      expected_char: null,
      outcome: "backspace",
      first_attempt: null,
    };
    expect(cursor.backspace()).toStrictEqual(atZero);
    expect(cursor.backspace()).toStrictEqual(atZero);
    expect(cursor.index).toBe(0);
    expect(cursor.type("a")).toStrictEqual({
      target_index: 0,
      expected_char: "a",
      outcome: "correct",
      first_attempt: true,
    });
  });

  it("reports the post-move index (D25)", () => {
    const cursor = new TextCursor("abc");
    cursor.type("a");
    cursor.type("b");
    expect(cursor.backspace()).toStrictEqual({
      target_index: 1,
      expected_char: null,
      outcome: "backspace",
      first_attempt: null,
    });
    expect(cursor.index).toBe(1);
    expect(cursor.backspace()?.target_index).toBe(0);
    expect(cursor.index).toBe(0);
  });

  it("makes a retype not a first attempt, even when the erased key was correct", () => {
    const cursor = new TextCursor("ab");
    expect(cursor.type("a")?.first_attempt).toBe(true);
    cursor.backspace();
    expect(cursor.type("a")).toStrictEqual({
      target_index: 0,
      expected_char: "a",
      outcome: "correct",
      first_attempt: false,
    });
    expect(cursor.type("b")?.first_attempt).toBe(true);
  });

  it("erases correct characters across a space; the retypes are not first attempts", () => {
    const cursor = new TextCursor("a bc");
    cursor.type("a");
    cursor.type(" ");
    cursor.type("b");
    expect(cursor.backspace()?.target_index).toBe(2);
    expect(cursor.backspace()?.target_index).toBe(1);
    expect(cursor.backspace()?.target_index).toBe(0);
    expect(cursor.type("a")).toStrictEqual({
      target_index: 0,
      expected_char: "a",
      outcome: "correct",
      first_attempt: false,
    });
    expect(cursor.type(" ")).toStrictEqual({
      target_index: 1,
      expected_char: " ",
      outcome: "correct",
      first_attempt: false,
    });
    expect(cursor.type("b")).toStrictEqual({
      target_index: 2,
      expected_char: "b",
      outcome: "correct",
      first_attempt: false,
    });
    expect(cursor.type("c")).toStrictEqual({
      target_index: 3,
      expected_char: "c",
      outcome: "correct",
      first_attempt: true,
    });
    expect(cursor.isDone()).toBe(true);
  });
});

describe("TextCursor isDone (T1.2 amendment F7)", () => {
  it("is done when the index reaches the end, even with an error left on screen", () => {
    const cursor = new TextCursor("ab");
    cursor.type("a");
    expect(cursor.isDone()).toBe(false);
    expect(cursor.type("x")).toStrictEqual({
      target_index: 1,
      expected_char: "b",
      outcome: "error",
      first_attempt: true,
    });
    expect(cursor.index).toBe(2);
    expect(cursor.isDone()).toBe(true);
  });

  it("ignores every key after it is done, Backspace included", () => {
    const cursor = new TextCursor("ab");
    cursor.type("a");
    cursor.type("b");
    expect(cursor.isDone()).toBe(true);
    expect(cursor.type("c")).toBeNull();
    expect(cursor.backspace()).toBeNull();
    expect(cursor.type("a")).toBeNull();
    expect(cursor.backspace()).toBeNull();
    expect(cursor.index).toBe(2);
    expect(cursor.isDone()).toBe(true);
  });

  it("keeps a wrong last character as a permanent first-attempt error", () => {
    const cursor = new TextCursor("ab");
    cursor.type("a");
    expect(cursor.type("x")?.outcome).toBe("error");
    expect(cursor.backspace()).toBeNull();
    expect(cursor.type("b")).toBeNull();
    expect(cursor.index).toBe(2);
    expect(cursor.isDone()).toBe(true);
  });
});

describe("TextCursor input validation (T1.3 owner answer 3)", () => {
  it("rejects a key that is not exactly one character a to z or space", () => {
    const cursor = new TextCursor("ab");
    for (const key of ["A", "T", "é", "1", "\n", "Tab", "Backspace", "", "ab"]) {
      expect(() => cursor.type(key)).toThrow(RangeError);
    }
    expect(cursor.index).toBe(0);
    expect(cursor.type("a")?.first_attempt).toBe(true);
  });

  it("rejects an invalid key even after the block is done", () => {
    const cursor = new TextCursor("a");
    cursor.type("a");
    expect(cursor.isDone()).toBe(true);
    expect(() => cursor.type("A")).toThrow(RangeError);
    expect(cursor.index).toBe(1);
    expect(cursor.isDone()).toBe(true);
  });

  it("rejects an empty target or one with characters outside a to z and space", () => {
    for (const target of ["", "The", "a,b", "a\tb", "café"]) {
      expect(() => new TextCursor(target)).toThrow(RangeError);
    }
  });
});
