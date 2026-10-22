"""Integration test: load_validator_config reads the six seeded keys from experiment_config (T2.3).
Uses migrated_engine so migration 0006 is applied."""

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from typist.generation.validator import (
    load_validator_config,
)


def test_load_validator_config_reads_the_six_keys(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        config = load_validator_config(session)
    assert config.min_length_chars == 270
    assert config.min_coverage == 3
    assert config.max_word_repeats == 3
    assert config.max_bigram_run == 3
    assert config.min_real_word_ratio == pytest.approx(0.8)
