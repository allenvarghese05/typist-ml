import { describe, expect, it } from "vitest";
import { type BigramMatrix, fetchSessionMatrix } from "../analysis";

const MATRIX: BigramMatrix = {
  session_id: "s1",
  participant_id: "p1",
  phase: "baseline",
  wpm: 22,
  accuracy: 0.86,
  cells: [{ bigram: "th", attempts: 10, errors: 5, error_rate: 0.5, iki_median_ms: 200, iki_n: 4 }],
};

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("fetchSessionMatrix", () => {
  it("returns ok with the parsed matrix on 200", async () => {
    const result = await fetchSessionMatrix("s1", async () => jsonResponse(MATRIX, 200));
    expect(result).toEqual({ status: "ok", matrix: MATRIX });
  });

  it("maps 404 to not-found", async () => {
    const result = await fetchSessionMatrix("s1", async () => new Response(null, { status: 404 }));
    expect(result).toEqual({ status: "not-found" });
  });

  it("maps 409 to not-completed", async () => {
    const result = await fetchSessionMatrix("s1", async () => new Response(null, { status: 409 }));
    expect(result).toEqual({ status: "not-completed" });
  });

  it("maps other non-2xx to error", async () => {
    const result = await fetchSessionMatrix("s1", async () => new Response(null, { status: 500 }));
    expect(result).toEqual({ status: "error", message: "request failed with status 500" });
  });

  it("maps a thrown fetch to error", async () => {
    const result = await fetchSessionMatrix("s1", async () => {
      throw new Error("boom");
    });
    expect(result).toEqual({ status: "error", message: "boom" });
  });

  it("encodes the session id in the path", async () => {
    let seen = "";
    await fetchSessionMatrix("a/b", async (input) => {
      seen = String(input);
      return jsonResponse(MATRIX, 200);
    });
    expect(seen).toBe("/api/v1/analysis/sessions/a%2Fb/matrix");
  });
});
