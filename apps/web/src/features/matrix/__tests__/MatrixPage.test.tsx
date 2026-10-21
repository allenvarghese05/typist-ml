// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import type { BigramMatrix } from "../../../api/analysis";
import { MatrixPage } from "../MatrixPage";

const MATRIX: BigramMatrix = {
  session_id: "s1",
  participant_id: "p1",
  phase: "baseline",
  wpm: 22,
  accuracy: 0.86,
  cells: [
    { bigram: "th", attempts: 10, errors: 5, error_rate: 0.5, iki_median_ms: 200, iki_n: 4 },
    { bigram: "he", attempts: 4, errors: 1, error_rate: 0.25, iki_median_ms: 100, iki_n: 2 },
  ],
};

function okFetch(): typeof fetch {
  return async () =>
    new Response(JSON.stringify(MATRIX), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
}

function cell(bigram: string): HTMLElement {
  const element = document.querySelector(`[data-cell-bigram="${bigram}"]`);
  if (element === null) {
    throw new Error(`no cell ${bigram}`);
  }
  return element as HTMLElement;
}

afterEach(() => {
  cleanup();
});

describe("MatrixPage", () => {
  it("renders 676 cells and 52 axis labels from the fetched matrix", async () => {
    render(<MatrixPage sessionId="s1" fetchImpl={okFetch()} />);
    await waitFor(() => expect(document.querySelectorAll("[data-cell-bigram]").length).toBe(676));
    expect(document.querySelectorAll("[data-axis-label]").length).toBe(52);
    expect(cell("th").getAttribute("data-value")).toBe("0.5");
    expect(cell("th").getAttribute("data-metric")).toBe("error");
  });

  it("toggling to Median IKI changes a cell's metric, value and colour", async () => {
    const user = userEvent.setup();
    render(<MatrixPage sessionId="s1" fetchImpl={okFetch()} />);
    await waitFor(() => expect(document.querySelectorAll("[data-cell-bigram]").length).toBe(676));
    const before = cell("th").style.backgroundColor;
    expect(cell("th").getAttribute("data-value")).toBe("0.5");
    await user.click(screen.getByRole("button", { name: "Median IKI" }));
    expect(cell("th").getAttribute("data-metric")).toBe("iki");
    expect(cell("th").getAttribute("data-value")).toBe("200");
    expect(cell("th").style.backgroundColor).not.toBe(before);
  });

  it("shows a message when the session is not found", async () => {
    const notFound: typeof fetch = async () => new Response(null, { status: 404 });
    render(<MatrixPage sessionId="nope" fetchImpl={notFound} />);
    expect(await screen.findByText("Session not found.")).toBeInTheDocument();
  });
});
