import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.services.storage import DocumentNotFoundError, DocumentStorageError, S3DocumentStorage


class RecordingS3Body:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self.closed = False

    def read(self) -> bytes:
        return self._content

    def close(self) -> None:
        self.closed = True


class RecordingS3Client:
    def __init__(self, content: bytes = b"private evidence") -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.body = RecordingS3Body(content)
        self.closed = False

    def put_object(self, **kwargs: object) -> object:
        self.calls.append(("put", kwargs))
        return {}

    def get_object(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("get", kwargs))
        return {"Body": self.body}

    def delete_object(self, **kwargs: object) -> object:
        self.calls.append(("delete", kwargs))
        return {}

    def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_s3_document_storage_round_trip_contract() -> None:
    s3 = RecordingS3Client()
    storage = S3DocumentStorage(
        "evident-private-documents",
        client=s3,
        region_name="us-west-2",
    )
    key = "tenants/t1/documents/d1/source.pdf"

    await storage.put(key=key, content=b"private evidence")
    assert await storage.get(key=key) == b"private evidence"
    await storage.delete(key=key)
    await storage.close()

    assert s3.calls == [
        (
            "put",
            {
                "Bucket": "evident-private-documents",
                "Key": key,
                "Body": b"private evidence",
                "ContentLength": 16,
                "ContentType": "application/octet-stream",
                "ServerSideEncryption": "AES256",
            },
        ),
        ("get", {"Bucket": "evident-private-documents", "Key": key}),
        ("delete", {"Bucket": "evident-private-documents", "Key": key}),
    ]
    assert s3.body.closed is True
    assert s3.closed is False


@pytest.mark.anyio
async def test_s3_document_storage_wraps_client_failures() -> None:
    class FailingS3Client(RecordingS3Client):
        def put_object(self, **kwargs: object) -> object:
            raise OSError("network unavailable")

    storage = S3DocumentStorage(
        "evident-private-documents",
        client=FailingS3Client(),
    )

    with pytest.raises(DocumentStorageError, match="Could not store"):
        await storage.put(key="tenants/t1/source.pdf", content=b"content")


@pytest.mark.anyio
async def test_s3_document_storage_get_raises_not_found_for_missing_key() -> None:
    class MissingKeyS3Client(RecordingS3Client):
        def get_object(self, **kwargs: object) -> dict[str, object]:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
                "GetObject",
            )

    storage = S3DocumentStorage(
        "evident-private-documents",
        client=MissingKeyS3Client(),
    )

    with pytest.raises(DocumentNotFoundError):
        await storage.get(key="tenants/t1/report-exports/missing/report.md")


@pytest.mark.anyio
async def test_s3_document_storage_get_wraps_other_client_errors() -> None:
    class DeniedS3Client(RecordingS3Client):
        def get_object(self, **kwargs: object) -> dict[str, object]:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access Denied."}},
                "GetObject",
            )

    storage = S3DocumentStorage(
        "evident-private-documents",
        client=DeniedS3Client(),
    )

    with pytest.raises(DocumentStorageError) as excinfo:
        await storage.get(key="tenants/t1/report-exports/blocked/report.md")

    assert not isinstance(excinfo.value, DocumentNotFoundError)


def test_s3_document_storage_requires_bucket() -> None:
    with pytest.raises(ValueError, match="bucket must not be empty"):
        S3DocumentStorage(" ", client=RecordingS3Client())
