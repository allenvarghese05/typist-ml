# Typist-ML Analysis Plan

Status: draft skeleton — not pre-registered. Pre-registration (dated, per D20) happens in T3.6.

This is the analysis plan that design doc section 15.1 asks for and that D20 pre-registers:
"Commit docs/analysis-plan.md with the date before the first practice session". It was drafted in
T0.6 from the design doc, v1.0 ([PDF](design/Typist-ML_Technical_Design.pdf)). Section numbers
refer to that document; D01 to D20 are in its section 2, and later decisions are in
[decisions/](decisions/). The exclusion rules below are settled in
[D23 (analysis plan definitions)](decisions/D23-analysis-plan-definitions.md). Values that the
design leaves to milestone M3 are marked "to be fixed in T3.6" and listed under Pre-registration.

The plan states no expected results and holds no participant data. The honesty rule of section 1
applies to everything reported under it: "No WASM claim, no improvement claim until real numbers
exist, results are reported as descriptive per-participant changes, and if the heuristic or the
control does as well as the LLM, that is the finding."

## Study Design and Definitions

- **Within-person design (D01).** "Each participant's weak bigrams are split into 4 sets; each set
  is assigned one arm". The unit of comparison is a bigram set within one participant.
- **Arms (D03).** control, heuristic, markov and llm. The control set gets no targeted drills
  (D02). D02's random-text block of equal length is practice, not a comparison: "versus the
  control set" always means the held-out control bigram set.
- **Weak bigrams (section 3.4).** A candidate needs "at least 20 first-attempt observations in the
  two baseline sessions". Candidates are ranked with a Beta prior "centred on the participant's
  overall bigram error rate with strength 20 (empirical Bayes)", and the top 16 are taken (4 per
  set). They are split into sets by rank, snake split and a seeded shuffle, and frozen before
  practice (D04). This ranking prior only chooses bigrams; outcomes use the Jeffreys prior below.
- **Schedule (section 3.2).** Baseline: two sessions on form A (day 0 and 1). Sets are assigned
  and frozen at the end of day 1. Practice: N sessions from day 2 (design default N = 10, days 2
  to 11; to be fixed in T3.6). Retest: two sessions on form B (day 12 and 13 with the default N),
  with "at least 40 attempts per tracked bigram". Then the debrief.
- **Phases.** Baseline means both form A sessions and retest means both form B sessions. Every
  outcome pools the two sessions of a phase.
- **Tracked bigrams (D13, section 12.3).** Letter-letter bigrams only. A bigram across a space is
  not tracked.
- **Attempt and error (D14, section 12.3).** An attempt of bigram (a, b) is counted only when
  first-attempt keystrokes exist for both characters, a was correct on its first attempt, and no
  backspace happened between them. An error is a first-attempt substitution at b in such an
  attempt. These are the `attempts` and `errors` of `bigram_stats` (section 8.1). Attribution runs
  only in Python (`services/api/src/typist/services/attribution.py`), and
  `services/api/tests/fixtures/golden_session.json` is the source of truth for what counts as an
  error.
- **Inter-key interval (IKI; D15, section 12.3).** Press to press. Bigram (a, b) gives an IKI
  sample only for a clean, correct pair in which b directly follows a (`b.seq == a.seq + 1`) and
  b is not after a pause (`not b.after_pause`).
- **Pause (section 12.2).** "IKI over 2000 ms, or first key after a blur".

## Primary Outcome

The targeting effect on error rate for the heuristic, Markov and LLM sets, each versus the control
set (sections 3.5 and 15.1, D05). Each participant has three primary comparisons (one in two-set
mode).

For one participant, set `s` and phase `t` (baseline or retest), pool the errors and attempts over
the set's bigrams, after the exclusions below:

- Set error rate: `p(s, t) = errors(s, t) / attempts(s, t)`.
- Set error rate change (section 3.5, "retest minus baseline"):
  `d(s) = p(s, retest) - p(s, baseline)`.
- Targeting effect (section 3.5, "difference in differences"): `E(s) = d(s) - d(control)`, for
  `s` in heuristic, markov and llm.

Method (section 3.5):

- For each set and phase, report errors, attempts and a 95% interval from the Beta posterior with
  the Jeffreys prior, `Beta(errors + 1/2, attempts - errors + 1/2)`. The interval runs from the
  posterior's 2.5th to its 97.5th percentile (the equal-tailed Jeffreys interval).
- For the targeting effect, "draw samples from the four posteriors" (set `s` and the control set,
  each at baseline and retest), compute `E(s)` for each draw, and "report the median effect and
  the share of samples below zero". The number of draws and the seed are to be fixed in T3.6. The
  draws come from a seeded generator passed in by the caller, and the seed is reported.
- Sign convention: a fall in error rate is negative. `E(s) < 0` means set `s` improved more (or
  worsened less) than the control set, so the share of samples below zero is the share of draws
  in which the targeted set did better than the control set.
