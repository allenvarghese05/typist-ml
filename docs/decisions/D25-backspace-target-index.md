# D25: Backspace rows record the post-move cursor position

- Date: 2026-10-06
- Status: accepted
- Task: T1.2

## Context

Section 8.1 defines `keystroke_events.target_index` as "Cursor position when the key was
pressed". For a printable key that is the position it is compared with. A Backspace moves the
cursor back one position, so "when the key was pressed" could mean the position before the move
or the position it erases. The golden fixture (T1.2) must pin one reading, because TextCursor
(T1.3) and every stored Backspace row must agree. The owner decided this on 2026-10-06 (T1.2
owner answer 8a, follow-up 1). Section 17.3: "Any change to a decision gets a short ADR in
docs/decisions/."

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D25 | target_index on Backspace rows | For Backspace rows, target_index records the post-move cursor position, not the pre-press position 8.1's general definition implies. | A Backspace row's meaningful position is what it erased/landed on, not where the cursor was a moment before — the general rule was written with forward-typing keystrokes in mind and doesn't cleanly apply to a key that moves the cursor backward. | A later key moves the cursor in another way (for example word delete), which is out of scope in v1 (D13) |

## Consequences

- A Backspace pressed with the cursor at index i > 0 is stored with `target_index = i - 1`, the
  position it erased. A Backspace at index 0 erases nothing, is still stored as a row with
  `outcome = "backspace"` and `target_index = 0`, and does not count as "a backspace happened
  between a and b" for any pair (T1.2 owner answer 8b).
- Backspace rows keep `expected_char` and `first_attempt` NULL (T1.1 owner answer 5).
- TextCursor (T1.3) reports this position for Backspace; the golden fixture
  (`services/api/tests/fixtures/golden_session.json`) pins it on every Backspace row.
- Attribution (T1.7) uses Backspace rows only through their `seq` (the "between a and b" test),
  so this choice changes no bigram statistic.
- Section 8.1 is not edited; this ADR records the narrower meaning for Backspace rows.
