from unittest.mock import Mock

import pytest

from app.core.config import settings
from app.services.embeddings import factory as embedding_factory
from app.services.storage import factory as storage_factory


def test_embedding_factory_selects_local_and_bedrock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ollama = object()
    bedrock = object()
    create_ollama = Mock(return_value=ollama)
    create_bedrock = Mock(return_value=bedrock)
    monkeypatch.setattr(embedding_factory, "OllamaEmbeddingClient", create_ollama)
    monkeypatch.setattr(
        embedding_factory,
        "BedrockTitanEmbeddingClient",
        create_bedrock,
    )

    assert embedding_factory.create_embedding_client(" OLLAMA ") is ollama
    assert embedding_factory.create_embedding_client("bedrock") is bedrock
    create_ollama.assert_called_once_with()
    create_bedrock.assert_called_once_with()


def test_embedding_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported embedding provider"):
        embedding_factory.create_embedding_client("unknown")


def test_storage_factory_selects_local_and_s3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = object()
    s3 = object()
    create_local = Mock(return_value=local)
    create_s3 = Mock(return_value=s3)
    monkeypatch.setattr(storage_factory, "LocalDocumentStorage", create_local)
    monkeypatch.setattr(storage_factory, "S3DocumentStorage", create_s3)

    assert storage_factory.create_document_storage(" LOCAL ") is local
    assert storage_factory.create_document_storage("s3") is s3
    create_local.assert_called_once_with(settings.document_storage_root)
    create_s3.assert_called_once_with()


def test_storage_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported document storage provider"):
        storage_factory.create_document_storage("unknown")
