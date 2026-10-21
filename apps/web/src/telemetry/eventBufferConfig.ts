/**
 * Transport parameters for EventBuffer (design doc 12.4). These are durability knobs, not
 * experiment parameters, so they live here and never in experiment_config (T1.6 owner answer 7).
 * All durations are milliseconds.
 */
export interface EventBufferConfig {
  /** A row with no key-up is marked ready this long after its keydown, with t_up_ms left null. */
  readonly keyUpWaitMs: number;
  /** Flush when this many ready rows have accumulated. */
  readonly flushRows: number;
  /** Flush ready rows on this fixed interval. */
  readonly flushIntervalMs: number;
  /** First retry delay; it doubles each failure (backoffBaseMs * 2 ** n). */
  readonly backoffBaseMs: number;
  /** Ceiling for the retry delay. */
  readonly backoffMaxMs: number;
}

/** The design doc 12.4 defaults (T1.6 owner answer 7). */
export const DEFAULT_EVENT_BUFFER_CONFIG: EventBufferConfig = {
  keyUpWaitMs: 2000,
  flushRows: 50,
  flushIntervalMs: 5000,
  backoffBaseMs: 500,
  backoffMaxMs: 8000,
};
