import asyncio
from typing import Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.config import settings
from app.services.storage.base import DocumentNotFoundError, DocumentStorageError


class S3ResponseBody(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...


class S3Client(Protocol):
    def put_object(self, **kwargs: object) -> object: ...

    def get_object(self, **kwargs: object) -> dict[str, object]: ...

    def delete_object(self, **kwargs: object) -> object: ...

    def close(self) -> None: ...


def create_s3_client(*, region_name: str) -> S3Client:
    return cast(
        S3Client,
        boto3.client(
            "s3",
            region_name=region_name,
            config=Config(
                retries={"total_max_attempts": 5, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=30,
                max_pool_connections=20,
            ),
        ),
    )


class S3DocumentStorage:
    """Store tenant source objects in one private encrypted S3 bucket."""

    def __init__(
        self,
        bucket: str | None = None,
        *,
        client: S3Client | None = None,
        region_name: str | None = None,
    ) -> None:
        selected_bucket = (bucket or settings.document_s3_bucket).strip()
        selected_region = (region_name or settings.aws_region).strip()
        if not selected_bucket:
            raise ValueError("Document S3 bucket must not be empty.")
        if not selected_region:
            raise ValueError("AWS region must not be empty.")

        self._bucket = selected_bucket
        self._client = client or create_s3_client(region_name=selected_region)
        self._owns_client = client is None

    async def put(self, *, key: str, content: bytes) -> None:
        if not key.strip():
            raise ValueError("Document storage key must not be empty.")
        if not content:
            raise ValueError("Document storage content must not be empty.")
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentLength=len(content),
                ContentType="application/octet-stream",
                ServerSideEncryption="AES256",
            )
        except Exception as error:
            raise DocumentStorageError("Could not store the private document.") from error

    async def get(self, *, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                Bucket=self._bucket,
                Key=key,
            )
            body = response.get("Body")
            if body is None or not hasattr(body, "read") or not hasattr(body, "close"):
                raise RuntimeError("S3 returned an invalid response body.")
            stream = cast(S3ResponseBody, body)
            try:
                return await asyncio.to_thread(stream.read)
            finally:
                stream.close()
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404"}:
                raise DocumentNotFoundError("The private document was not found.") from error
            raise DocumentStorageError("Could not read the private document.") from error
        except Exception as error:
            raise DocumentStorageError("Could not read the private document.") from error

    async def delete(self, *, key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=self._bucket,
                Key=key,
            )
        except Exception as error:
            raise DocumentStorageError("Could not delete the private document.") from error

    async def close(self) -> None:
        if self._owns_client:
            await asyncio.to_thread(self._client.close)
