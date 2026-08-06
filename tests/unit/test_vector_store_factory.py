import pytest

from app.core.config import settings
from app.services.vector_store import factory


def test_factory_creates_memory_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_store = object()
    captured_dimensions: list[int] = []

    def create_memory_store(
        *,
        dimensions: int,
    ) -> object:
        captured_dimensions.append(dimensions)
        return expected_store

    monkeypatch.setattr(
        factory,
        "InMemoryVectorStore",
        create_memory_store,
    )

    result = factory.create_vector_store(
        "  MeMoRy  ",
        dimensions=3,
    )

    assert result is expected_store
    assert captured_dimensions == [3]


def test_factory_creates_milvus_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_store = object()
    captured_dimensions: list[int] = []

    def create_milvus_store(
        *,
        dimensions: int,
        circuit_breaker: object = None,
    ) -> object:
        captured_dimensions.append(dimensions)
        return expected_store

    monkeypatch.setattr(
        factory,
        "MilvusVectorStore",
        create_milvus_store,
    )

    result = factory.create_vector_store(
        "milvus",
        dimensions=1024,
    )

    assert result is expected_store
    assert captured_dimensions == [1024]


def test_factory_uses_provider_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_store = object()

    monkeypatch.setattr(
        settings,
        "vector_store_provider",
        "milvus",
    )
    monkeypatch.setattr(
        factory,
        "MilvusVectorStore",
        lambda *, dimensions, circuit_breaker=None: expected_store,
    )

    result = factory.create_vector_store(
        dimensions=1024,
    )

    assert result is expected_store


def test_factory_uses_dimensions_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_store = object()
    captured_dimensions: list[int] = []

    def create_memory_store(
        *,
        dimensions: int,
    ) -> object:
        captured_dimensions.append(dimensions)
        return expected_store

    monkeypatch.setattr(
        settings,
        "vector_store_provider",
        "memory",
    )
    monkeypatch.setattr(
        settings,
        "ollama_embedding_dimensions",
        384,
    )
    monkeypatch.setattr(
        factory,
        "InMemoryVectorStore",
        create_memory_store,
    )

    result = factory.create_vector_store()

    assert result is expected_store
    assert captured_dimensions == [384]


def test_factory_rejects_unsupported_provider() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported vector-store provider",
    ):
        factory.create_vector_store(
            "unknown-provider",
            dimensions=2,
        )
