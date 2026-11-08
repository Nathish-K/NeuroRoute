"""Controlled, additive migration for the live ``requests`` table.

Adds the columns introduced by Task 1.4 (``complexity_class``,
``end_to_end_latency_ms``, ``created_at``) with ALTER TABLE ... ADD COLUMN.
``Base.metadata.create_all()`` never alters an existing table, hence this script.

Run from ``backend/``:

    python -m testing.migrate_requests_table            # dry run (default)
    python -m testing.migrate_requests_table --apply    # real run

The dry run only issues SELECT statements. ``--apply`` takes a JSON backup
first, records a row count and checksum, runs the missing statements one at a
time, and verifies that nothing changed except the added columns. The script
is idempotent: columns that already exist are skipped.
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("migrate_requests_table")

DEFAULT_TABLE = "requests"
DEFAULT_BACKUP_DIR = Path(__file__).resolve().parents[1] / "backups"
LEGACY_COLUMNS = ("id", "prompt", "status")
NEW_COLUMNS = ("complexity_class", "end_to_end_latency_ms", "created_at")
_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ABORT = 2
EXIT_VERIFY_FAILED = 3


def validate_table_name(name: str) -> str:
    """Return ``name`` if it is a safe identifier, otherwise raise ValueError."""
    if not isinstance(name, str) or not _TABLE_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Invalid table name: must match ^[A-Za-z_][A-Za-z0-9_]{0,63}$"
        )
    return name


def build_migration_statements(
    existing_columns: set[str], table: str = DEFAULT_TABLE
) -> list[str]:
    """Return the ADD COLUMN statements for columns missing from ``table``."""
    table = validate_table_name(table)
    statements: list[str] = []
    if "complexity_class" not in existing_columns:
        statements.append(
            f"ALTER TABLE {table} ADD COLUMN complexity_class VARCHAR(20) NULL"
        )
    if "end_to_end_latency_ms" not in existing_columns:
        statements.append(
            f"ALTER TABLE {table} ADD COLUMN end_to_end_latency_ms INT NULL"
        )
    if "created_at" not in existing_columns:
        statements.append(
            f"ALTER TABLE {table} ADD COLUMN created_at DATETIME "
            "NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )
    return statements


def get_existing_columns(conn: Connection, table: str) -> set[str]:
    """Read-only: names of the columns currently on ``table``."""
    table = validate_table_name(table)
    return {col["name"] for col in inspect(conn).get_columns(table)}


def count_rows(conn: Connection, table: str) -> int:
    """Read-only: number of rows in ``table``."""
    table = validate_table_name(table)
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


def fingerprint(conn: Connection, table: str) -> tuple[int, str]:
    """Read-only: (row_count, sha256 hex) over (id, prompt, status) ordered by id."""
    table = validate_table_name(table)
    rows = conn.execute(
        text(f"SELECT id, prompt, status FROM {table} ORDER BY id")
    ).fetchall()
    payload = "\n".join(
        json.dumps([row_id, prompt, status]) for row_id, prompt, status in rows
    )
    return len(rows), hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def backup_table(conn: Connection, table: str, backup_dir: Path) -> Path:
    """SELECT-only logical backup of every column of every row to a JSON file."""
    table = validate_table_name(table)
    result = conn.execute(text(f"SELECT * FROM {table} ORDER BY id"))
    columns = list(result.keys())
    rows = [dict(zip(columns, row)) for row in result.fetchall()]

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = backup_dir / f"{table}_{stamp}.json"
    payload = {"table": table, "columns": columns, "rows": rows}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, default=_json_default, indent=2)
    return path


def execute_statement(conn: Connection, statement: str) -> None:
    """Run one static migration statement and commit it."""
    conn.execute(text(statement))
    conn.commit()


def _verify(
    conn: Connection,
    table: str,
    before: tuple[int, str],
) -> list[str]:
    """Return a list of problems found after the migration (empty means OK)."""
    problems: list[str] = []
    after = fingerprint(conn, table)
    if after[0] != before[0]:
        problems.append(f"row count changed: {before[0]} -> {after[0]}")
    if after[1] != before[1]:
        problems.append("checksum of (id, prompt, status) changed")
    columns = get_existing_columns(conn, table)
    missing = [name for name in NEW_COLUMNS if name not in columns]
    if missing:
        problems.append("columns still missing: " + ", ".join(missing))
    elif count_nulls(conn, table, "created_at") != 0:
        problems.append("created_at contains NULL values")
    return problems


def count_nulls(conn: Connection, table: str, column: str) -> int:
    """Read-only: number of rows where ``column`` IS NULL."""
    table = validate_table_name(table)
    if column not in NEW_COLUMNS and column not in LEGACY_COLUMNS:
        raise ValueError("Unknown column")
    query = f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL"
    return int(conn.execute(text(query)).scalar_one())


def run_migration(
    conn: Connection,
    table: str = DEFAULT_TABLE,
    apply: bool = False,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
) -> int:
    """Dry-run or apply the migration on ``conn``; return a process exit code."""
    table = validate_table_name(table)
    existing = get_existing_columns(conn, table)
    row_count = count_rows(conn, table)
    statements = build_migration_statements(existing, table)

    logger.info("Table: %s", table)
    logger.info("Row count: %d", row_count)
    logger.info("Existing columns: %s", ", ".join(sorted(existing)))

    missing_legacy = [name for name in LEGACY_COLUMNS if name not in existing]
    if missing_legacy:
        logger.error(
            "Aborting: legacy column(s) missing: %s", ", ".join(missing_legacy)
        )
        return EXIT_ABORT

    if not statements:
        logger.info("Nothing to apply: all columns already exist.")
        return EXIT_OK

    if not apply:
        logger.info("DRY RUN: the following statements WOULD run:")
        for statement in statements:
            logger.info("  %s", statement)
        logger.info("Re-run with --apply to execute them. Nothing was changed.")
        return EXIT_OK

    # Backup first: no ALTER may run without a successful backup.
    try:
        backup_path = backup_table(conn, table, backup_dir)
    except Exception as exc:  # noqa: BLE001 - any failure must abort
        logger.error("Aborting: backup failed (%s). No changes were made.",
                     type(exc).__name__)
        return EXIT_ABORT
    logger.info("Backup written: %s", backup_path)

    before = fingerprint(conn, table)
    logger.info("Recorded fingerprint: %d rows, sha256 %s", before[0], before[1])

    for statement in statements:
        logger.info("Executing: %s", statement)
        execute_statement(conn, statement)

    problems = _verify(conn, table, before)
    if problems:
        for problem in problems:
            logger.error("Verification failed: %s", problem)
        logger.error(
            "MySQL DDL is not transactional, so a partial run is possible. "
            "Re-running is safe because the migration is idempotent."
        )
        return EXIT_VERIFY_FAILED

    logger.info("Verification passed: row count and checksum unchanged, "
                "new columns present, no NULL created_at.")
    return EXIT_OK


def _table_arg(value: str) -> str:
    try:
        return validate_table_name(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add the Task 1.4 columns to the requests table "
        "(dry run unless --apply is given)."
    )
    parser.add_argument("--apply", action="store_true",
                        help="execute the migration (default is a dry run)")
    parser.add_argument("--table", type=_table_arg, default=DEFAULT_TABLE,
                        help="table name (for rehearsal on a scratch copy)")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR,
                        help="directory for the JSON backup (default: backend/backups)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        from app.database.connection import engine  # lazy: no DB on import/--help

        with engine.connect() as conn:
            return run_migration(conn, args.table, args.apply, args.backup_dir)
    except SQLAlchemyError as exc:
        # Report only the error class and driver message; never the URL.
        logger.error("Database error (%s): %s", type(exc).__name__,
                     getattr(exc, "orig", None) or "see database logs")
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001
        logger.error("Migration failed (%s).", type(exc).__name__)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
