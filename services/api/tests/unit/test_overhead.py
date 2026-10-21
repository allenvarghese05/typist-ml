"""overhead.percentiles: the inclusive-quantile method on hand-computed lists (T1.10)."""

from typist.services.overhead import Percentiles, percentiles


def test_percentiles_of_one_to_five_are_hand_computed() -> None:
    assert percentiles([1.0, 2.0, 3.0, 4.0, 5.0]) == Percentiles(p50=3.0, p95=4.8, p99=4.96)


def test_single_value_is_its_own_percentiles() -> None:
    assert percentiles([7.0]) == Percentiles(p50=7.0, p95=7.0, p99=7.0)


def test_two_values_interpolate() -> None:
    assert percentiles([2.0, 4.0]) == Percentiles(p50=3.0, p95=3.9, p99=3.98)


def test_empty_list_has_no_percentiles() -> None:
    assert percentiles([]) is None


def test_order_does_not_change_the_result() -> None:
    assert percentiles([5.0, 1.0, 4.0, 2.0, 3.0]) == Percentiles(p50=3.0, p95=4.8, p99=4.96)
