"""Seeded, deterministic sampling helpers shared by the non-LLM generators (design doc 13.2, 13.3).

Both functions take a random.Random passed in by the caller (CLAUDE.md: randomness is always
seeded by the caller) and consume exactly one rng.random() draw, so a given rng state plus inputs
always yields the same item -- the determinism the acceptance requires. weighted_choice is 13.2's
frequency-weighted draw (the caller supplies the weights, e.g. sqrt(frequency)); softmax_choice is
13.3 step 4's softmax-over-top-50 at a given temperature, the same idiom as the baseline composer's
_choose_word (copied, not imported, so the frozen composer is untouched; owner answer 4). Pure: no
I/O, no mlx, importable on Linux CI.
"""

import math
import random
from collections.abc import Sequence


def weighted_choice[T](rng: random.Random, items: Sequence[T], weights: Sequence[float]) -> T:
    """Return one item chosen with probability proportional to its weight, using one rng draw.

    items and weights must be non-empty and the same length; every weight must be >= 0 and their
    sum must be > 0. Deterministic for a given rng state. The cumulative scan mirrors the composer's
    seeded selection; the final item is returned when floating-point rounding leaves the threshold
    exactly at the top of the cumulative sum.
    """
    threshold = rng.random() * sum(weights)
    cumulative = 0.0
    for item, weight in zip(items, weights, strict=True):
        cumulative += weight
        if threshold <= cumulative:
            return item
    return items[-1]


def softmax_choice[T](
    rng: random.Random,
    items: Sequence[T],
    scores: Sequence[float],
    temperature: float,
) -> T:
    """Return one item sampled from the softmax of scores at temperature, using one rng draw.

    items and scores must be non-empty and the same length; temperature must be > 0. Scores are
    shifted by their maximum before exponentiating (numerical stability; identical to the composer's
    _choose_word idiom, 13.3 step 4). Deterministic for a given rng state.
    """
    highest = max(scores)
    weights = [math.exp((score - highest) / temperature) for score in scores]
    threshold = rng.random() * sum(weights)
    cumulative = 0.0
    for item, weight in zip(items, weights, strict=True):
        cumulative += weight
        if threshold <= cumulative:
            return item
    return items[-1]
