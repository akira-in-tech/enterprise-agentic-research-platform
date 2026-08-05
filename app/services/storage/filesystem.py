import asyncio
import os
import tempfile
from pathlib import Path, PurePosixPath

from app.services.storage.base import DocumentStorageError


class LocalDocumentStorage:
    """Store private source objects beneath one local runtime directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()

    async def put(self, *, key: str, content: bytes) -> None:
        """Atomically write one source object without blocking the event loop."""

        if not content:
            raise ValueError("Document storage content must not be empty.")

        path = self._resolve_key(key)

        try:
            await asyncio.to_thread(self._write_atomic, path, content)
        except OSError as error:
            raise DocumentStorageError("Could not store the private document.") from error

    async def get(self, *, key: str) -> bytes:
        """Read one source object without blocking the event loop."""

        path = self._resolve_key(key)

        try:
            return await asyncio.to_thread(path.read_bytes)
        except OSError as error:
            raise DocumentStorageError("Could not read the private document.") from error

    async def delete(self, *, key: str) -> None:
        """Delete one source object idempotently."""

        path = self._resolve_key(key)

        try:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        except OSError as error:
            raise DocumentStorageError("Could not delete the private document.") from error

    def _resolve_key(self, key: str) -> Path:
        normalized_key = key.strip()
        pure_key = PurePosixPath(normalized_key)

        if (
            not normalized_key
            or pure_key.is_absolute()
            or "\\" in normalized_key
            or any(part in {"", ".", ".."} for part in pure_key.parts)
        ):
            raise ValueError("Document storage key must be a safe relative path.")

        path = self._root.joinpath(*pure_key.parts).resolve()

        if not path.is_relative_to(self._root):
            raise ValueError("Document storage key escapes the configured root.")

        return path

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".document-",
        )
        temporary_path = Path(temporary_name)

        try:
            os.chmod(temporary_path, 0o600)

            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
