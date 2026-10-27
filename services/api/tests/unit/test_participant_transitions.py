"""Unit tests for participant schemas and transition rules (T2.8)."""

from typist.schemas.participants import ParticipantCreate


def test_participant_create_enforces_builder_is_not_blinded() -> None:
    builder = ParticipantCreate(alias="builder_user", is_builder=True, is_blinded=True)
    assert builder.is_builder is True
    assert builder.is_blinded is False

    standard = ParticipantCreate(alias="normal_user", is_builder=False, is_blinded=True)
    assert standard.is_builder is False
    assert standard.is_blinded is True
