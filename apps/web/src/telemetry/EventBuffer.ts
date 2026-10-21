import { apiPath } from "../api/paths";
import { DEFAULT_EVENT_BUFFER_CONFIG, type EventBufferConfig } from "./eventBufferConfig";
import type { KeystrokeRow, KeystrokeSink, KeyUpUpdate } from "./types";

/** The JSON body of POST /api/v1/blocks/{block_id}/events (T1.6 owner answer 4). */
export interface EventBatch {
  readonly events: readonly KeystrokeRow[];
}

/**
 * How a batch leaves the browser. Injected so tests use a fake; the default uses fetch for
 * flushes and navigator.sendBeacon for page unload (no openapi-typescript, no client.ts — owner
 * answer 12).
 */
export interface EventTransport {
  /**
   * POST the batch for one block. Resolves on a 2xx response, rejects on any other status or a
   * network error. Timed, threshold and block-end flushes retry on rejection.
   */
  send(blockId: string, batch: EventBatch): Promise<void>;
  /**
   * Best-effort synchronous send for page unload (navigator.sendBeacon). Returns whether the user
   * agent queued the request; the response is never read (owner answer 6).
   */
  sendBeacon(blockId: string, batch: EventBatch): boolean;
}

/** Timer seam so tests drive readiness, interval and backoff with fake timers. */
export interface Timers {
  setTimeout(handler: () => void, ms: number): number;
  clearTimeout(handle: number): void;
  setInterval(handler: () => void, ms: number): number;
  clearInterval(handle: number): void;
}

/** Minimal page-unload hook (window in production); injected as a fake in tests. */
export interface PageHideTarget {
  addEventListener(type: "pagehide", listener: () => void): void;
  removeEventListener(type: "pagehide", listener: () => void): void;
}

/** Everything an EventBuffer needs; one buffer per block attempt (owner answers 8, 9). */
export interface EventBufferOptions {
  /** The block this buffer uploads to; it addresses POST /blocks/{blockId}/events (owner answer 4). */
  readonly blockId: string;
  /** Where batches go. Defaults to createFetchTransport(). */
  readonly transport?: EventTransport;
  /** Timer source. Defaults to the global timers (controllable with vi.useFakeTimers()). */
  readonly timers?: Timers;
  /**
   * Page-unload source for sendBeacon. Defaults to window when it exists, else null (no unload
   * hook). Pass null to disable, or a fake target in tests.
   */
  readonly lifecycleTarget?: PageHideTarget | null;
  /** Overrides merged over DEFAULT_EVENT_BUFFER_CONFIG. */
  readonly config?: Partial<EventBufferConfig>;
}

/** The production transport: fetch for flushes, navigator.sendBeacon for unload. */
export function createFetchTransport(): EventTransport {
  return {
    async send(blockId, batch) {
      const response = await fetch(apiPath(`/blocks/${encodeURIComponent(blockId)}/events`), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(batch),
        keepalive: true,
      });
      if (!response.ok) {
        throw new Error(`events upload failed with status ${response.status}`);
      }
    },
    sendBeacon(blockId, batch) {
      const blob = new Blob([JSON.stringify(batch)], { type: "application/json" });
      return navigator.sendBeacon(apiPath(`/blocks/${encodeURIComponent(blockId)}/events`), blob);
    },
  };
}

/** Global timers behind the Timers seam. In the DOM lib these return numbers. */
const browserTimers: Timers = {
  setTimeout: (handler, ms) => setTimeout(handler, ms),
  clearTimeout: (handle) => {
    clearTimeout(handle);
  },
  setInterval: (handler, ms) => setInterval(handler, ms),
  clearInterval: (handle) => {
    clearInterval(handle);
  },
};

/** A KeystrokeRow being buffered, so t_up_ms/dwell_ms can be filled before it is sent. */
type BufferedRow = { -readonly [K in keyof KeystrokeRow]: KeystrokeRow[K] };

/**
 * Buffers one block's keystroke rows and uploads them idempotently (design doc 12.4; T1.6).
 *
 * It implements KeystrokeSink. onRow copies a row and waits for its key-up or keyUpWaitMs; onKeyUp
 * fills that row's t_up_ms/dwell_ms and releases it. A row is sent only once it is ready (key-up
 * arrived, or keyUpWaitMs passed with t_up_ms left null — owner answer 1). Ready rows flush every
 * flushRows, every flushIntervalMs, and on an explicit flush() at block end; a block-end flush
 * never forces a pending row out. Failed sends retry with exponential backoff forever. On pagehide
 * every remaining row is sent with navigator.sendBeacon. onRow/onKeyUp only enqueue and never
 * throw; all network happens off the key-handler path. No statistics, no randomness.
 */
