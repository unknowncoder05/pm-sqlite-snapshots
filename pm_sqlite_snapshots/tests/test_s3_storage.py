import json

from pm_sqlite_snapshots.storage.s3 import S3SnapshotStorage


class FakeBody:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class FakePaginator:
    def __init__(self, client):
        self.client = client

    def paginate(self, Bucket, Prefix):
        contents = [
            {"Key": key}
            for (bucket, key) in self.client.objects
            if bucket == Bucket and key.startswith(Prefix)
        ]
        return [{"Contents": contents}]


class FakeS3Client:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.objects = {}
        self.uploads = []
        self.puts = []
        self.deleted = []

    def upload_file(self, filename, bucket, key, **kwargs):
        self.uploads.append((filename, bucket, key, kwargs))
        with open(filename, "rb") as fh:
            self.objects[(bucket, key)] = fh.read()

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]

    def get_object(self, Bucket, Key):
        try:
            body = self.objects[(Bucket, Key)]
        except KeyError:
            raise self.exceptions.NoSuchKey()
        return {"Body": FakeBody(body)}

    def download_file(self, bucket, key, destination_path):
        with open(destination_path, "wb") as fh:
            fh.write(self.objects[(bucket, key)])

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self)

    def delete_objects(self, Bucket, Delete):
        self.deleted.append((Bucket, Delete))


def test_s3_upload_writes_snapshot_manifest_then_latest_with_kms_args(tmp_path, monkeypatch):
    client = FakeS3Client()
    monkeypatch.setattr("pm_sqlite_snapshots.storage.s3.boto3.client", lambda *args, **kwargs: client)
    db_path = tmp_path / "db.sqlite3.gz"
    db_path.write_bytes(b"compressed")

    storage = S3SnapshotStorage(
        bucket="snapshots",
        prefix="app/sqlite",
        region="us-east-1",
        server_side_encryption="aws:kms",
        kms_key_id="alias/sqlite-snapshots",
    )
    ref = storage.upload(str(db_path), _manifest())

    assert ref.snapshot_id == "20260528T120000000000Z"
    assert client.uploads[0][2].endswith(".sqlite3.gz")
    assert client.uploads[0][3] == {
        "ExtraArgs": {
            "ServerSideEncryption": "aws:kms",
            "SSEKMSKeyId": "alias/sqlite-snapshots",
        }
    }
    assert client.puts[0]["Key"].endswith(".manifest.json")
    assert client.puts[1]["Key"] == "app/sqlite/latest.json"
    assert all(put["ServerSideEncryption"] == "aws:kms" for put in client.puts)
    assert all(put["SSEKMSKeyId"] == "alias/sqlite-snapshots" for put in client.puts)


def test_s3_latest_and_list_read_manifest_objects(tmp_path, monkeypatch):
    client = FakeS3Client()
    monkeypatch.setattr("pm_sqlite_snapshots.storage.s3.boto3.client", lambda *args, **kwargs: client)
    storage = S3SnapshotStorage(bucket="snapshots", prefix="app/sqlite")
    db_path = tmp_path / "db.sqlite3.gz"
    db_path.write_bytes(b"compressed")
    uploaded = storage.upload(str(db_path), _manifest())

    latest = storage.latest()
    listed = storage.list()

    assert latest == uploaded
    assert [snapshot.snapshot_id for snapshot in listed] == [uploaded.snapshot_id]


def test_s3_download_uses_snapshot_database_key(tmp_path, monkeypatch):
    client = FakeS3Client()
    monkeypatch.setattr("pm_sqlite_snapshots.storage.s3.boto3.client", lambda *args, **kwargs: client)
    storage = S3SnapshotStorage(bucket="snapshots", prefix="app/sqlite")
    db_path = tmp_path / "db.sqlite3.gz"
    db_path.write_bytes(b"compressed")
    ref = storage.upload(str(db_path), _manifest())
    destination = tmp_path / "downloaded.sqlite3.gz"

    storage.download(ref, str(destination))

    assert destination.read_bytes() == b"compressed"


def _manifest():
    return {
        "snapshot_id": "20260528T120000000000Z",
        "created_at": "2026-05-28T12:00:00Z",
        "sha256": "abc123",
        "database_alias": "default",
        "database_path": "/tmp/app.sqlite3",
        "compressed_size_bytes": 10,
        "uncompressed_size_bytes": 20,
        "django_migrations": {},
        "source": {},
    }
