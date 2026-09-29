# D23: Analysis plan exclusion definitions

- Date: 2026-09-29
- Status: accepted
- Task: T0.6

## Context

Design doc section 15.1 lists the analysis plan's exclusions as "abandoned sessions, pauses,
bigrams with fewer than 20 retest attempts (reported, not silently dropped)". The rest of the
design leaves three points open (T0.6 brief, open question 6):

- section 12.2 excludes pauses from IKI statistics but still counts them for errors, while 15.1
  lists pauses as an exclusion without that split;
- section 9.3 excludes abandoned practice sessions from outcome analysis but says nothing about
  abandoned baseline and retest sessions, which are the sessions the outcomes are computed from;
- 15.1 does not say how the 20 retest attempts are counted, or whether a bigram below it is
  dropped from retest only or from both phases.

The owner settled all three on 2026-09-29 (T0.6 owner answer 6). Section 17.3: "Any change to a
decision gets a short ADR in docs/decisions/." D01 to D20 are in design doc section 2; D21 and
later are in this directory. This D23 is separate from
[D23: one-time download of the model weights](D23-model-download.md).

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D23 | Analysis plan exclusions | (a) Pauses (section 12.2: "IKI over 2000 ms, or first key after a blur") are excluded from IKI statistics only and are still counted for errors. (b) Section 9.3's rule for abandoned practice sessions applies to every phase: the keystrokes of an abandoned baseline, practice or retest session are kept but excluded from outcome analysis. (c) "Fewer than 20 retest attempts" is counted per tracked bigram, pooled over both retest sessions, using the section 12.3 attempts that the primary outcome counts. A bigram below 20 is dropped from its set's comparison in both baseline and retest, for the primary and the key secondary outcome, and is listed in the write-up. | (a) matches section 12.2; (b) applies one rule to every session an outcome can come from; (c) keeps each set's baseline and retest over the same bigrams, so the difference in differences compares like with like | Before retest only, by editing the analysis plan (D05), with the change logged in its Amendments section |

## Consequences

- `docs/analysis-plan.md` (section Exclusions) states these rules. T3.6 pre-registers them with the
  rest of the plan.
- T4.1 (`analysis.py`) applies them at analysis time: sessions whose `sessions.status` is
  `abandoned` (section 8.1) are left out of every outcome in every phase, and bigrams below 20
  retest attempts are removed from their set before either phase is pooled. Keystroke rows are
  kept (`keystroke_events` rows are append-only, CLAUDE.md).
- Rule (a) needs no change to attribution: `bigram_stats.attempts` and `errors` follow section
  12.3, and `iki_median_ms` and `iki_n` already use "Only clean, correct pairs; pauses over 2000 ms
  excluded" (section 8.1).
- The write-up lists every excluded session and every dropped bigram (section 15.1, "reported, not
  silently dropped").
- Not decided here, and marked "to be fixed in T3.6" in the analysis plan: whether an abandoned
  baseline or retest session is run again, and which sessions count after a redone baseline.
