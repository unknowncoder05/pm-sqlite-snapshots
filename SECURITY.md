# Security Analysis

`pm-sqlite-snapshots` stores complete SQLite database snapshots. Treat every
snapshot object as production data, not as a cache artifact.

## S3 Storage Behavior

The S3 backend writes three object types:

- `snapshots/<date>/<snapshot_id>.sqlite3.gz`
- `snapshots/<date>/<snapshot_id>.manifest.json`
- `latest.json`

Snapshot uploads are append-only by convention. `latest.json` is updated only
after the compressed database object and manifest object have been written. This
prevents a new latest pointer from referencing an incomplete upload.

The `.sqlite3.gz` object is compressed, but gzip is not encryption. Confidentiality
depends on S3 bucket policy, IAM, TLS in transit, and server-side or client-side
encryption.

## Recommended S3 Controls

- Use a private bucket with S3 Block Public Access enabled at the account and
  bucket level.
- Scope the ECS task role to one prefix, for example
  `arn:aws:s3:::my-bucket/my-app/sqlite/*`.
- Allow only the actions required by this package:
  `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, and `s3:ListBucket` with a
  prefix condition.
- Enable bucket versioning so overwritten `latest.json` versions are recoverable.
- Enable default bucket encryption, preferably SSE-KMS.
- Configure the package with `SERVER_SIDE_ENCRYPTION="aws:kms"` and a dedicated
  `KMS_KEY_ID` when using a customer-managed key.
- Restrict KMS decrypt permissions to the runtime role and operational break-glass
  roles.
- Enable S3 server access logging or CloudTrail data events for the snapshot
  prefix.
- Use lifecycle policies for retention, but do not expire all versions of
  `latest.json` until recovery procedures have been tested.

## Data Integrity

Each manifest includes a SHA-256 checksum of the compressed database object.
Restore verifies this checksum before replacing the local database. The restored
SQLite file is also checked with `PRAGMA integrity_check`.

## Residual Risks

- Snapshots can contain secrets, tokens, PII, and deleted application data until
  retention removes them.
- Anyone with `s3:GetObject` and KMS decrypt access can read the full database.
- Anyone with `s3:PutObject` on the prefix can tamper with future restore points
  unless IAM is tightly scoped and monitored.
- This package does not currently perform client-side encryption, object lock, or
  snapshot signing. Use SSE-KMS and least-privilege IAM as the minimum baseline.

## Production Guidance

This package is intended for single-writer ephemeral deployments. For high-value
production data, multi-replica writes, or strict recovery point objectives, use a
managed relational database such as RDS PostgreSQL with automated backups.
