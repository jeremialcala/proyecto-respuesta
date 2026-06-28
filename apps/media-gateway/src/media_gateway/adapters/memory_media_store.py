"""MediaStore fake (tests). El real es `s3_media_store.S3MediaStore` (lee la bóveda S3)."""
from __future__ import annotations


class MemoryMediaStore:
    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, dict]] = {}

    def put(self, media_ref: str, ciphertext: bytes, metadata: dict) -> None:
        """Helper de tests: siembra un objeto. `metadata` debe incluir `scan` y `content_type`."""
        self._objects[media_ref] = (ciphertext, metadata)

    def get(self, media_ref: str) -> tuple[bytes, dict]:
        if media_ref not in self._objects:
            raise KeyError(media_ref)
        return self._objects[media_ref]
