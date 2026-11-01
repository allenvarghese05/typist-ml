// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EventBatch, EventTransport } from "../../../telemetry/EventBuffer";
import { SessionPage } from "../SessionPage";

function pressKey(key: string, code: string): void {
  fireEvent.keyDown(window, { key, code });
  fireEvent.keyUp(window, { key, code });
}

beforeEach(() => {
  vi.spyOn(document, "hasFocus").mockReturnValue(true);
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SessionPage", () => {
  it("enrolls a new profile, records consent, runs a baseline session, flushes events, and shows summary", async () => {
    let status = "enrolled";
    let participantsList: Array<{
      id: string;
      alias: string;
      status: string;
      is_builder: boolean;
      is_blinded: boolean;
      created_at: string;
      consent_at: string | null;
    }> = [];
    const trendList: Array<{
      session_id: string;
      phase: string;
      day_index: number;
      started_at: string;
      wpm: number | null;
      accuracy: number | null;
      per_set_error_rate: Record<string, number | null>;
      per_set_attempts: Record<string, number>;
      per_set_errors: Record<string, number>;
    }> = [];

    const uploadedBatches: Array<{ blockId: string; batch: EventBatch }> = [];
    const fakeTransport: EventTransport = {
      async send(blockId, batch) {
        uploadedBatches.push({ blockId, batch });
      },
      sendBeacon() {
        return true;
      },
    };

    const completedBlocks: string[] = [];
    const completedSessions: string[] = [];

    const fakeFetch: typeof fetch = vi.fn().mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.endsWith("/health")) {
        return new Response(
          JSON.stringify({
            status: "ok",
            database: "ok",
            worker: { status: "ok", heartbeat_age_s: 1.0 },
          }),
          { status: 200 },
        );
      }

      if (url.endsWith("/participants") && method === "GET") {
        return new Response(JSON.stringify(participantsList), { status: 200 });
      }

      if (url.endsWith("/participants") && method === "POST") {
        const created = {
          id: "p-allen",
          alias: "allen",
          status: "enrolled",
          is_builder: false,
          is_blinded: true,
          created_at: "2026-11-01T12:00:00Z",
          consent_at: null,
        };
        participantsList = [created];
        return new Response(JSON.stringify(created), { status: 201 });
      }

      if (url.endsWith("/participants/p-allen/consent") && method === "POST") {
        status = "baseline";
        participantsList = participantsList.map((p) =>
          p.id === "p-allen" ? { ...p, status, consent_at: "2026-11-01T12:01:00Z" } : p,
        );
        return new Response(JSON.stringify(participantsList[0]), { status: 200 });
      }

      if (url.includes("/analysis/participants/p-allen/trend")) {
        return new Response(JSON.stringify(trendList), { status: 200 });
      }

      if (url.endsWith("/participants/p-allen/sessions") && method === "POST") {
        return new Response(
          JSON.stringify({
            session_id: "s-base-1",
            participant_id: "p-allen",
            phase: "baseline",
            day_index: 1,
            status: "in_progress",
            blocks: [
              {
                block_id: "b-base-1",
                block_index: 0,
                label: "Block 1",
                target_text: "ab",
                started_at: null,
                ended_at: null,
              },
            ],
          }),
          { status: 200 },
        );
      }

      if (url.endsWith("/blocks/b-base-1/start") && method === "POST") {
        return new Response(
          JSON.stringify({
            id: "b-base-1",
            session_id: "s-base-1",
            block_index: 0,
            label: "Block 1",
            started_at: "2026-11-01T12:02:00Z",
            ended_at: null,
          }),
          { status: 200 },
        );
      }

      if (url.endsWith("/blocks/b-base-1/complete") && method === "POST") {
        completedBlocks.push("b-base-1");
        return new Response(
          JSON.stringify({
            id: "b-base-1",
            session_id: "s-base-1",
            block_index: 0,
            label: "Block 1",
            started_at: "2026-11-01T12:02:00Z",
            ended_at: "2026-11-01T12:02:10Z",
          }),
          { status: 200 },
        );
      }

      if (url.endsWith("/sessions/s-base-1/complete") && method === "POST") {
        completedSessions.push("s-base-1");
        trendList.push({
          session_id: "s-base-1",
          phase: "baseline",
          day_index: 1,
          started_at: "2026-11-01T12:02:00Z",
          wpm: 64.2,
          accuracy: 0.985,
          per_set_error_rate: {},
          per_set_attempts: {},
          per_set_errors: {},
        });
        return new Response(
          JSON.stringify({
            session_id: "s-base-1",
            wpm: 64.2,
            accuracy: 0.985,
            bigram_count: 1,
            blocks: 1,
          }),
          { status: 200 },
        );
      }

      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    });

    render(<SessionPage fetchImpl={fakeFetch} eventTransport={fakeTransport} />);

    // 1. Empty workspace opens enrollment form automatically
    const aliasInput = await screen.findByTestId("studio-alias-input");
    fireEvent.change(aliasInput, { target: { value: "allen" } });
    fireEvent.click(screen.getByTestId("studio-create-profile-btn"));

    // 2. Consent card appears for 'enrolled' status
    const consentBtn = await screen.findByTestId("record-consent-btn");
    fireEvent.click(consentBtn);

    // 3. Baseline Session 1 of 2 launch card appears
    const startBtn = await screen.findByTestId("start-session-btn");
    expect(startBtn).toHaveTextContent("Start Baseline 1 of 2");
    fireEvent.click(startBtn);

    // 4. Pre-block briefing screen prevents premature idle abandon before typing starts
    const beginBlockBtn = await screen.findByTestId("begin-block-btn");
    expect(beginBlockBtn).toHaveTextContent("Begin Block 1");
    fireEvent.click(beginBlockBtn);

    // 5. Active typing surface mounts; type "ab"
    await screen.findByTestId("live-typing-stage");
    act(() => {
      pressKey("a", "KeyA");
      pressKey("b", "KeyB");
    });

    // 6. EventBuffer drains BEFORE completeBlock & completeSession, then Summary Card renders
    const summaryCard = await screen.findByTestId("session-summary-card");
    expect(summaryCard).toBeInTheDocument();
    expect(uploadedBatches.length).toBeGreaterThanOrEqual(1);
    expect(uploadedBatches.flatMap((u) => u.batch.events.map((e) => e.key))).toEqual(["a", "b"]);
    expect(completedBlocks).toEqual(["b-base-1"]);
    expect(completedSessions).toEqual(["s-base-1"]);
    expect(screen.getByTestId("summary-wpm")).toHaveTextContent("64.2");
    expect(screen.getByTestId("summary-accuracy")).toHaveTextContent("98.5%");

    // 7. Continuing returns to hub showing Baseline 2 of 2 ready
    fireEvent.click(screen.getByTestId("summary-continue-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("start-session-btn")).toHaveTextContent("Start Baseline 2 of 2");
    });
  });

  it("preserves strict single-blind labels (D18) during assigned pool readiness and multi-block practice", async () => {
    const fakeTransport: EventTransport = {
      async send() {},
      sendBeacon() {
        return true;
      },
    };

    const fakeFetch: typeof fetch = vi.fn().mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";

      if (url.endsWith("/health")) {
        return new Response(
          JSON.stringify({
            status: "ok",
            database: "ok",
            worker: { status: "ok", heartbeat_age_s: 1.0 },
          }),
          { status: 200 },
        );
      }
      if (url.endsWith("/participants")) {
        return new Response(
          JSON.stringify([
            {
              id: "p-prac",
              alias: "blinded-peer",
              status: "assigned",
              is_builder: false,
              is_blinded: true,
              created_at: "2026-11-01T12:00:00Z",
              consent_at: "2026-11-01T12:01:00Z",
            },
          ]),
          { status: 200 },
        );
      }
      if (url.includes("/analysis/participants/p-prac/trend")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.includes("/admin/pool")) {
        return new Response(
          JSON.stringify([
            {
              participant_id: "p-prac",
              alias: "blinded-peer",
              arms: [
                {
                  arm: "control",
                  ready_count: 6,
                  target_count: 6,
                  queued_count: 0,
                  used_count: 0,
                  deficit: 0,
                  is_ready: true,
                },
                {
                  arm: "heuristic",
                  ready_count: 6,
                  target_count: 6,
                  queued_count: 0,
                  used_count: 0,
                  deficit: 0,
                  is_ready: true,
                },
                {
                  arm: "markov",
                  ready_count: 6,
                  target_count: 6,
                  queued_count: 0,
                  used_count: 0,
                  deficit: 0,
                  is_ready: true,
                },
                {
                  arm: "llm",
                  ready_count: 6,
                  target_count: 6,
                  queued_count: 0,
                  used_count: 0,
                  deficit: 0,
                  is_ready: true,
                },
              ],
            },
          ]),
          { status: 200 },
        );
      }
      if (url.endsWith("/participants/p-prac/sessions") && method === "POST") {
        return new Response(
          JSON.stringify({
            session_id: "s-prac-1",
            participant_id: "p-prac",
            phase: "practice",
            day_index: 1,
            status: "in_progress",
            blocks: [
              {
                block_id: "b-1",
                block_index: 0,
                label: "Block 1",
                target_text: "x",
                started_at: null,
                ended_at: null,
              },
              {
                block_id: "b-2",
                block_index: 1,
                label: "Block 2",
                target_text: "y",
                started_at: null,
                ended_at: null,
              },
            ],
          }),
          { status: 200 },
        );
      }
      if (url.includes("/blocks/") && method === "POST") {
        return new Response(
          JSON.stringify({
            id: "b-1",
            session_id: "s-prac-1",
            block_index: 0,
            label: "Block 1",
            started_at: "2026-11-01T12:02:00Z",
            ended_at: "2026-11-01T12:02:05Z",
          }),
          { status: 200 },
        );
      }
      if (url.endsWith("/sessions/s-prac-1/complete") && method === "POST") {
        return new Response(
          JSON.stringify({
            session_id: "s-prac-1",
            wpm: 51.0,
            accuracy: 1.0,
            bigram_count: 0,
            blocks: 2,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });

    render(<SessionPage fetchImpl={fakeFetch} eventTransport={fakeTransport} />);

    const card = await screen.findByTestId("assigned-pool-card");
    const html = card.innerHTML.toLowerCase();
    expect(html).not.toContain("heuristic");
    expect(html).not.toContain("markov");
    expect(html).not.toContain("llm");

    // Launch Practice Session 1 -> Block 1 -> Inter-block Ready for Block 2 -> Summary
    fireEvent.click(await screen.findByTestId("start-session-btn"));
    fireEvent.click(await screen.findByTestId("begin-block-btn"));
    await screen.findByTestId("live-typing-stage");
    act(() => {
      pressKey("x", "KeyX");
    });

    // Inter-block transition shows Ready for Block 2
    const nextReady = await screen.findByTestId("begin-block-btn");
    expect(nextReady).toHaveTextContent("Begin Block 2");
    fireEvent.click(nextReady);
    await screen.findByTestId("live-typing-stage");
    act(() => {
      pressKey("y", "KeyY");
    });

    expect(await screen.findByTestId("session-summary-card")).toBeInTheDocument();
  });
});
