# D28: Candidate observation threshold is 15, not section 3.4's "at least 20"

- Date: 2026-10-21
- Status: accepted
- Task: T2.2 (assignment.py)

## Context

Section 3.4 step 1 requires a candidate bigram to have "at least 20 first-attempt observations in
the two baseline sessions". Under T1.8 option A (its "Owner decision on session length") each
baseline session types one part of form A (~2,700 chars), and `baseline_min_occurrences = 15`
(migration 0002). The T1.8 plan showed the coverage-efficient composer reaches every tracked
bigram's 15 combined occurrences with a small margin (measured ~20), but the design's literal "20"
is above the composed target, so a strict "≥ 20" filter could drop most tracked bigrams and leave
a near-empty candidate pool. T1.8 flagged that "that threshold must be revisited (lowered to match
`baseline_min_occurrences`, or the candidate pool accepted as smaller) by the assignment task
(T2.2) and recorded in an ADR" (owner-decisions.md #6). Section 17.3: "Any change to a decision
gets a short ADR in docs/decisions/."

## Decision

| ID | Decision | Choice | Why | Revisit if |
|---|---|---|---|---|
| D28 | Candidate observation threshold for 3.4 step 1 | The candidate threshold is `assignment_min_observations = 15` (a new `experiment_config` key, migration 0005), equal to `baseline_min_occurrences`, not the design's literal 20. A tracked bigram qualifies when its pooled first-attempt attempts over the two completed baseline sessions are `>= 15`. This deviates from section 3.4 step 1's "at least 20 first-attempt observations". | The baseline composer (T1.8 option A) targets 15 combined occurrences per tracked bigram, so a strict "≥ 20" would disqualify most tracked bigrams and empty the candidate pool, breaking assignment. 15 keeps the pool full; the extra ranking noise from a few fewer observations is absorbed by the strength-20 empirical-Bayes prior (section 3.4 step 2), which is exactly why that prior exists. | The owner later types both parts of form A per baseline session (≈ 30 occurrences per bigram): raise the threshold back toward 20. |

## Consequences

- `assignment.py` filters candidates with `attempts >= assignment_min_observations` (15); the key
  is frozen with the rest of the config at M3 (T3.5).
- Ranking is slightly noisier per bigram than a 20-observation pool would give; the strength-20
  Beta prior centred on the participant's overall error rate keeps an under-observed bigram from
  ranking first (the design's stated intent for the prior).
- `docs/analysis-plan.md` cites D28 on its "at least 20 first-attempt observations" line. The
  separate exclusion rule "bigrams with fewer than 20 retest attempts" (section 15.1 / D23) is a
  different rule about the retest and is unchanged.
- Section 3.4 is not edited; this ADR records the deviation.