- "This is a description of one or two people, not a significance test. The write-up states the
  number of participants, sessions and keystrokes plainly." No significance claims (section 18).
- The README chart (section 15.3) shows the per-set error rate change with intervals, with the
  control set marked.

## Key Secondary Outcome

The same targeting effect for median IKI (section 15.1, D05). Section 3.5 defines the set IKI
change as "Median inter-key interval over the set's bigrams, retest minus baseline, minus the
control set's change". Timing is the key secondary because it "is far more sensitive with small
counts" (D05).

- `m(s, t)`: the median, in ms, of all IKI samples of the set's bigrams, pooled over both sessions
  of phase `t`, after the exclusions below (a pause gives no sample).
- IKI change: `c(s) = m(s, retest) - m(s, baseline)`.
- IKI targeting effect: `F(s) = c(s) - c(control)`, for `s` in heuristic, markov and llm.
- Same sign convention: `F(s) < 0` means set `s` got faster, relative to its baseline, than the
  control set did.
- For each set and phase, report `m(s, t)` and the number of IKI samples.
- The design gives no interval method for IKI. How its uncertainty is described is to be fixed in
  T3.6.

## Secondary Measures from Section 3.5

Section 3.5 lists four more measures. They do not answer the research question. Under section 15.1
("Everything else is exploratory and labelled as such") the write-up labels each one "exploratory"
and states its section 3.5 role.

| Measure | Definition (section 3.5) | Role (section 3.5) |
|---|---|---|
| Overall WPM and accuracy | Session-level, baseline versus retest | Check that speed was not lost elsewhere |
| Instrumentation overhead | Handler time and dispatch lag per keystroke, p50, p95, p99 | Engineering claim |
| LLM generation | Tokens per second, acceptance rate, attempts per accepted drill | Engineering claim |
| Drill quality | Target density, mean word length, real-word ratio per arm | Checks fairness between arms |

- The README reports overhead p95 and LLM tokens per second as measured values, and a table of
  arm, drills, mean density, real-word ratio and acceptance rate (section 15.3).
- The drill density range (design default 0.15 to 0.40, "Calibrated at M3") is to be fixed in
  T3.6.

## Exclusions

Section 15.1: "abandoned sessions, pauses, bigrams with fewer than 20 retest attempts (reported,
not silently dropped)". The rules below are settled in D23 (analysis plan definitions).

1. **Abandoned sessions, every phase.** A session becomes `abandoned` "if a session is left
   unfinished for more than 30 minutes" (section 9.3). "Abandoned practice sessions do not count
   toward N, and their keystrokes are kept but excluded from outcome analysis" (section 9.3). The
   same rule applies to baseline and retest sessions: their keystrokes are kept but excluded from
   outcome analysis. Whether an abandoned baseline or retest session is run again, and which
   sessions then count, is to be fixed in T3.6.
2. **Pauses, IKI only.** A pause is "IKI over 2000 ms, or first key after a blur", and it is
   "Excluded from IKI statistics, still counted for errors" (section 12.2). A keystroke after a
   pause still counts as an attempt, and as an error if it is one, but gives no IKI sample.
3. **Bigrams with fewer than 20 retest attempts.** Attempts are counted per tracked bigram, pooled
   over both retest sessions, as defined above (the attempts the primary outcome counts). A bigram
   below 20 is dropped from its set in both baseline and retest, for the primary and the key
   secondary outcome. The retest is built to give "at least 40 attempts per tracked bigram"
   (section 3.2), so this should only happen after a lost session or when attribution skips many
   pairs.
4. **Reported, not silently dropped.** For each participant the write-up lists every excluded
   session (its phase and the reason), every dropped bigram (its set and its retest attempts) and
   the number of IKI samples excluded as pauses per set and phase.

No other data is excluded from the primary and key secondary outcomes. Any further exclusion is
logged under Deviations Log or Amendments. Keystrokes are never deleted; exclusions apply at
analysis time only.

## Exploratory Analysis

Section 15.1: "Everything else is exploratory and labelled as such." Anything not defined under
Primary Outcome or Key Secondary Outcome is exploratory, including:

