from pathlib import Path

import pytest

from app.services.storage import LocalDocumentStorage


@pytest.mark.anyio
async def test_local_document_storage_round_trip_is_private(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    key = "tenants/example/documents/document/source.md"

    await storage.put(key=key, content=b"trusted evidence")

    stored_path = tmp_path / key
    assert await storage.get(key=key) == b"trusted evidence"
    assert stored_path.stat().st_mode & 0o777 == 0o600

    await storage.delete(key=key)
    await storage.delete(key=key)

    assert not stored_path.exists()


@pytest.mark.parametrize(
    "key",
    ["", "/etc/passwd", "../escape.txt", "safe/../../escape.txt", r"safe\escape.txt"],
)
@pytest.mark.anyio
async def test_local_document_storage_rejects_unsafe_keys(
    tmp_path: Path,
    key: str,
) -> None:
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(ValueError, match="safe relative path|escapes"):
        await storage.put(key=key, content=b"blocked")
