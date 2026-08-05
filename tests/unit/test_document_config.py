import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_document_upload_configuration_has_safe_defaults() -> None:
    config = Settings()

    assert config.document_storage_root == "uploads"
    assert config.document_max_upload_bytes == 10_000_000


@pytest.mark.parametrize("max_upload_bytes", [0, 100_000_001])
def test_document_upload_configuration_rejects_unsafe_size_bounds(
    max_upload_bytes: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(
            document_max_upload_bytes=max_upload_bytes,
        )
