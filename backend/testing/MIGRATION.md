# Migrating the `requests` table (Task 1.4a)

**Status: the script `migrate_requests_table.py` has NOT been applied to the live database as of its creation.** Only the read-only dry run has been used against it.

`Base.metadata.create_all()` never alters an existing table, so the three new `requests` columns (`complexity_class`, `end_to_end_latency_ms`, `created_at`) are added by this additive `ALTER TABLE ... ADD COLUMN` script. The script never drops, truncates, deletes, updates, inserts, or recreates anything.

## Prerequisites

- MySQL running locally and `backend/.env` filled in (see `backend/.env.example`).
- Virtual environment active. From `backend/`:

```powershell
.\.venv\Scripts\Activate.ps1
```

All commands below run from `backend/`.

## Step 1: Dry run

```powershell
python -m testing.migrate_requests_table
```

Logs the row count, the existing columns, and the statements that WOULD run. Executes only SELECTs.

## Step 2: Optional `mysqldump` backup

```powershell
mysqldump -u <user> -p neuroroute requests > backups\requests_manual.dump
```

`backups/` and `*.dump` are gitignored. The script also writes its own JSON backup automatically on `--apply` (`backend/backups/requests_<timestamp>.json`), and aborts without changes if that backup fails.

## Step 3: Scratch-table rehearsal

In MySQL Workbench or the mysql client:

```sql
CREATE TABLE requests_scratch LIKE requests;
INSERT INTO requests_scratch SELECT * FROM requests;
```

Then:

```powershell
python -m testing.migrate_requests_table --table requests_scratch
python -m testing.migrate_requests_table --table requests_scratch --apply
```

Verify on the scratch table:

```sql
SELECT COUNT(*) FROM requests_scratch;
DESCRIBE requests_scratch;
SELECT id, status, complexity_class, end_to_end_latency_ms, created_at FROM requests_scratch ORDER BY id;
```

When satisfied, remove ONLY the scratch table:

```sql
DROP TABLE requests_scratch;
```

## Step 4: Real apply (only after the user approves)

```powershell
python -m testing.migrate_requests_table --apply
```

The script: recomputes the missing columns, aborts if `id`/`prompt`/`status` is missing, takes the JSON backup, records a row count and SHA-256 fingerprint of `(id, prompt, status)`, runs each statement, then verifies row count, fingerprint, new columns, and no NULL `created_at`. Any mismatch gives a non-zero exit code.

## Step 5: Verification

```sql
SELECT id, status, complexity_class, end_to_end_latency_ms, created_at FROM requests ORDER BY id;
```

Expect:

- 4 rows, ids 1-4 unchanged (same prompts and statuses).
- The three new columns exist.
- `created_at` filled for the legacy rows with the migration time.
- `complexity_class` and `end_to_end_latency_ms` NULL for the legacy rows.

## Notes

- Re-running is a no-op: existing columns are skipped ("nothing to apply").
- Legacy rows share one `created_at`, so list queries order by `created_at DESC, id DESC`.
- There is no automatic rollback and none is needed: the change is additive and existing code ignores extra columns.
- MySQL DDL is not transactional. A partial run is possible; re-running is safe because of idempotence.
- The JSON backup is for inspection or manual restore. Do not commit it.
