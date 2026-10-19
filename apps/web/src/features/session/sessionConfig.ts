/**
 * Block behaviour parameters kept out of logic (design doc 17.1; idle rule from D26). Durations
 * are milliseconds. The surface accepts overrides so tests can use short thresholds.
 */

/** No recorded keystroke for this long shows the idle warning while the block keeps running. */
export const IDLE_WARNING_MS = 5000;
/** No recorded keystroke for this long abandons the block; it must be restarted (D26). */
export const IDLE_ABANDON_MS = 10000;
