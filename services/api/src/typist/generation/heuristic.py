"""The heuristic drill generator: the 13.3 dictionary baseline the LLM must beat (design doc 13.3).

Per step HeuristicGenerator picks the target bigram with the lowest coverage counter (ties broken by
rng; owner answer 5), then softmax-samples one of the top _TOP_CANDIDATES eligible words ranked by
the 13.3 step-4 score (_word_score): (occurrences of the target in the word / number of letter
bigrams in the word) * log(frequency(word) / min_frequency), where min_frequency is the smallest
frequency in the index so the log is >= 0 and never flips the ranking (owner answer 5). Words are
skipped once used _MAX_USES_PER_DRILL times (13.3 step 5). A density governor keeps the drill inside
[spec.min_density, spec.max_density] without changing the 13.3 recipe: before each pick it compares
the running target density to the midpoint (spec.min_density + spec.max_density) / 2 and, if above,
picks a sqrt-frequency *filler* from the control pool that contains no target bigram instead of a
target word (owner answer 5; a greedy target-dense loop with no governor overshoots 0.40). The loop
terminates when the next word would exceed spec.length_chars (word boundary, <= length_chars). The
only randomness is random.Random(spec.seed) (owner answer 2). Pure: one DrillCandidate per call
(text == raw_output; owner answer 3); no DB write (T2.5 validates and persists). Per-target candidate
lists and scores are precomputed once per generate, so each step is O(words-per-target), never a
full-vocabulary scan (brief performance note).
"""

import math
import random
from typing import Final

from typist.corpus.word_index import WordIndex, word_bigrams
from typist.generation.base import Arm, DrillCandidate, DrillSpec
from typist.generation.sampling import softmax_choice, weighted_choice
from typist.generation.validator import ValidatorConfig

_VERSION: Final = "heuristic-v1"
# 13.3 algorithm constants (owner answer 7), module literals like the composer's.
_TEMPERATURE: Final = 0.5  # 13.3 step-4 softmax temperature.
_TOP_CANDIDATES: Final = 50  # 13.3 step-4 "sample one of the top 50".
_MAX_USES_PER_DRILL: Final = 2  # 13.3 step-5 "skip words already used twice".
_MIN_WORD_LEN: Final = 2  # 13.4 word-length range, applied to target and filler words.
_MAX_WORD_LEN: Final = 10


class HeuristicGenerator:
    """The 13.3 dictionary-baseline generator for the heuristic arm."""

    arm = Arm.HEURISTIC
    version = _VERSION

    def __init__(
        self, index: WordIndex, config: ValidatorConfig, pool_size: int
    ) -> None:
        """index supplies the words, frequencies and bigram index; config is accepted for a uniform
        generator constructor (T2.5) though the heuristic reads density bounds and length off the
        spec, not config; pool_size is control_word_pool, used for the filler pool (owner answers
        1, 5). Precomputes min_frequency, the 2-10-letter filler pool and its sqrt-frequency
        weights."""
        self._index = index
        self._config = config
        self._min_frequency = min(index.frequencies.values())
        self._filler_pool: tuple[str, ...] = tuple(
            word
            for word in index.words[:pool_size]
            if _MIN_WORD_LEN <= len(word) <= _MAX_WORD_LEN
        )
        self._sqrt_freq: dict[str, float] = {
            word: math.sqrt(index.frequencies[word]) for word in self._filler_pool
        }

    def _word_score(self, word: str, target: str) -> float:
        """13.3 step-4 score (owner answer 5): (occurrences of target in word / number of letter
        bigrams in word) * log(frequency(word) / min_frequency). min_frequency is the smallest
        frequency in the index, so the log is >= 0. Returns 0.0 for a word with no bigrams (never
        reached for a word that contains target)."""
        bigrams = word_bigrams(word)
        if not bigrams:
            return 0.0
        density = bigrams.count(target) / len(bigrams)
        return density * math.log(self._index.frequencies[word] / self._min_frequency)

    def generate(self, spec: DrillSpec) -> DrillCandidate:
        """Compose one heuristic drill and return it as a DrillCandidate (text == raw_output).

        Deterministic for a given spec.seed (random.Random(spec.seed)). See the module docstring for
        the step logic: lowest-coverage target (rng tie-break), top-50 softmax by _word_score, the
        density governor at the (min+max)/2 midpoint with sqrt-frequency non-target fillers, 2-use
        cap, and termination at spec.length_chars on a word boundary.
        """
        rng = random.Random(spec.seed)
        targets = spec.target_bigrams
        coverage: dict[str, int] = {bigram: 0 for bigram in targets}
        target_set = frozenset(targets)
        ranked: dict[str, tuple[str, ...]] = {}
        scores: dict[str, dict[str, float]] = {}
        for bigram in targets:
            words = [
                word
                for word in self._index.words_containing(bigram)
                if _MIN_WORD_LEN <= len(word) <= _MAX_WORD_LEN
            ]
            word_scores = {word: self._word_score(word, bigram) for word in words}
            ranked[bigram] = tuple(
                word for _, word in sorted(
                    (-word_scores[word], word) for word in words
                )
            )
            scores[bigram] = word_scores
        fillers = tuple(
            word
            for word in self._filler_pool
            if not (frozenset(word_bigrams(word)) & target_set)
        )
        midpoint = (spec.min_density + spec.max_density) / 2
        used: dict[str, int] = {}
        chosen_words: list[str] = []
        length = 0
        target_occurrences = 0
        total_bigrams = 0
        while True:
            density = target_occurrences / total_bigrams if total_bigrams else 0.0
            word: str | None = None
            if not density > midpoint:
                lowest = min(coverage[bigram] for bigram in targets)
                tied = sorted(
                    bigram for bigram in targets if coverage[bigram] == lowest
                )
                rng.shuffle(tied)
                for bigram in tied:
                    eligible = [
                        candidate
                        for candidate in ranked[bigram]
                        if used.get(candidate, 0) < _MAX_USES_PER_DRILL
                    ][:_TOP_CANDIDATES]
                    if eligible:
                        word = softmax_choice(
                            rng,
                            eligible,
                            [scores[bigram][candidate] for candidate in eligible],
                            _TEMPERATURE,
                        )
                        break
            if word is None:
                eligible_fillers = [
                    candidate
                    for candidate in fillers
                    if used.get(candidate, 0) < _MAX_USES_PER_DRILL
                ]
                if not eligible_fillers:
                    break
                word = weighted_choice(
                    rng,
                    eligible_fillers,
                    [self._sqrt_freq[candidate] for candidate in eligible_fillers],
                )
            addition = len(word) + (1 if chosen_words else 0)
            if length + addition > spec.length_chars:
                break
            used[word] = used.get(word, 0) + 1
            length += addition
            word_bg = word_bigrams(word)
            total_bigrams += len(word_bg)
            for bigram in targets:
                count = word_bg.count(bigram)
                coverage[bigram] += count
                target_occurrences += count
            chosen_words.append(word)
        text = " ".join(chosen_words)
        return DrillCandidate(
            text=text,
            raw_output=text,
            generator_version=_VERSION,
            seed=spec.seed,
        )
