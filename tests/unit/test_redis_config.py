import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_settings_accepts_custom_redis_configuration() -> None:
    config = Settings(
        redis_url=SecretStr(
            "rediss://cache.internal.example:6380/2",
        ),
        redis_max_connections=48,
        redis_socket_connect_timeout_seconds=1.5,
        redis_socket_timeout_seconds=3.0,
        redis_health_check_interval_seconds=15,
    )

    assert config.redis_url.get_secret_value() == "rediss://cache.internal.example:6380/2"
    assert config.redis_max_connections == 48
    assert config.redis_socket_connect_timeout_seconds == 1.5
    assert config.redis_socket_timeout_seconds == 3.0
    assert config.redis_health_check_interval_seconds == 15


def test_settings_rejects_empty_redis_connection_pool() -> None:
    with pytest.raises(ValidationError):
        Settings(
            redis_max_connections=0,
        )


def test_settings_rejects_non_positive_redis_timeout() -> None:
    with pytest.raises(ValidationError):
        Settings(
            redis_socket_timeout_seconds=0,
        )
