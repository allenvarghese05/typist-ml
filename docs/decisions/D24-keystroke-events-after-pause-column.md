# D24: keystroke_events gets an after_pause column

- Date: 2026-09-29
- Status: accepted
- Task: T1.1

## Context

Section 12.2 defines a pause as "IKI over 2000 ms, or first key after a blur", and says pauses
are "Excluded from IKI statistics, still counted for errors". Section 12.1 says "On window blur:
pause the block, mark the next keystroke as following a pause", and the attribution pseudocode
in section 12.3 tests `b.after_pause`. The `keystroke_events` table in section 8.1 has no column
for this, and the `KeystrokeEvent` type in Figure 5 (section 9.2) has no field for it.

The IKI half of the definition can be recomputed from the stored press times. The blur half
cannot: a key typed 1.8 s after the window regains focus has an IKI under 2000 ms, and no 8.1
column shows that the window was blurred in between. `keystroke_events` is the raw data that
cannot be rebuilt (section 10.3), so the flag has to be stored when the key is captured. The
owner decided this on 2026-09-29 (T1.1 owner answer 4). Section 17.3: "Any change to a decision
gets a short ADR in docs/decisions/."

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D24 | Pause flag on keystroke_events | Add `after_pause BOOLEAN NOT NULL DEFAULT FALSE` to `keystroke_events`. It is true only for the first keystroke after the window regains focus following a blur (section 12.1). A long gap (IKI over 2000 ms) is not stored in this column; it is derived from the stored press times at analysis time. | It stores the one fact that cannot be recomputed later, and nothing that can | A pause source other than blur appears that the timestamps cannot show |

## Consequences

- Revision `0001_initial_schema` (T1.1) creates the column with a database default of false
  (0). The SQLModel class `KeystrokeEvent` has `after_pause: bool = False`.
- Attribution (T1.7) treats a pair as a pause when the second key has `after_pause` true or
  the press-to-press gap is over 2000 ms. The `b.after_pause` test in section 12.3 stands for
  both parts of the section 12.2 definition, not for the column alone.
- The browser client captures the flag and sends it with each keystroke, and the events endpoint
  (T1.6) stores it. Figure 5's `KeystrokeEvent` type gains this field.
- The golden fixture (T1.2, "includes errors, backspace, rollover, a pause") includes a
  keystroke with `after_pause` true.
- Section 8.1 is not edited; this ADR records the added column.
