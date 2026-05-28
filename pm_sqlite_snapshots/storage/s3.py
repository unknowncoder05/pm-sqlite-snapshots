import json
from urllib.parse import urlparse

import boto3

from . import SnapshotRef


class S3SnapshotStorage:
    def __init__(self, *, bucket: str, prefix: str = "", region: str | None = None, **kwargs):
        if not bucket:
            raise ValueError("SQLITE_SNAPSHOTS STORAGE.BUCKET is required")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3", region_name=region or None)

    @classmethod
    def from_config(cls, config: dict):
        return cls(
            bucket=config.get("BUCKET", ""),
            prefix=config.get("PREFIX", ""),
            region=config.get("REGION"),
        )

    def upload(self, database_path: str, manifest: dict) -> SnapshotRef:
        snapshot_id = manifest["snapshot_id"]
        base = self._key(f"snapshots/{snapshot_id[:4]}/{snapshot_id[4:6]}/{snapshot_id[6:8]}/{snapshot_id}")
        database_key = f"{base}.sqlite3.gz"
        manifest_key = f"{base}.manifest.json"

        self.client.upload_file(database_path, self.bucket, database_key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )
        latest = {
            "snapshot_id": snapshot_id,
            "database_key": database_key,
            "manifest_key": manifest_key,
            "created_at": manifest["created_at"],
            "sha256": manifest["sha256"],
        }
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key("latest.json"),
            Body=json.dumps(latest, indent=2, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )
        return SnapshotRef(**latest)

    def download(self, snapshot: SnapshotRef, destination_path: str) -> None:
        self.client.download_file(self.bucket, snapshot.database_key, destination_path)

    def latest(self) -> SnapshotRef | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key("latest.json"))
        except self.client.exceptions.NoSuchKey:
            return None
        except Exception as exc:
            if _is_missing_key_error(exc):
                return None
            raise
        data = json.loads(response["Body"].read().decode("utf-8"))
        return SnapshotRef(**data)

    def list(self) -> list[SnapshotRef]:
        refs = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self._key("snapshots/")):
            for item in page.get("Contents", []):
                key = item["Key"]
                if not key.endswith(".manifest.json"):
                    continue
                response = self.client.get_object(Bucket=self.bucket, Key=key)
                manifest = json.loads(response["Body"].read().decode("utf-8"))
                refs.append(
                    SnapshotRef(
                        snapshot_id=manifest["snapshot_id"],
                        database_key=key.replace(".manifest.json", ".sqlite3.gz"),
                        manifest_key=key,
                        created_at=manifest["created_at"],
                        sha256=manifest.get("sha256"),
                    )
                )
        return sorted(refs, key=lambda ref: ref.created_at, reverse=True)

    def delete(self, snapshot: SnapshotRef) -> None:
        self.client.delete_objects(
            Bucket=self.bucket,
            Delete={
                "Objects": [
                    {"Key": snapshot.database_key},
                    {"Key": snapshot.manifest_key},
                ],
                "Quiet": True,
            },
        )

    def _key(self, suffix: str) -> str:
        suffix = suffix.lstrip("/")
        return f"{self.prefix}/{suffix}" if self.prefix else suffix


def _is_missing_key_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not response:
        return False
    code = response.get("Error", {}).get("Code")
    return code in {"NoSuchKey", "404", "NotFound"}
