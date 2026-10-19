import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { KeystrokeRow, Outcome } from "../../../telemetry/types";
import { TypingDisplayStore } from "../displayStore";

function recorded(targetIndex: number, outcome: Outcome): KeystrokeRow {
  return {
    seq: 0,
    key: outcome === "backspace" ? "Backspace" : "x",
    code: "KeyX",
    t_down_ms: 0,
    t_up_ms: null,
    dwell_ms: null,
    iki_ms: null,
    target_index: targetIndex,
    expected_char: outcome === "backspace" ? null : "x",
    outcome,
    first_attempt: outcome === "backspace" ? null : true,
    after_pause: false,
    handler_ms: 0,
    dispatch_lag_ms: 0,
  };
}

function make(
  targetText: string,
  over: Partial<{ onComplete: () => void; onAbandon: () => void }> = {},
) {
  return new TypingDisplayStore({
    targetText,
    idleWarningMs: 5000,
    idleAbandonMs: 10000,
    ...over,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("TypingDisplayStore", () => {
  it("paints correct and error cells and advances the cursor", () => {
    const store = make("abc");
    store.applyRow(recorded(0, "correct"));
    store.applyRow(recorded(1, "error"));
    expect(store.getCellSnapshot(0)).toBe("correct");
    expect(store.getCellSnapshot(1)).toBe("error");
    expect(store.getCursorIndex()).toBe(2);
    expect(store.getTypedCount()).toBe(2);
    expect(store.getCellSnapshot(2)).toBe("untyped-cursor");
  });

  it("shows the cursor on the current index", () => {
    const store = make("ab");
    expect(store.getCellSnapshot(0)).toBe("untyped-cursor");
    expect(store.getCellSnapshot(1)).toBe("untyped");
  });

  it("backspace clears the cell it lands on and moves the cursor back", () => {
    const store = make("the");
    store.applyRow(recorded(0, "correct"));
    store.applyRow(recorded(1, "error"));
    store.applyRow(recorded(1, "backspace"));
    expect(store.getCursorIndex()).toBe(1);
    expect(store.getCellSnapshot(1)).toBe("untyped-cursor");
    expect(store.getCellSnapshot(0)).toBe("correct");
  });

  it("enters done and calls onComplete once at the last position", () => {
    const onComplete = vi.fn();
    const store = make("ab", { onComplete });
    store.applyRow(recorded(0, "correct"));
    store.applyRow(recorded(1, "correct"));
    expect(store.getPhase()).toBe("done");
    expect(store.getCursorIndex()).toBe(2);
    expect(onComplete).toHaveBeenCalledOnce();
  });

  it("ignores rows once done", () => {
    const onComplete = vi.fn();
    const store = make("ab", { onComplete });
    store.applyRow(recorded(0, "correct"));
    store.applyRow(recorded(1, "correct"));
    store.applyRow(recorded(1, "backspace"));
    expect(store.getPhase()).toBe("done");
    expect(store.getCursorIndex()).toBe(2);
  });

  it("notifies subscribers on each applied row and stops after unsubscribe", () => {
    const store = make("abc");
    const fn = vi.fn();
    const off = store.subscribe(fn);
    store.applyRow(recorded(0, "correct"));
    expect(fn).toHaveBeenCalledOnce();
    off();
    store.applyRow(recorded(1, "correct"));
    expect(fn).toHaveBeenCalledOnce();
  });

  it("enters warning at idleWarningMs and abandons at idleAbandonMs with no recorded rows", () => {
    const onAbandon = vi.fn();
    const store = make("abcd", { onAbandon });
    store.start();
    vi.advanceTimersByTime(5000);
    expect(store.getPhase()).toBe("warning");
    vi.advanceTimersByTime(5000);
    expect(store.getPhase()).toBe("abandoned");
    expect(onAbandon).toHaveBeenCalledOnce();
  });

  it("a recorded row before the warning resets the idle timer", () => {
    const store = make("abcd");
    store.start();
    vi.advanceTimersByTime(4000);
    store.applyRow(recorded(0, "correct"));
    vi.advanceTimersByTime(4000);
    expect(store.getPhase()).toBe("active");
    vi.advanceTimersByTime(1000);
    expect(store.getPhase()).toBe("warning");
  });

  it("resuming typing during the warning clears it back to active", () => {
    const store = make("abcd");
    store.start();
    vi.advanceTimersByTime(5000);
    expect(store.getPhase()).toBe("warning");
    store.applyRow(recorded(0, "correct"));
    expect(store.getPhase()).toBe("active");
  });

  it("idle timers run while paused (blur counts as idle)", () => {
    const onAbandon = vi.fn();
    const store = make("abcd", { onAbandon });
    store.start();
    store.pause();
    vi.advanceTimersByTime(10000);
    expect(store.getPhase()).toBe("abandoned");
    expect(onAbandon).toHaveBeenCalledOnce();
  });

  it("pause and resume toggle isPaused and notify", () => {
    const store = make("ab");
    const fn = vi.fn();
    store.subscribe(fn);
    store.pause();
    expect(store.isPaused()).toBe(true);
    expect(fn).toHaveBeenCalledOnce();
    store.pause();
    expect(fn).toHaveBeenCalledOnce();
    store.resume();
    expect(store.isPaused()).toBe(false);
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("dispose clears pending idle timers", () => {
    const onAbandon = vi.fn();
    const store = make("abcd", { onAbandon });
    store.start();
    store.dispose();
    vi.advanceTimersByTime(10000);
    expect(onAbandon).not.toHaveBeenCalled();
    expect(store.getPhase()).toBe("active");
  });
});
