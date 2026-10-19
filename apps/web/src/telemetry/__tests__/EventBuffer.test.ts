import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createFetchTransport,
  type EventBatch,
  EventBuffer,
  type EventTransport,
} from "../EventBuffer";
import type { KeystrokeRow } from "../types";

function row(seq: number, over: Partial<KeystrokeRow> = {}): KeystrokeRow {
  return {
    seq,
    key: "a",
    code: "KeyA",
    t_down_ms: seq * 100,
    t_up_ms: null,
    dwell_ms: null,
    iki_ms: seq === 0 ? null : 100,
    target_index: seq,
    expected_char: "a",
    outcome: "correct",
    first_attempt: true,
    after_pause: false,
    handler_ms: 0.2,
    dispatch_lag_ms: 0.5,
    ...over,
  };
}

interface Captured {
  readonly blockId: string;
  readonly events: KeystrokeRow[];
}

class FakeTransport implements EventTransport {
  readonly batches: Captured[] = [];
  readonly beacons: Captured[] = [];
  failTimes = 0;
  send(blockId: string, batch: EventBatch): Promise<void> {
    this.batches.push({ blockId, events: [...batch.events] });
    if (this.failTimes > 0) {
      this.failTimes -= 1;
      return Promise.reject(new Error("transport failure"));
    }
    return Promise.resolve();
  }
  sendBeacon(blockId: string, batch: EventBatch): boolean {
    this.beacons.push({ blockId, events: [...batch.events] });
    return true;
  }
}

