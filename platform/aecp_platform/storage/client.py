from __future__ import annotations

from pathlib import Path

# Later when scale can integrate 3rd party storage (cloud)

class ObjectStorageClient:
    """Simple local object storage client for MVP."""

    def __init__(self, bucket: str) -> None:
        self.root = Path(bucket)
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, data: bytes, tenant_id: str | None = None) -> str:
        storage_key = f"{tenant_id}/{key}" if tenant_id else key
        path = self.root / storage_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return storage_key

    async def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self.root / key
        if path.exists():
            path.unlink()

    async def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    async def list(self, prefix: str = "") -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []

        return [
            str(path.relative_to(self.root))
            for path in base.rglob("*")
            if path.is_file()
        ]
