# Owner decisions carried across tasks

Standing answers from the owner. The analyst copies the relevant ones into each brief's
"## Owner answers" so the pipeline does not stop to ask again.

## 2026-10-21 (after M1 closed)

1. **Participants.** Only the owner (builder) for the pilot, on the owner's Mac. The owner's
   participant row is `is_builder = true`, `is_blinded = false`. Second-participant features
   (blinding, separate reporting) stay in the code but are not exercised.
2. **Consent.** A basic one-paragraph local consent screen; recording `consent_at` is enough.
3. **Model runtime.** Llama 3.2 1B 4-bit via mlx-lm on the owner's Mac (disk available).
4. **Pilot.** 14 days of daily typing, starting as soon as M3 freezes config.
5. **Daily visibility.** The owner wants to see progress every day. Pull a minimal "Trend" view
   forward into M2: `typist check --pid` prints per-session WPM, accuracy and per-set error rate
   on practice text alongside the data-quality checks, and the admin page (T2.9) shows the same
   table. This adds no experiment semantics; the primary outcome is still baseline vs retest and
   nothing frozen may change mid-pilot.
6. **T1.8 option A consequence.** T2.2 must reconcile section 3.4's "at least 20 first-attempt
   observations" with `baseline_min_occurrences = 15` through an ADR.
7. **bigram_stats already exists** (created in T1.9, migration 0003). T2.1 adds only the other
   four tables.