export class EventBuffer implements KeystrokeSink {
  readonly #blockId: string;
  readonly #transport: EventTransport;
  readonly #timers: Timers;
  readonly #config: EventBufferConfig;
  readonly #lifecycleTarget: PageHideTarget | null;
  readonly #onPageHide = (): void => {
    this.#beaconRemaining();
  };

  /** Rows waiting for their key-up or the keyUpWaitMs timeout, keyed by seq. */
  readonly #pending = new Map<number, BufferedRow>();
  /** The keyUpWaitMs readiness timer per pending seq. */
  readonly #waitTimers = new Map<number, number>();
  /** Rows ready to send, in the order they became ready. */
  readonly #ready: BufferedRow[] = [];

  #intervalTimer: number | null = null;
  #immediateTimer: number | null = null;
  #retryTimer: number | null = null;
  #sending = false;
  #backoffExponent = 0;
  #closed = false;

  constructor(options: EventBufferOptions) {
    this.#blockId = options.blockId;
    this.#transport = options.transport ?? createFetchTransport();
    this.#timers = options.timers ?? browserTimers;
    this.#config = { ...DEFAULT_EVENT_BUFFER_CONFIG, ...options.config };
    this.#lifecycleTarget =
      options.lifecycleTarget === undefined
        ? typeof window === "undefined"
          ? null
          : window
        : options.lifecycleTarget;
    this.#intervalTimer = this.#timers.setInterval(() => {
      this.#flush();
    }, this.#config.flushIntervalMs);
    this.#lifecycleTarget?.addEventListener("pagehide", this.#onPageHide);
  }

  /** Buffer a new row (KeystrokeSink). Cheap, never throws into the key handler. */
  onRow(row: KeystrokeRow): void {
    try {
      if (this.#closed) {
        return;
      }
      const buffered: BufferedRow = { ...row };
      this.#pending.set(buffered.seq, buffered);
      const seq = buffered.seq;
      const handle = this.#timers.setTimeout(() => {
        this.#promote(seq);
      }, this.#config.keyUpWaitMs);
      this.#waitTimers.set(seq, handle);
    } catch {
      // The KeystrokeSink contract forbids throwing into the key handler.
    }
  }

  /** Fill a buffered row's key-up and release it (KeystrokeSink). Late/unknown key-ups are dropped. */
  onKeyUp(update: KeyUpUpdate): void {
    try {
      if (this.#closed) {
        return;
      }
      const row = this.#pending.get(update.seq);
      if (row === undefined) {
        // Row already ready or sent (owner answer 1): keyup stays null; drop it.
        return;
      }
      row.t_up_ms = update.t_up_ms;
      row.dwell_ms = update.dwell_ms;
      this.#promote(update.seq);
    } catch {
      // Never throw into the key handler.
    }
  }

  /** Send every ready row now (block end, design doc 12.4). Pending rows keep waiting (owner answer 1). */
  flush(): void {
    this.#flush();
  }

  /** Stop all timers and the pagehide listener. Call when the attempt is finished or discarded. */
  dispose(): void {
    this.#closed = true;
    if (this.#intervalTimer !== null) {
      this.#timers.clearInterval(this.#intervalTimer);
      this.#intervalTimer = null;
    }
    if (this.#immediateTimer !== null) {
      this.#timers.clearTimeout(this.#immediateTimer);
      this.#immediateTimer = null;
    }
    if (this.#retryTimer !== null) {
      this.#timers.clearTimeout(this.#retryTimer);
      this.#retryTimer = null;
    }
    for (const handle of this.#waitTimers.values()) {
      this.#timers.clearTimeout(handle);
    }
    this.#waitTimers.clear();
    this.#lifecycleTarget?.removeEventListener("pagehide", this.#onPageHide);
  }

  /** Move a pending row to the ready queue and clear its wait timer. */
  #promote(seq: number): void {
    const row = this.#pending.get(seq);
    if (row === undefined) {
      return;
    }
    this.#pending.delete(seq);
    const handle = this.#waitTimers.get(seq);
    if (handle !== undefined) {
      this.#timers.clearTimeout(handle);
      this.#waitTimers.delete(seq);
    }
    this.#ready.push(row);
    if (this.#ready.length >= this.#config.flushRows) {
      this.#scheduleImmediate();
    }
  }

  /** Arm a 0 ms flush so the key handler never does network work directly. */
  #scheduleImmediate(): void {
    if (
      this.#closed ||
      this.#immediateTimer !== null ||
      this.#sending ||
      this.#retryTimer !== null
    ) {
      return;
    }
    this.#immediateTimer = this.#timers.setTimeout(() => {
      this.#immediateTimer = null;
      this.#flush();
    }, 0);
  }

  /** Send the whole ready queue as one batch, single-flight. */
  #flush(): void {
    if (this.#closed || this.#sending || this.#retryTimer !== null) {
      return;
    }
    if (this.#ready.length === 0) {
      return;
    }
    const batch = this.#ready.splice(0, this.#ready.length);
    this.#sending = true;
    this.#transport.send(this.#blockId, { events: batch }).then(
      () => {
        this.#onSendSuccess();
      },
      () => {
        this.#onSendError(batch);
      },
    );
  }

  #onSendSuccess(): void {
    this.#sending = false;
    this.#backoffExponent = 0;
    if (!this.#closed && this.#ready.length > 0) {
      this.#scheduleImmediate();
    }
  }

  #onSendError(batch: BufferedRow[]): void {
    this.#ready.unshift(...batch);
    this.#sending = false;
    if (this.#closed) {
      return;
    }
    const delay = Math.min(
      this.#config.backoffBaseMs * 2 ** this.#backoffExponent,
      this.#config.backoffMaxMs,
    );
    this.#backoffExponent += 1;
    this.#retryTimer = this.#timers.setTimeout(() => {
      this.#retryTimer = null;
      this.#flush();
    }, delay);
  }

  #beaconRemaining(): void {
    if (this.#closed) {
      return;
    }
    const remaining: BufferedRow[] = [...this.#ready, ...this.#pending.values()];
    if (remaining.length === 0) {
      return;
    }
    this.#transport.sendBeacon(this.#blockId, { events: remaining });
  }
}
