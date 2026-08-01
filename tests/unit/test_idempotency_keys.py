from uuid import uuid4

import pytest

from app.services.cache import (
    MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH,
    RESEARCH_IDEMPOTENCY_KEY_VERSION,
    RESEARCH_IDEMPOTENCY_LOCK_VERSION,
    create_research_idempotency_lock_redis_key,
    create_research_idempotency_redis_key,
)


def test_idempotency_redis_key_is_deterministic() -> None:
    tenant_id = uuid4()
    client_key = "research-request-123"

    first_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )
    second_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )

    assert first_key == second_key
    assert first_key.startswith(
        "enterprise-research"
        f":{RESEARCH_IDEMPOTENCY_KEY_VERSION}"
        f":tenant:{tenant_id}"
        ":research-idempotency:"
    )


def test_idempotency_redis_key_normalizes_outer_whitespace() -> None:
    tenant_id = uuid4()

    normalized_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key="research-request-123",
    )
    padded_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key="  research-request-123  ",
    )

    assert normalized_key == padded_key


def test_idempotency_redis_key_isolates_tenants() -> None:
    first_key = create_research_idempotency_redis_key(
        tenant_id=uuid4(),
        client_key="research-request-123",
    )
    second_key = create_research_idempotency_redis_key(
        tenant_id=uuid4(),
        client_key="research-request-123",
    )

    assert first_key != second_key


def test_idempotency_redis_key_isolates_client_keys() -> None:
    tenant_id = uuid4()

    first_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key="research-request-123",
    )
    second_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key="research-request-456",
    )

    assert first_key != second_key


def test_idempotency_redis_key_does_not_expose_client_key() -> None:
    client_key = "confidential-client-operation-123"

    redis_key = create_research_idempotency_redis_key(
        tenant_id=uuid4(),
        client_key=client_key,
    )

    assert client_key not in redis_key
    assert "confidential" not in redis_key


@pytest.mark.parametrize(
    "client_key",
    [
        "",
        "   ",
        "\n\t",
    ],
)
def test_idempotency_redis_key_rejects_blank_value(
    client_key: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="client_key must not be empty",
    ):
        create_research_idempotency_redis_key(
            tenant_id=uuid4(),
            client_key=client_key,
        )


def test_idempotency_redis_key_accepts_maximum_length() -> None:
    redis_key = create_research_idempotency_redis_key(
        tenant_id=uuid4(),
        client_key="a" * MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH,
    )

    assert redis_key


def test_idempotency_redis_key_rejects_excessive_length() -> None:
    with pytest.raises(
        ValueError,
        match="client_key must not exceed",
    ):
        create_research_idempotency_redis_key(
            tenant_id=uuid4(),
            client_key=("a" * (MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH + 1)),
        )


def test_idempotency_lock_key_is_deterministic() -> None:
    tenant_id = uuid4()
    client_key = "research-request-123"

    first_key = create_research_idempotency_lock_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )
    second_key = create_research_idempotency_lock_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )

    assert first_key == second_key
    assert first_key.startswith(
        "enterprise-research"
        f":{RESEARCH_IDEMPOTENCY_LOCK_VERSION}"
        f":tenant:{tenant_id}"
        ":research-idempotency-lock:"
    )


def test_idempotency_lock_key_is_distinct_from_record_key() -> None:
    tenant_id = uuid4()
    client_key = "research-request-123"

    record_key = create_research_idempotency_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )
    lock_key = create_research_idempotency_lock_redis_key(
        tenant_id=tenant_id,
        client_key=client_key,
    )

    assert lock_key != record_key


def test_idempotency_lock_key_normalizes_outer_whitespace() -> None:
    tenant_id = uuid4()

    normalized_key = create_research_idempotency_lock_redis_key(
        tenant_id=tenant_id,
        client_key="research-request-123",
    )
    padded_key = create_research_idempotency_lock_redis_key(
        tenant_id=tenant_id,
        client_key="  research-request-123  ",
    )

    assert normalized_key == padded_key


def test_idempotency_lock_key_isolates_tenants() -> None:
    first_key = create_research_idempotency_lock_redis_key(
        tenant_id=uuid4(),
        client_key="research-request-123",
    )
    second_key = create_research_idempotency_lock_redis_key(
        tenant_id=uuid4(),
        client_key="research-request-123",
    )

    assert first_key != second_key


def test_idempotency_lock_key_does_not_expose_client_key() -> None:
    client_key = "confidential-operation-123"

    lock_key = create_research_idempotency_lock_redis_key(
        tenant_id=uuid4(),
        client_key=client_key,
    )

    assert client_key not in lock_key
    assert "confidential" not in lock_key


@pytest.mark.parametrize(
    "client_key",
    [
        "",
        "   ",
        "\n\t",
    ],
)
def test_idempotency_lock_key_rejects_blank_value(
    client_key: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="client_key must not be empty",
    ):
        create_research_idempotency_lock_redis_key(
            tenant_id=uuid4(),
            client_key=client_key,
        )


def test_idempotency_lock_key_rejects_excessive_length() -> None:
    with pytest.raises(
        ValueError,
        match="client_key must not exceed",
    ):
        create_research_idempotency_lock_redis_key(
            tenant_id=uuid4(),
            client_key=("a" * (MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH + 1)),
        )