- comparisons between targeted arms, for example LLM versus heuristic (section 1 asks: "does a
  small on-device language model write better drills than a dictionary heuristic or a Markov
  chain?");
- any figure that pools participants (results are "descriptive per-participant changes", section
  1);
- changes for single bigrams, for bigrams outside the sets, and on the random-text block (D02);
- the secondary measures from section 3.5 above;
- any analysis chosen after seeing data.

Each exploratory result carries the word "exploratory" wherever it appears: the dashboard (section
15.2), the README (section 15.3) and the notebooks.

## Participants and Blinding

- Participants are stored by alias only; no name, email or free text is stored (section 4.2).
  This plan names no participant.
- The builder takes part and is not blind: "The builder is flagged as unblinded" (D18), recorded
  in `participants.is_builder` and `is_blinded` (section 8.1). The practice UI labels blocks 1 to
  4 and never names the arm (D18).
- Every result is reported per participant. Section 18: "Flag builder data; show the second
  participant separately."
- Whether there is a second participant is to be fixed in T3.6 (design default "Builder only",
  decided "Before baseline", section 20.1). With the builder only, all data is unblinded, and the
  write-up says so.
- If the second participant drops out, the builder's data is "Still a valid within-person result
  for one person; say so" (section 18).

## Two-Set Mode Contingency

Section 16: "If M3 slips, run the pilot in 2-set mode (control and heuristic, 8 bigrams each),
which the config supports with `arms_enabled`." In two-set mode:

- the only primary comparison is heuristic versus control, and the only key secondary comparison
  is the same;
- the Markov and LLM comparisons are not run, and the write-up says so instead of leaving them out
  silently;
- every definition and exclusion above applies unchanged.

Which mode the pilot runs is to be fixed in T3.6 (`arms_enabled` in `experiment_config`).

## Twelve-Bigram Fallback

Section 3.4: "Take the top 16 (4 per set). If fewer than 16 qualify, take 12 (3 per set) and log
it." Outcomes pool over a set's bigrams, so every definition above holds with 3 bigrams per set;
each set then has fewer attempts, and its intervals are wider. The write-up states the number of
bigrams per set for each participant. How the fallback applies in two-set mode is not stated in the
design and is to be fixed in T3.6.

## Missed Days and the Three-Day Baseline Rule

Section 3.2: "baseline must finish no more than 3 days before the first practice session ...
Missed practice days are allowed but logged; the retest happens after N completed practice
sessions, not N calendar days."

- Only completed practice sessions count toward N; abandoned ones do not (section 9.3).
- The write-up reports, per participant, the missed practice days and the number of days between
  the end of baseline and the first practice session.
- If the baseline has to be redone, which baseline sessions count is to be fixed in T3.6.

## Known Weaknesses and Limitations

From section 3.5 ("Known weakness") and section 18. The counts quoted here are design estimates,
not results.

- Error rates are low, "often under 5%". With "about 200 attempts per set at retest, a set may
  show only around 10 errors", which is why timing is the key secondary outcome.
- Spill-over between sets "makes effects look smaller, not larger".
- "Markov drills use pseudo-words while tests use real words; and the builder is not blind."
- One or two participants: no significance claims (section 18).
- The write-up has "A limitations paragraph that states N, sessions and keystrokes" (section
  15.3), where N is the number of participants (section 3.5).

## Pre-registration

Section 15.1: "Commit this plan with a date before the first practice session (D20)." D20 exists
because pre-registration "Stops outcome-shopping after seeing data".

This draft is not the pre-registration. Task T3.6 ("Commit the dated analysis plan", done when the
"Commit exists before the first practice session") turns it into one:

1. fill in every value listed below;
2. replace the status line with a dated one, and write the pre-registration date in this file;
3. commit before the first practice session, so that the date in the file and the commit date
   match (D20's "with the date" means both, T0.6 owner answer 4).

Milestone M3 is done when "All four arms produce valid drills; config and analysis plan frozen".
After the pre-registration commit this plan changes only through the Amendments section.

### Values to Be Fixed in T3.6

| Item | Design default or rule | Source |
|---|---|---|
| Practice sessions N | 10, "Freeze at M3" | Sections 3.2, 20.1 |
| Second participant | "Builder only", decided "Before baseline" | Section 20.1 |
| Arms enabled (four sets or two-set mode) | Four sets; two-set mode "If M3 slips" | Section 16, `arms_enabled` |
| Drill density range | 0.15 to 0.40, "Calibrated at M3" | Section 20.1 |
| Final model | Llama-3.2-1B-Instruct-4bit, "Bake-off at M3" | Section 20.1 |
| Number of posterior draws and their seed | Not set in the design | Section 3.5, CLAUDE.md |
| Uncertainty description for the IKI effect | Not set in the design | Section 3.5 |
| Re-running an abandoned baseline or retest session; which sessions count after a redone baseline | Not set in the design | Sections 3.2, 9.3 |
| Twelve-bigram fallback in two-set mode | Not set in the design | Sections 3.4, 16 |

## Deviations Log

The pilot runbook (section 16): "Do not change code that affects telemetry, generation or text
composition during the pilot. Bug fixes that do are logged as deviations in the write-up." Each
deviation is logged here with its date, what changed, the sessions affected, and whether stored
statistics were recomputed (`typist stats recompute`, section 6.2).

No deviations yet.

## Amendments

Dated changes to this plan after the T3.6 pre-registration commit are logged here, one entry per
change (D05: "Before retest only, by editing the analysis plan"); a change to a decision also gets
an ADR (section 17.3).

No amendments yet.
