import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_document_upload_configuration_has_safe_defaults() -> None:
    config = Settings()

    assert config.document_storage_root == "uploads"
    assert config.document_storage_provider == "local"
    assert config.document_s3_bucket == ""
    assert config.document_max_upload_bytes == 10_000_000
    assert config.embedding_provider == "ollama"
    assert config.aws_region == "us-west-2"
    assert config.bedrock_embedding_model == "amazon.titan-embed-text-v2:0"
    assert config.bedrock_embedding_dimensions == 1024
    assert config.mcp_endpoint == ""
    assert config.mcp_server_name == "evident-reference"
    assert config.mcp_server_host == "127.0.0.1"
    assert config.mcp_server_port == 8001


def test_bedrock_embedding_dimensions_coerces_a_string_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Environment variables (as ECS task definitions and shells set them)
    # are always strings. A plain `int` field coerces "1024" -> 1024
    # automatically; Literal[256, 512, 1024] does not by default, which
    # crashed every container on staging with a ValidationError before
    # this was fixed.
    monkeypatch.setenv("BEDROCK_EMBEDDING_DIMENSIONS", "1024")

    config = Settings()

    assert config.bedrock_embedding_dimensions == 1024
    assert isinstance(config.bedrock_embedding_dimensions, int)


def test_bedrock_embedding_dimensions_rejects_an_unsupported_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BEDROCK_EMBEDDING_DIMENSIONS", "999")

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("max_upload_bytes", [0, 100_000_001])
def test_document_upload_configuration_rejects_unsafe_size_bounds(
    max_upload_bytes: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            document_max_upload_bytes=max_upload_bytes,
        )
