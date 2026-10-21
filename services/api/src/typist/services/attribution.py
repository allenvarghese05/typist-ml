"""Bigram attribution: the only place a keystroke is attributed to a bigram (CLAUDE.md).

Implements design doc section 12.3 verbatim, with two amendments the golden fixture pins:

* D24 (docs/decisions/D24): a pair is "paused" when the second key carries after_pause OR the
  press-to-press gap exceeds 2000 ms. The threshold is strict: a gap of exactly 2000 ms is NOT a
  pause and still yields an IKI sample (fixture case o, bigram "ld").
* D23(a) (docs/decisions/D23): a paused pair, and an error pair, still count an attempt (and an
  error when the second key is an error). Only the IKI *sample* is dropped.

For each position j >= 1 where target[j-1] and target[j] are both letters (D13): a is the
first-attempt keystroke at j-1 and b the first-attempt keystroke at j. The pair is skipped, in this
order, when a or b is missing, when a is not correct, or when a Backspace row lies strictly between
a.seq and b.seq. Otherwise it is an attempt; an error when b is an error; otherwise an IKI sample
b.t_down_ms - a.t_down_ms when b is adjacent (b.seq == a.seq + 1) and the pair is not paused.

iki_median_ms is statistics.median over the raw samples (mean of the two middle values on an even
count, the sorted middle on an odd count; owner answer 6, derivation A.6); it is None exactly when
iki_n == 0. Bigrams with zero attempts are omitted. attribute_block returns a list sorted by bigram.
Pairs never cross a block boundary: this function attributes one block; T1.9 aggregates a session's
blocks by pooling raw samples (not a median of medians), which is why attribute_block_samples is
exposed. The browser never attributes bigrams (CLAUDE.md).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from sqlmodel import Session, col, select

from typist.models import KeystrokeEvent, SessionBlock

PAUSE_GAP_MS = 2000.0
"""Press-to-press gap above which a pair is a pause (D24). Strict: exactly 2000 ms is not a pause."""


@dataclass(frozen=True)
class BigramSamples:
    """Raw per-bigram attribution for one block: counts plus the IKI samples before any median.

    attempts and errors follow D23(a) (paused and error pairs still count). iki_samples holds the
    clean, unpaused, adjacent samples in a.seq order. Exposed so T1.9 can pool samples across a
    session's blocks before taking one median (owner answer 3).
    """

    bigram: str
    attempts: int
    errors: int
    iki_samples: tuple[float, ...]


@dataclass(frozen=True)
class BigramStat:
    """Reduced per-bigram stats matching the section 8.1 bigram_stats columns the fixture asserts.

    iki_median_ms is statistics.median over the samples, or None when iki_n == 0; iki_n is the
    sample count. The browser computes display stats only; this is the authoritative computation.
    """

    bigram: str
    attempts: int
    errors: int
    iki_median_ms: float | None
    iki_n: int


def _is_letter(char: str) -> bool:
    """True for a single lowercase a-z character (D13 tracks letter-letter bigrams only)."""
    return "a" <= char <= "z"


def attribute_block_samples(
    target_text: str, rows: Sequence[KeystrokeEvent]
) -> dict[str, BigramSamples]:
    """Attribute one block's rows to bigrams, returning raw counts and IKI samples per bigram.

    rows may arrive in any order; they are sorted by seq internally. Only bigrams with at least one
    attempt appear in the result. Implements design doc 12.3 with D24 and D23(a) (see the module
    docstring). This is the low-level form; attribute_block reduces it to medians.
    """
    ordered = sorted(rows, key=lambda row: row.seq)
    first_attempt_at: dict[int, KeystrokeEvent] = {}
    backspace_seqs: list[int] = []
    for row in ordered:
        if row.outcome == "backspace":
            backspace_seqs.append(row.seq)
        elif row.first_attempt:
            first_attempt_at[row.target_index] = row

    attempts: dict[str, int] = {}
    errors: dict[str, int] = {}
    samples: dict[str, list[float]] = {}

    for j in range(1, len(target_text)):
        if not (_is_letter(target_text[j - 1]) and _is_letter(target_text[j])):
            continue
        a = first_attempt_at.get(j - 1)
        b = first_attempt_at.get(j)
        if a is None or b is None:
            continue
        if a.outcome != "correct":
            continue
        if any(a.seq < seq < b.seq for seq in backspace_seqs):
            continue
        bigram = target_text[j - 1] + target_text[j]
        attempts[bigram] = attempts.get(bigram, 0) + 1
        errors.setdefault(bigram, 0)
        samples.setdefault(bigram, [])
        if b.outcome == "error":
            errors[bigram] += 1
        elif b.seq == a.seq + 1:
            gap = b.t_down_ms - a.t_down_ms
            paused = b.after_pause or gap > PAUSE_GAP_MS
            if not paused:
                samples[bigram].append(gap)

    return {
        bigram: BigramSamples(
            bigram=bigram,
            attempts=count,
            errors=errors[bigram],
            iki_samples=tuple(samples[bigram]),
        )
        for bigram, count in attempts.items()
    }


def attribute_block(target_text: str, rows: Sequence[KeystrokeEvent]) -> list[BigramStat]:
    """Attribute one block and reduce to BigramStat, sorted by bigram.

    Bigrams with zero attempts are omitted. iki_median_ms is statistics.median over the samples, or
    None when there are none. rows may arrive in any order (sorted internally), so the result is
    order-independent.
    """
    per_bigram = attribute_block_samples(target_text, rows)
    stats: list[BigramStat] = []
    for bigram in sorted(per_bigram):
        entry = per_bigram[bigram]
        iki_n = len(entry.iki_samples)
        iki_median_ms = median(entry.iki_samples) if iki_n > 0 else None
        stats.append(
            BigramStat(
                bigram=bigram,
                attempts=entry.attempts,
                errors=entry.errors,
                iki_median_ms=iki_median_ms,
                iki_n=iki_n,
            )
        )
    return stats


def attribute_block_from_db(session: Session, block_id: str) -> list[BigramStat]:
    """Load one block's target_text and keystroke rows and attribute them (design doc 12.3).

    Raises LookupError if no session_blocks row has the id. Otherwise delegates to attribute_block,
    so the DB path and the in-memory path produce identical results.
    """
    block = session.get(SessionBlock, block_id)
    if block is None:
        raise LookupError(f"no session_blocks row with id {block_id!r}")
    rows = session.exec(
        select(KeystrokeEvent).where(col(KeystrokeEvent.block_id) == block_id)
    ).all()
    return attribute_block(block.target_text, rows)