function make(transport: EventTransport, config = {}, lifecycleTarget: EventTarget | null = null) {
  return new EventBuffer({ blockId: "blk", transport, lifecycleTarget, config });
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("EventBuffer", () => {
  it("sends a row with its key-up filled in on an explicit flush", () => {
    const t = new FakeTransport();
    const b = make(t);
    b.onRow(row(0));
    b.onKeyUp({ seq: 0, t_up_ms: 120, dwell_ms: 20 });
    b.flush();
    expect(t.batches.length).toBe(1);
    // deviation: noUncheckedIndexedAccess requires optional chaining on array index access
    expect(t.batches[0]?.blockId).toBe("blk");
    expect(t.batches[0]?.events[0]?.t_up_ms).toBe(120);
    expect(t.batches[0]?.events[0]?.dwell_ms).toBe(20);
    expect(t.batches[0]?.events[0]?.seq).toBe(0);
  });

  it("does not send a row before its key-up arrives", () => {
    const t = new FakeTransport();
    const b = make(t);
    b.onRow(row(0));
    b.flush();
    expect(t.batches.length).toBe(0);
  });

  it("marks a row ready with null key-up after keyUpWaitMs", async () => {
    const t = new FakeTransport();
    const b = make(t, { keyUpWaitMs: 2000 });
    b.onRow(row(0));
    await vi.advanceTimersByTimeAsync(2000);
    b.flush();
    expect(t.batches.length).toBe(1);
    expect(t.batches[0]?.events[0]?.t_up_ms).toBeNull();
    expect(t.batches[0]?.events[0]?.dwell_ms).toBeNull();
  });

  it("drops a key-up that arrives after the row is already ready", async () => {
    const t = new FakeTransport();
    const b = make(t, { keyUpWaitMs: 2000 });
    b.onRow(row(0));
    await vi.advanceTimersByTimeAsync(2000);
    b.onKeyUp({ seq: 0, t_up_ms: 500, dwell_ms: 400 });
    b.flush();
    expect(t.batches[0]?.events[0]?.t_up_ms).toBeNull();
  });

  it("ignores an unknown key-up seq", () => {
    const t = new FakeTransport();
    const b = make(t);
    b.onKeyUp({ seq: 99, t_up_ms: 1, dwell_ms: 1 });
    b.flush();
    expect(t.batches.length).toBe(0);
  });

  it("flushes automatically at the row threshold", async () => {
    const t = new FakeTransport();
    const b = make(t, { flushRows: 3 });
    for (const s of [0, 1, 2]) {
      b.onRow(row(s));
      b.onKeyUp({ seq: s, t_up_ms: s * 100 + 10, dwell_ms: 10 });
    }
    await vi.advanceTimersByTimeAsync(0);
    expect(t.batches.length).toBe(1);
    expect(t.batches[0]?.events.map((e) => e.seq)).toEqual([0, 1, 2]);
  });

  it("flushes ready rows on the interval", async () => {
    const t = new FakeTransport();
    const b = make(t, { flushIntervalMs: 5000, flushRows: 50 });
    b.onRow(row(0));
    b.onKeyUp({ seq: 0, t_up_ms: 10, dwell_ms: 10 });
    await vi.advanceTimersByTimeAsync(5000);
    expect(t.batches.length).toBe(1);
    expect(t.batches[0]?.events[0]?.seq).toBe(0);
    await vi.advanceTimersByTimeAsync(5000);
    expect(t.batches.length).toBe(1);
  });

  it("delivers ready rows once across threshold and interval", async () => {
    const t = new FakeTransport();
    const b = make(t, { flushRows: 2, flushIntervalMs: 5000 });
    for (const s of [0, 1]) {
      b.onRow(row(s));
      b.onKeyUp({ seq: s, t_up_ms: s * 100 + 10, dwell_ms: 10 });
    }
    await vi.advanceTimersByTimeAsync(0);
    expect(t.batches.length).toBe(1);
    await vi.advanceTimersByTimeAsync(5000);
    expect(t.batches.length).toBe(1);
  });

  it("retries a failed send with exponential backoff until it succeeds", async () => {
    const t = new FakeTransport();
    t.failTimes = 2;
    const b = make(t, { flushRows: 1, backoffBaseMs: 500, backoffMaxMs: 8000 });
    b.onRow(row(0));
    b.onKeyUp({ seq: 0, t_up_ms: 10, dwell_ms: 10 });
    await vi.advanceTimersByTimeAsync(0);
    expect(t.batches.length).toBe(1);
    await vi.advanceTimersByTimeAsync(500);
    expect(t.batches.length).toBe(2);
    await vi.advanceTimersByTimeAsync(1000);
    expect(t.batches.length).toBe(3);
    await vi.advanceTimersByTimeAsync(10000);
    expect(t.batches.length).toBe(3);
    for (const batch of t.batches) {
      expect(batch.events.map((e) => e.seq)).toEqual([0]);
    }
  });

  it("caps the backoff delay at backoffMaxMs", async () => {
    const t = new FakeTransport();
    t.failTimes = 4;
    const b = make(t, { flushRows: 1, backoffBaseMs: 500, backoffMaxMs: 8000 });
    b.onRow(row(0));
    b.onKeyUp({ seq: 0, t_up_ms: 10, dwell_ms: 10 });
    await vi.advanceTimersByTimeAsync(0);
    expect(t.batches.length).toBe(1);
    await vi.advanceTimersByTimeAsync(500);
    expect(t.batches.length).toBe(2);
    await vi.advanceTimersByTimeAsync(1000);
    expect(t.batches.length).toBe(3);
    await vi.advanceTimersByTimeAsync(2000);
    expect(t.batches.length).toBe(4);
    await vi.advanceTimersByTimeAsync(4000);
    expect(t.batches.length).toBe(5);
    await vi.advanceTimersByTimeAsync(8000);
    expect(t.batches.length).toBe(5);
  });

  it("beacons all remaining ready and pending rows on pagehide", () => {
    const t = new FakeTransport();
    const target = new EventTarget();
    const b = make(t, {}, target);
    b.onRow(row(0));
    b.onKeyUp({ seq: 0, t_up_ms: 10, dwell_ms: 10 });
    b.onRow(row(1));
    target.dispatchEvent(new Event("pagehide"));
    expect(t.beacons.length).toBe(1);
    expect(t.beacons[0]?.blockId).toBe("blk");
    expect(t.beacons[0]?.events.map((e) => e.seq)).toEqual([0, 1]);
    expect(t.beacons[0]?.events[1]?.t_up_ms).toBeNull();
    expect(t.batches.length).toBe(0);
  });

  it("dispose clears timers and the pagehide listener", async () => {
    const t = new FakeTransport();
    const target = new EventTarget();
    const b = make(t, { flushIntervalMs: 5000, keyUpWaitMs: 2000 }, target);
    b.onRow(row(0));
    b.dispose();
    await vi.advanceTimersByTimeAsync(10000);
    target.dispatchEvent(new Event("pagehide"));
    expect(t.batches.length).toBe(0);
    expect(t.beacons.length).toBe(0);
  });

  it("uses the configured block id for sends and beacons", () => {
    const t = new FakeTransport();
    const target = new EventTarget();
    const b = new EventBuffer({ blockId: "blk-xyz", transport: t, lifecycleTarget: target });
    b.onRow(row(0));
    b.onKeyUp({ seq: 0, t_up_ms: 10, dwell_ms: 10 });
    b.flush();
    expect(t.batches[0]?.blockId).toBe("blk-xyz");
    // row(1) is pending (no key-up) so #beaconRemaining has something to send on pagehide
    b.onRow(row(1));
    target.dispatchEvent(new Event("pagehide"));
    expect(t.beacons[0]?.blockId).toBe("blk-xyz");
  });

  it("createFetchTransport posts JSON to the block events path", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true }) as Response);
    vi.stubGlobal("fetch", fetchMock);
    const tr = createFetchTransport();
    await tr.send("blk-1", { events: [row(0)] });
    expect(fetchMock).toHaveBeenCalledOnce();
    // deviation: cast through unknown first (noUncheckedIndexedAccess + tuple cast)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/blocks/blk-1/events");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["content-type"]).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ events: [row(0)] });
  });

  it("createFetchTransport rejects on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 500 }) as Response),
    );
    await expect(createFetchTransport().send("blk", { events: [] })).rejects.toThrow(/status 500/);
  });
});
