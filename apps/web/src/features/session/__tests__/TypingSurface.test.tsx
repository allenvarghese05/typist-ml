// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, createEvent, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createCollectorSink } from "../collector";
import type { BlockLifecycleEvent } from "../TypingSurface";
import { TypingSurface } from "../TypingSurface";

function press(key: string, code: string): void {
  fireEvent.keyDown(window, { key, code });
  fireEvent.keyUp(window, { key, code });
}
function cellState(index: number): string | null {
  return document.querySelector(`[data-cell="${index}"]`)?.getAttribute("data-state") ?? null;
}

beforeEach(() => {
  vi.spyOn(document, "hasFocus").mockReturnValue(true);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("TypingSurface", () => {
  it("renders the block label and one span per target character", () => {
    render(<TypingSurface targetText="abc" blockLabel="Block 1" sink={createCollectorSink()} />);
    expect(screen.getByText("Block 1")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-cell]").length).toBe(3);
  });

  it("typing does not re-render the surface or the text container", () => {
    const onSurfaceRender = vi.fn();
    const onTextRender = vi.fn();
    render(
      <TypingSurface
        targetText="abcdef"
        blockLabel="Block 1"
        sink={createCollectorSink()}
        probe={{ onSurfaceRender, onTextRender }}
      />,
    );
    expect(onSurfaceRender).toHaveBeenCalledOnce();
    expect(onTextRender).toHaveBeenCalledOnce();
    press("a", "KeyA");
    press("b", "KeyB");
    press("c", "KeyC");
    expect(onSurfaceRender).toHaveBeenCalledOnce();
    expect(onTextRender).toHaveBeenCalledOnce();
    expect(cellState(0)).toBe("correct");
    expect(cellState(2)).toBe("correct");
    expect(cellState(3)).toBe("untyped-cursor");
  });

  it("shows wrong characters in red and leaves them until Backspace", () => {
    render(<TypingSurface targetText="the" blockLabel="Block 1" sink={createCollectorSink()} />);
    press("t", "KeyT");
    expect(cellState(0)).toBe("correct");
    press("x", "KeyX");
    expect(cellState(1)).toBe("error");
    press("Backspace", "Backspace");
    expect(cellState(1)).toBe("untyped-cursor");
    expect(cellState(0)).toBe("correct");
  });

  it("prevents default on handled keys and not on others", () => {
    render(<TypingSurface targetText="a b" blockLabel="Block 1" sink={createCollectorSink()} />);

    const spaceEv = createEvent.keyDown(window, { key: " ", code: "Space" });
    fireEvent(window, spaceEv);
    expect(spaceEv.defaultPrevented).toBe(true);

    const backspaceEv = createEvent.keyDown(window, { key: "Backspace", code: "Backspace" });
    fireEvent(window, backspaceEv);
    expect(backspaceEv.defaultPrevented).toBe(true);

    const aEv = createEvent.keyDown(window, { key: "a", code: "KeyA" });
    fireEvent(window, aEv);
    expect(aEv.defaultPrevented).toBe(true);

    const tabEv = createEvent.keyDown(window, { key: "Tab", code: "Tab" });
    fireEvent(window, tabEv);
    expect(tabEv.defaultPrevented).toBe(false);

    const arrowEv = createEvent.keyDown(window, { key: "ArrowLeft", code: "ArrowLeft" });
    fireEvent(window, arrowEv);
    expect(arrowEv.defaultPrevented).toBe(false);

    const ctrlAEv = createEvent.keyDown(window, { key: "a", code: "KeyA", ctrlKey: true });
    fireEvent(window, ctrlAEv);
    expect(ctrlAEv.defaultPrevented).toBe(false);
  });

  it("pauses on window blur and resumes on focus", () => {
    render(<TypingSurface targetText="abc" blockLabel="Block 1" sink={createCollectorSink()} />);
    fireEvent.blur(window);
    expect(screen.getByText(/paused/i)).toBeInTheDocument();
    fireEvent.focus(window);
    expect(screen.queryByText(/paused/i)).toBeNull();
  });

  it("does not record keys while blurred", () => {
    const sink = createCollectorSink();
    render(<TypingSurface targetText="abc" blockLabel="Block 1" sink={sink} />);
    press("a", "KeyA");
    expect(sink.rows.length).toBe(1);
    fireEvent.blur(window);
    press("b", "KeyB");
    expect(sink.rows.length).toBe(1);
    fireEvent.focus(window);
    press("b", "KeyB");
    expect(sink.rows.length).toBe(2);
    expect(sink.rows[1]?.after_pause).toBe(true);
  });

  it("emits start on mount with attempt 0 and the block-start origin", () => {
    const events: BlockLifecycleEvent[] = [];
    render(
      <TypingSurface
        targetText="abc"
        blockLabel="Block 1"
        sink={createCollectorSink()}
        onLifecycle={(e) => events.push(e)}
        now={() => 1234}
      />,
    );
    expect(events[0]).toEqual({ kind: "start", attempt: 0, blockStartMs: 1234 });
  });

  it("completes the block and emits complete", () => {
    const events: BlockLifecycleEvent[] = [];
    render(
      <TypingSurface
        targetText="ab"
        blockLabel="Block 1"
        sink={createCollectorSink()}
        onLifecycle={(e) => events.push(e)}
      />,
    );
    press("a", "KeyA");
    press("b", "KeyB");
    expect(events).toContainEqual({ kind: "complete", attempt: 0 });
    expect(screen.getByText(/complete/i)).toBeInTheDocument();
  });

  it("warns, abandons, and restarts a fresh attempt", () => {
    vi.useFakeTimers();
    const events: BlockLifecycleEvent[] = [];
    render(
      <TypingSurface
        targetText="abcdef"
        blockLabel="Block 1"
        sink={createCollectorSink()}
        idleWarningMs={5000}
        idleAbandonMs={10000}
        onLifecycle={(e) => events.push(e)}
      />,
    );
    press("a", "KeyA");
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByText(/keep typing/i)).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByText(/abandoned/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restart/i })).toBeInTheDocument();
    expect(events).toContainEqual({ kind: "abandon", attempt: 0 });
    fireEvent.click(screen.getByRole("button", { name: /restart/i }));
    expect(events.some((e) => e.kind === "start" && e.attempt === 1)).toBe(true);
    expect(cellState(0)).toBe("untyped-cursor");
  });

  it("records typing driven by user-event", async () => {
    const sink = createCollectorSink();
    render(<TypingSurface targetText="abc" blockLabel="Block 1" sink={sink} />);
    const user = userEvent.setup();
    await user.keyboard("abc");
    expect(cellState(0)).toBe("correct");
    expect(sink.rows.map((r) => r.key)).toEqual(["a", "b", "c"]);
  });

  it("has no editable field, so no autocorrect or spellcheck applies", () => {
    render(<TypingSurface targetText="abc" blockLabel="Block 1" sink={createCollectorSink()} />);
    expect(document.querySelector("input, textarea, [contenteditable]")).toBeNull();
  });

  it("starts paused and drops keys when the page is not focused", () => {
    vi.spyOn(document, "hasFocus").mockReturnValue(false);
    const sink = createCollectorSink();
    render(<TypingSurface targetText="abc" blockLabel="Block 1" sink={sink} />);
    expect(screen.getByText(/paused/i)).toBeInTheDocument();
    press("a", "KeyA");
    expect(sink.rows.length).toBe(0);
  });
});
