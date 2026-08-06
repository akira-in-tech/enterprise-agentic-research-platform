import pytest

from app.services.auth.passwords import hash_password, verify_password


def test_hash_password_produces_a_verifiable_hash() -> None:
    password_hash = hash_password("correct-horse-battery")

    assert password_hash != "correct-horse-battery"
    assert verify_password("correct-horse-battery", password_hash)


def test_verify_password_rejects_wrong_password() -> None:
    password_hash = hash_password("correct-horse-battery")

    assert not verify_password("wrong-password", password_hash)


def test_hash_password_rejects_short_passwords() -> None:
    with pytest.raises(
        ValueError,
        match="at least 8 characters",
    ):
        hash_password("short")
