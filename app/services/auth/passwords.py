from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage."""

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    return _hasher.hash(password)


def verify_password(
    password: str,
    password_hash: str,
) -> bool:
    """Return whether a plaintext password matches a stored hash."""

    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
