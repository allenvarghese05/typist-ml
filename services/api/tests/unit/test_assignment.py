"""Unit tests for assignment's pure functions: smoothing, ranking, snake deal, selection (T2.2)."""

import pytest

from typist.services.assignment import (
    PooledBigram,
    RankedBigram,
    TooFewCandidatesError,
    rank_candidates,
    select_count,
    shuffle_arms,
    smoothed_rate,
    snake_deal,
)


def test_smoothed_rate_matches_the_hand_computed_posterior_mean() -> None:
    # (3 errors + 20*0.1) / (10 attempts + 20) = 5/30.
    assert smoothed_rate(3, 10, p0=0.1, strength=20) == pytest.approx(0.16666666666666666)


def test_smoothed_rate_keeps_a_sparse_bigram_near_the_prior() -> None:
    # The design's own example: 1 error in 3 attempts, p0=0.05 -> (1+1)/23, close to p0.
    assert smoothed_rate(1, 3, p0=0.05, strength=20) == pytest.approx(0.08695652173913043)


def _ranks(ranked: list[RankedBigram]) -> dict[str, int]:
    return {item.bigram: item.rank for item in ranked}


def test_rank_candidates_orders_by_smoothed_rate_then_breaks_ties_by_iki_zscore() -> None:
    # aa and bb tie on smoothed=0.1; population medians [250,150,100,300] give mean 200, pstdev
    # ~79.057, so z(aa)=+0.632 (slower, weaker) ranks above z(bb)=-0.632. cc (0.175) is rank 1,
    # dd (0.075) is rank 4.
    candidates = [
        PooledBigram("aa", attempts=20, errors=2, iki_median_ms=250.0),
        PooledBigram("bb", attempts=20, errors=2, iki_median_ms=150.0),
        PooledBigram("cc", attempts=20, errors=5, iki_median_ms=100.0),
        PooledBigram("dd", attempts=20, errors=1, iki_median_ms=300.0),
    ]
    ranked = rank_candidates(candidates, p0=0.1, strength=20)
    assert _ranks(ranked) == {"cc": 1, "aa": 2, "bb": 3, "dd": 4}
    assert ranked[0].smoothed_rate == pytest.approx(0.175)
    assert ranked[1].smoothed_rate == pytest.approx(0.1)


def test_rank_candidates_zero_std_falls_back_to_bigram_string() -> None:
    # Equal medians -> pstdev 0 -> all z=0; aa and bb tie on smoothed -> bigram string orders them.
    candidates = [
        PooledBigram("bb", attempts=20, errors=2, iki_median_ms=100.0),
        PooledBigram("aa", attempts=20, errors=2, iki_median_ms=100.0),
    ]
    ranked = rank_candidates(candidates, p0=0.1, strength=20)
    assert _ranks(ranked) == {"aa": 1, "bb": 2}


def test_rank_candidates_treats_a_missing_median_as_z_zero() -> None:
    # cc has no IKI sample (None): its z is 0 (neutral). aa (median 300, z>0) outranks a tie.
    candidates = [
        PooledBigram("aa", attempts=20, errors=2, iki_median_ms=300.0),
        PooledBigram("cc", attempts=20, errors=2, iki_median_ms=None),
        PooledBigram("bb", attempts=20, errors=2, iki_median_ms=100.0),
    ]
    ranked = rank_candidates(candidates, p0=0.1, strength=20)
    # population medians [300,100] -> mean 200, pstdev 100; z(aa)=+1, z(bb)=-1, z(cc)=0.
    assert _ranks(ranked) == {"aa": 1, "cc": 2, "bb": 3}


def _sets(dealt: list[tuple[RankedBigram, int]]) -> dict[int, set[int]]:
    groups: dict[int, set[int]] = {}
    for item, set_index in dealt:
        groups.setdefault(set_index, set()).add(item.rank)
    return groups


def _ranked(n: int) -> list[RankedBigram]:
    return [
        RankedBigram(f"b{i}", rank=i, smoothed_rate=0.0, attempts=20, errors=0)
        for i in range(1, n + 1)
    ]


def test_snake_deal_16_over_4_sets() -> None:
    groups = _sets(snake_deal(_ranked(16), 4))
    assert groups == {
        0: {1, 8, 9, 16},
        1: {2, 7, 10, 15},
        2: {3, 6, 11, 14},
        3: {4, 5, 12, 13},
    }


def test_snake_deal_8_over_2_sets() -> None:
    groups = _sets(snake_deal(_ranked(8), 2))
    assert groups == {0: {1, 4, 5, 8}, 1: {2, 3, 6, 7}}


def test_snake_deal_12_over_4_sets_is_three_per_set() -> None:
    groups = _sets(snake_deal(_ranked(12), 4))
    assert groups == {0: {1, 8, 9}, 1: {2, 7, 10}, 2: {3, 6, 11}, 3: {4, 5, 12}}


def test_select_count_full_fallback_and_floor() -> None:
    assert select_count(16, per_set=4, fallback=3, sets=4) == 16
    assert select_count(14, per_set=4, fallback=3, sets=4) == 12  # fallback to 3 per set
    assert select_count(8, per_set=4, fallback=3, sets=2) == 8  # two-set mode
    assert select_count(6, per_set=4, fallback=3, sets=2) == 6


def test_select_count_below_the_floor_raises() -> None:
    with pytest.raises(TooFewCandidatesError, match="11 < 12"):
        select_count(11, per_set=4, fallback=3, sets=4)
    with pytest.raises(TooFewCandidatesError, match="5 < 6"):
        select_count(5, per_set=4, fallback=3, sets=2)


def test_shuffle_arms_is_seeded_and_non_mutating() -> None:
    import random

    arms = ("control", "heuristic", "markov", "llm")
    first = shuffle_arms(arms, random.Random("20261021:p-assign-01"))
    second = shuffle_arms(arms, random.Random("20261021:p-assign-01"))
    assert first == second == ["markov", "heuristic", "llm", "control"]
    assert arms == ("control", "heuristic", "markov", "llm")  # not mutated
