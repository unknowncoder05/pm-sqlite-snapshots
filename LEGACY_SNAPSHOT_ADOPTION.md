# Legacy SQLite Snapshot Adoption

Snapshots created before the identity receipt cannot pass the new startup gate.
Do not disable the gate or bootstrap a new namespace to work around this.

1. Pause all writers and retain the deployment's original snapshot bucket and prefix.
2. Verify the chosen snapshot ID, SHA-256, and expected application records against the original backup. Keep the original backup unchanged.
3. On a fresh instance with a missing SQLite database file, run the one-shot management command:
   `python manage.py dbsnapshot_adopt_legacy --snapshot-id ID --expected-sha256 SHA256`
4. The command restores the selected archive with checksum validation, writes the bound identity receipt, and exports a new snapshot. Confirm the new snapshot with `dbsnapshot_list` before starting the web service.
5. Resume the deployment only after pre-migration `dbsnapshot_prepare_startup` succeeds.

The adoption command refuses an existing destination database, an unknown snapshot,
or a checksum mismatch. A changed bucket or prefix requires recovery of the
original storage identity, not adoption into the changed namespace.
