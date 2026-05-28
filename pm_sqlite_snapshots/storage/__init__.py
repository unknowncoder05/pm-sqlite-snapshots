from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SnapshotRef:
    snapshot_id: str
    database_key: str
    manifest_key: str
    created_at: str
    sha256: str | None = None


class SnapshotStorage(Protocol):
    def upload(self, database_path: str, manifest: dict) -> SnapshotRef:
        ...

    def download(self, snapshot: SnapshotRef, destination_path: str) -> None:
        ...

    def latest(self) -> SnapshotRef | None:
        ...

    def list(self) -> list[SnapshotRef]:
        ...

    def delete(self, snapshot: SnapshotRef) -> None:
        ...
