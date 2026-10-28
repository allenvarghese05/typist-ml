"""The Markov drill generator: character n-gram pseudo-words with beta target bias (design doc 13.4).

MarkovGenerator implements Arm.MARKOV (D03). Pseudo-words are sampled character-by-character from an
order-3 character n-gram model (CharNGramModel) with sentinels '^' and '$'. When sampling, if the
immediately preceding character is the first letter of a target bigram, the transition probability
of that bigram's second letter is multiplied by markov_beta before renormalization (13.4 step 2;
owner answer 7). Pseudo-words are constrained to 3-10 characters (13.4 step 3; owner answer 4):
  - End marker '$' is masked out when word length < 3
  - If length reaches 10, the word is terminated
  - Dead-end contexts discard the candidate word and resample with the seeded RNG (owner answer 5)
Each pseudo-word is capped at _MAX_USES_PER_DRILL (2) uses per drill, matching control and heuristic
generators (owner answer 8). The generator stops when the next word would exceed spec.length_chars
(300), terminating cleanly at a word boundary (measured 290-300 characters, >= 270 floor).
Randomness is strictly random.Random(spec.seed). Pure: returns one DrillCandidate per call.
"""

import random
from collections import defaultdict
from typing import Final

from typist.corpus.ngram import END_CHAR, START_CHAR, CharNGramModel
from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm, DrillCandidate, DrillSpec
from typist.generation.sampling import weighted_choice
from typist.generation.validator import ValidatorConfig

_VERSION: Final[str] = "markov-v1"
_MAX_USES_PER_DRILL: Final[int] = 2  # Matches control.py and heuristic.py (owner answer 8)
_MIN_WORD_LEN: Final[int] = 3  # 13.4 step 3 pseudo-word bounds (owner answer 4)
_MAX_WORD_LEN: Final[int] = 10


class MarkovGenerator:
    """The 13.4 character-level Markov pseudo-word generator for Arm.MARKOV."""

    arm = Arm.MARKOV
    version = _VERSION

    def __init__(
        self,
        index: WordIndex,
        config: ValidatorConfig,
        beta: float,
        model: CharNGramModel | None = None,
    ) -> None:
        """index supplies words/frequencies for model training; config is accepted for uniform
        generator signature; beta is markov_beta from experiment_config; model can be injected
        or is trained from index."""
        self._config = config
        self._beta = beta
        self._model = model if model is not None else CharNGramModel.from_word_index(index)

    def _sample_word(self, rng: random.Random, target_map: dict[str, set[str]]) -> str:
        """Sample one pseudo-word of 3 to 10 characters using the seeded RNG.

        Discard and retry if a dead end is reached before valid completion (owner answer 5).
        """
        while True:
            chars = [START_CHAR, START_CHAR]
            dead_end = False
            while True:
                word_len = len(chars) - 2
                if word_len == _MAX_WORD_LEN:
                    break
                ctx = (chars[-2], chars[-1])
                next_transitions = self._model.get_transitions(ctx)
                if not next_transitions:
                    dead_end = True
                    break
                prev_char = chars[-1]
                boosted_seconds = target_map.get(prev_char, set())
                candidates: list[str] = []
                weights: list[float] = []
                for char, base_weight in next_transitions.items():
                    if char == END_CHAR and word_len < _MIN_WORD_LEN:
                        continue
                    w = base_weight * (self._beta if char in boosted_seconds else 1.0)
                    candidates.append(char)
                    weights.append(w)
                if not candidates or sum(weights) <= 0.0:
                    dead_end = True
                    break
                next_char = weighted_choice(rng, candidates, weights)
                if next_char == END_CHAR:
                    break
                chars.append(next_char)
            word_len = len(chars) - 2
            if dead_end or word_len < _MIN_WORD_LEN:
                continue
            return "".join(chars[2:])

    def generate(self, spec: DrillSpec) -> DrillCandidate:
        """Compose one Markov drill candidate deterministically for spec.seed.

        Emits pseudo-words separated by single spaces up to spec.length_chars at a word boundary.
        """
        rng = random.Random(spec.seed)
        target_map: dict[str, set[str]] = defaultdict(set)
        for bigram in spec.target_bigrams:
            if len(bigram) == 2:
                target_map[bigram[0]].add(bigram[1])

        used: dict[str, int] = {}
        words: list[str] = []
        length = 0

        while True:
            word = self._sample_word(rng, target_map)
            if used.get(word, 0) >= _MAX_USES_PER_DRILL:
                continue
            addition = len(word) + (1 if words else 0)
            if length + addition > spec.length_chars:
                break
            used[word] = used.get(word, 0) + 1
            length += addition
            words.append(word)

        text = " ".join(words)
        return DrillCandidate(
            text=text,
            raw_output=text,
            generator_version=_VERSION,
            seed=spec.seed,
        )
