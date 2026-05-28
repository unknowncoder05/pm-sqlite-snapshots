from __future__ import annotations

import json
import os
import shutil

from . import SnapshotRef


class LocalSnapshotStorage:
    def __init__(self, *, path: str, **kwargs):
        if not path:
            raise ValueError("SQLITE_SNAPSHOTS STORAGE.PATH is required")
        self.path = path
        os.makedirs(self.path, exist_ok=True)

    @classmethod
    def from_config(cls, config: dict):
        return cls(path=config.get("PATH", ""))

    def upload(self, database_path: str, manifest: dict) -> SnapshotRef:
        snapshot_id = manifest["snapshot_id"]
        database_key = os.path.join(self.path, f"{snapshot_id}.sqlite3.gz")
        manifest_key = os.path.join(self.path, f"{snapshot_id}.manifest.json")
        latest_key = os.path.join(self.path, "latest.json")
        shutil.copy2(database_path, database_key)
        with open(manifest_key, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
        ref = SnapshotRef(
            snapshot_id=snapshot_id,
            database_key=database_key,
            manifest_key=manifest_key,
            created_at=manifest["created_at"],
            sha256=manifest["sha256"],
        )
        with open(latest_key, "w", encoding="utf-8") as fh:
            json.dump(ref.__dict__, fh, indent=2, sort_keys=True)
        return ref

    def download(self, snapshot: SnapshotRef, destination_path: str) -> None:
        shutil.copy2(snapshot.database_key, destination_path)

    def latest(self) -> SnapshotRef | None:
        latest_key = os.path.join(self.path, "latest.json")
        if not os.path.exists(latest_key):
            return None
        with open(latest_key, encoding="utf-8") as fh:
            return SnapshotRef(**json.load(fh))

    def list(self) -> list[SnapshotRef]:
        refs = []
        for filename in os.listdir(self.path):
            if not filename.endswith(".manifest.json"):
                continue
            manifest_key = os.path.join(self.path, filename)
            with open(manifest_key, encoding="utf-8") as fh:
                manifest = json.load(fh)
            snapshot_id = manifest["snapshot_id"]
            refs.append(
                SnapshotRef(
                    snapshot_id=snapshot_id,
                    database_key=os.path.join(self.path, f"{snapshot_id}.sqlite3.gz"),
                    manifest_key=manifest_key,
                    created_at=manifest["created_at"],
                    sha256=manifest.get("sha256"),
                )
            )
        return sorted(refs, key=lambda ref: ref.created_at, reverse=True)

    def delete(self, snapshot: SnapshotRef) -> None:
        for path in (snapshot.database_key, snapshot.manifest_key):
            if os.path.exists(path):
                os.remove(path)
