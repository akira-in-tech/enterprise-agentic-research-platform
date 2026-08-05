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


@pytest.mark.parametrize("max_upload_bytes", [0, 100_000_001])
def test_document_upload_configuration_rejects_unsafe_size_bounds(
    max_upload_bytes: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            document_max_upload_bytes=max_upload_bytes,
        )
