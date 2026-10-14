# D26: Session WPM uses elapsed time with pauses included; idle limit on a block

- Date: 2026-10-13
- Status: accepted
- Task: T1.2 (recorded); T1.5 and T1.9 (built)

## Context

Section 12.3 says: "Session WPM is correct first-attempt characters divided by 5, divided by
minutes of active typing (pauses removed)." Section 12.2 defines a pause as "IKI over 2000 ms,
or first key after a blur", excluded from IKI statistics and still counted for errors. While
drafting the golden fixture (T1.2), the owner reviewed the WPM rule and decided on 2026-10-13
(T1.2 brief, "Amendments after plan approval") that the WPM timer must not stop for pauses, and
added a limit on idle time within a block. Section 17.3: "Any change to a decision gets a short
ADR in docs/decisions/."

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D26 | Session WPM time base, and idle limit | WPM = correct first-attempt characters / 5 / elapsed minutes. Elapsed time runs continuously from the first keystroke's press (`t_down_ms` of the block's first row) to the press of the final character; for a block that never reaches the end, to the last row's press. Pauses and time away from the window (blur) are included, not removed. This deviates from section 12.3's "minutes of active typing (pauses removed)". Pair speed is unchanged: an IKI sample is still skipped when `b.after_pause` is true or the press-to-press gap is over 2000 ms (D24, D23(a)). Idle rule: after 5 s with no keypress the block shows a warning while the timer keeps running; after 10 s with no keypress the block is abandoned and must be restarted. Blur counts as idle. Keystroke rows of an abandoned block are kept (append-only) and the block is marked abandoned. | Owner: WPM is the score shown to the user, so it reflects real elapsed time (the way Monkeytype times a test, used as a behaviour reference only). Pair speed (IKI) is what the system uses to learn the typist's patterns and train them, so it is kept separate and still excludes pauses. The idle limit keeps a long pause from silently distorting the score or the block. | Pilot data shows the idle limit abandons too many blocks, or the WPM time base makes baseline and retest sessions incomparable |

## Consequences

- The golden fixture (T1.2) expects WPM on elapsed time: 55 correct first attempts / 5 / 0.5 min
  = 22, with no pause removed, while its IKI samples still skip the pauses.
- T1.9 computes `sessions.wpm` this way. Attribution (T1.7) and `bigram_stats` are unchanged.
- T1.5 builds the idle warning (5 s), the abandon-and-restart (10 s) and blur-as-idle. It must
  decide how an abandoned block is marked and how its restart is stored: `session_blocks` (T1.1)
  has no status column, and `UNIQUE (session_id, block_index)` stops a second row with the same
  index. The owner has decided that abandoned and restarted blocks are tracked in the database,
  through a status column or a new table in migration 0002. The design is settled first, when the
  idle rule is designed (T1.5, or a small dedicated task before it).
- No press-to-press gap inside a completed block can exceed 10 s, so a pause adds at most about
  10 s to a block's elapsed time.
- `docs/analysis-plan.md` (draft until T3.6): the exploratory measure "Overall WPM and accuracy"
  must cite this definition when the plan is pre-registered in T3.6, and T3.6 must say whether
  rows of an idle-abandoned block are excluded from outcome analysis (Exclusions rule 1 covers
  abandoned sessions only). Exclusion rule 2 ("Pauses, IKI only") already agrees with this ADR.
- Free-practice modes (timed or word-count tests) are not built now. If added later they are a
  separate feature whose data stays out of the experiment's analysis.
- Section 12.3 is not edited; this ADR records the deviation.
