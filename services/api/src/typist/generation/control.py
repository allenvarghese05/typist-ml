"""The control drill generator: frequency-weighted random words, no targets (design doc 3.3, 13.2).

ControlGenerator draws words from the control pool -- the pool_size most frequent a-z words, which is
index.words[:pool_size] because words.json is rank-ordered (owner answer 1) -- weighted by
sqrt(frequency) (13.2), capping each word at _MAX_USES_PER_DRILL uses per drill so it can never trip
the validator's word_repeat rule (owner answer 8: 2 < the config's 3). It fills up to
spec.length_chars at a word boundary without exceeding it (owner answer 5); measured length is
299-300 for length_chars 300, safely above the 270 floor. It targets nothing, so target_bigrams is
empty and the validator skips density/coverage (3.3). The only randomness is random.Random(spec.seed)
(owner answer 2). Pure: returns one DrillCandidate per call (text == raw_output; owner answer 3) and
writes no DB rows (T2.5 validates and persists).
"""

import math
import random
from typing import Final

from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm, DrillCandidate, DrillSpec
from typist.generation.sampling import weighted_choice
from typist.generation.validator import ValidatorConfig

_VERSION: Final = "control-v1"
# 13.3 step-5 cap, kept below the validator's drill_max_word_repeats (3) so control never fails
# word_repeat; not an experiment knob (owner answer 7), so a module literal like the composer's.
_MAX_USES_PER_DRILL: Final = 2


class ControlGenerator:
    """Frequency-weighted random-word generator for the control arm (design doc 3.3, 13.2)."""

    arm = Arm.CONTROL
    version = _VERSION

    def __init__(
        self, index: WordIndex, config: ValidatorConfig, pool_size: int
    ) -> None:
        """index supplies the ranked words and their frequencies; config is accepted for a uniform
        generator constructor (T2.5 wires every arm the same way) though control reads nothing from
        it; pool_size is control_word_pool (owner answer 1) -- the pool is index.words[:pool_size].
        Precomputes the pool and its sqrt-frequency weights once."""
        self._config = config
        self._pool: tuple[str, ...] = index.words[:pool_size]
        self._sqrt_freq: dict[str, float] = {
            word: math.sqrt(index.frequencies[word]) for word in self._pool
        }

    def generate(self, spec: DrillSpec) -> DrillCandidate:
        """Compose one control drill and return it as a DrillCandidate (text == raw_output).

        Draws words from the pool weighted by sqrt(frequency) with a seeded rng
        (random.Random(spec.seed)); each word is used at most _MAX_USES_PER_DRILL times; a word is
        added only if it still fits within spec.length_chars (counting the joining space), so the
        joined text is <= spec.length_chars at a word boundary with no leading/trailing/doubled
        space. Stops when no eligible word fits. Deterministic for a given spec.seed.
        """
        rng = random.Random(spec.seed)
        used: dict[str, int] = {}
        words: list[str] = []
        length = 0
        while True:
            fits = [
                word
                for word in self._pool
                if used.get(word, 0) < _MAX_USES_PER_DRILL
                and length + len(word) + (1 if words else 0) <= spec.length_chars
            ]
            if not fits:
                break
            weights = [self._sqrt_freq[word] for word in fits]
            word = weighted_choice(rng, fits, weights)
            used[word] = used.get(word, 0) + 1
            length += len(word) + (1 if words else 0)
            words.append(word)
        text = " ".join(words)
        return DrillCandidate(
            text=text,
            raw_output=text,
            generator_version=_VERSION,
            seed=spec.seed,
        )
