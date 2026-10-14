# D27: IKI and dwell are computed in the browser

- Date: 2026-10-14
- Status: accepted
- Task: T1.4 (recorded); T1.6 (built)

## Context

T1.2 answer 10a said `dwell_ms` and `iki_ms` are stored, computed by the service layer:
`dwell_ms` when the key-up arrives, `iki_ms` at insert time from the prior row's `t_down`.
`release_to_press_ms` is not stored (T1.1 answer 6). While scoping T1.4 (KeystrokeRecorder), the
owner decided in the T1.4 brief, "Owner answers" item 2 (2026-10-14), to move the computation of
the two stored values to the browser.

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D27 | Where `iki_ms` and `dwell_ms` are computed | The recorder computes `iki_ms` (from the previous recorded row's `t_down_ms`, null at seq 0) and `dwell_ms` (when the key-up arrives before the row leaves) and puts them in the row. The server's `record_key_up` computes dwell only for late key-ups. Whether T1.6 re-checks the browser values is T1.6's question. This refines T1.2 answer 10a: computation moves to the browser, and the server fills only late key-ups. | Owner decision in the T1.4 brief, Owner answers item 2. | T1.6 finds the browser values need re-checking on the server, or a late key-up path makes the split awkward |

## Consequences

- The values and their meaning are unchanged; only the place of computation moves.
- T1.6 must decide whether the server trusts or re-checks the browser's `iki_ms` and `dwell_ms`.
- Plan flag F6 of T1.4 records that no ADR was written inside that task; this ADR is that record.
- `release_to_press_ms` is unaffected: it is still not a stored row field (T1.2 answer 10a, T1.1
  answer 6).
