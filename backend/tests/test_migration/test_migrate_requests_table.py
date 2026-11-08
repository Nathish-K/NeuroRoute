import json
import logging
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from testing import migrate_requests_table as mig

PROMPTS = [
    "Explain how RAG works",
    "Explain how ML works",
    "Hi How are you",
    "who are you",
]
STATUSES = ["completed", "completed", "pending", "pending"]
ALL = {"complexity_class", "end_to_end_latency_ms", "created_at"}
FORBIDDEN = ("DROP", "TRUNCATE", "DELETE", "UPDATE", "INSERT", "CREATE")


@pytest.fixture()
def conn():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        yield connection


def make_table(conn, extra_columns: str = "") -> None:
    conn.execute(text(
        "CREATE TABLE requests (id INTEGER PRIMARY KEY, prompt VARCHAR(1000) "
        f"NOT NULL, status VARCHAR(50){extra_columns})"
    ))
    for i, (prompt, status) in enumerate(zip(PROMPTS, STATUSES), start=1):
        if extra_columns:
            conn.execute(
                text("INSERT INTO requests (id, prompt, status, created_at) "
                     "VALUES (:i, :p, :s, '2024-01-01 00:00:00')"),
                {"i": i, "p": prompt, "s": status},
            )
        else:
            conn.execute(
                text("INSERT INTO requests (id, prompt, status) VALUES (:i, :p, :s)"),
                {"i": i, "p": prompt, "s": status},
            )
    conn.commit()


# --- build_migration_statements -------------------------------------------

def test_all_missing_gives_three_statements_in_order():
    stmts = mig.build_migration_statements(set())
    assert stmts == [
        "ALTER TABLE requests ADD COLUMN complexity_class VARCHAR(20) NULL",
        "ALTER TABLE requests ADD COLUMN end_to_end_latency_ms INT NULL",
        "ALTER TABLE requests ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
    ]


def test_only_created_at_missing():
    stmts = mig.build_migration_statements({"complexity_class", "end_to_end_latency_ms"})
    assert len(stmts) == 1 and "created_at" in stmts[0]


def test_none_missing_gives_empty_list():
    assert mig.build_migration_statements(set(ALL)) == []


@pytest.mark.parametrize("present", [
    {"complexity_class"}, {"end_to_end_latency_ms"}, {"created_at"},
    {"complexity_class", "created_at"},
])
def test_partial_combinations(present):
    stmts = mig.build_migration_statements(present)
    assert len(stmts) == 3 - len(present)
    for col in present:
        assert not any(f"ADD COLUMN {col} " in s for s in stmts)


def test_statements_are_additive_only():
    for stmt in mig.build_migration_statements(set(), "requests_scratch"):
        assert stmt.startswith("ALTER TABLE")
        assert "ADD COLUMN" in stmt
        # Whole words only: the column name created_at contains "CREATE".
        assert not re.search(r"\b(" + "|".join(FORBIDDEN) + r")\b", stmt, re.I)


# --- validate_table_name --------------------------------------------------

@pytest.mark.parametrize("name", ["requests", "requests_scratch", "_x1"])
def test_valid_table_names(name):
    assert mig.validate_table_name(name) == name


@pytest.mark.parametrize("name", [
    "requests; DROP TABLE x", "a b", "1abc", "", "a'b", 'a"b', "a`b",
    "a-b", "a.b", "a" * 65,
])
def test_invalid_table_names(name):
    with pytest.raises(ValueError):
        mig.validate_table_name(name)


def test_cli_rejects_bad_table():
    with pytest.raises(SystemExit):
        mig.build_parser().parse_args(["--table", "requests; DROP TABLE x"])


# --- backup and fingerprint -----------------------------------------------

def test_backup_and_fingerprint(conn, tmp_path, caplog):
    make_table(conn)
    with caplog.at_level(logging.DEBUG):
        path = mig.backup_table(conn, "requests", tmp_path / "bk")
        first = mig.fingerprint(conn, "requests")
        second = mig.fingerprint(conn, "requests")
    assert path.parent == tmp_path / "bk" and path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["rows"]) == 4
    assert first == second and first[0] == 4
    conn.execute(text("UPDATE requests SET status = 'failed' WHERE id = 1"))
    conn.commit()
    assert mig.fingerprint(conn, "requests") != first
    assert not any(p in caplog.text for p in PROMPTS)


# --- run_migration --------------------------------------------------------

def make_partial(conn):
    make_table(conn, ", created_at DATETIME NOT NULL DEFAULT '2024-01-01 00:00:00'")


def test_full_apply_flow(conn, tmp_path):
    make_partial(conn)
    before = mig.fingerprint(conn, "requests")
    executed: list[str] = []
    original = mig.execute_statement

    def recording(c, stmt):
        executed.append(stmt)
        original(c, stmt)

    mig.execute_statement = recording
    try:
        assert mig.run_migration(conn, "requests", True, tmp_path) == 0
        assert len(executed) == 2
        assert mig.fingerprint(conn, "requests") == before
        assert ALL <= mig.get_existing_columns(conn, "requests")
        executed.clear()
        assert mig.run_migration(conn, "requests", True, tmp_path) == 0
        assert executed == []
    finally:
        mig.execute_statement = original


def test_backup_runs_before_alter(conn, tmp_path, monkeypatch):
    make_partial(conn)
    events: list[str] = []
    real_backup, real_exec = mig.backup_table, mig.execute_statement
    monkeypatch.setattr(mig, "backup_table",
                        lambda *a, **k: (events.append("backup"), real_backup(*a, **k))[1])
    monkeypatch.setattr(mig, "execute_statement",
                        lambda c, s: (events.append("alter"), real_exec(c, s))[1])
    assert mig.run_migration(conn, "requests", True, tmp_path) == 0
    assert events == ["backup", "alter", "alter"]


def test_failing_backup_aborts_without_alter(conn, tmp_path, monkeypatch):
    make_partial(conn)
    altered: list[str] = []

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(mig, "backup_table", boom)
    monkeypatch.setattr(mig, "execute_statement", lambda c, s: altered.append(s))
    assert mig.run_migration(conn, "requests", True, tmp_path) != 0
    assert altered == []


def test_dry_run_changes_nothing(conn, tmp_path, monkeypatch):
    make_partial(conn)
    altered: list[str] = []
    monkeypatch.setattr(mig, "execute_statement", lambda c, s: altered.append(s))
    assert mig.run_migration(conn, "requests", False, tmp_path) == 0
    assert altered == []
    assert list(Path(tmp_path).iterdir()) == []
    assert "complexity_class" not in mig.get_existing_columns(conn, "requests")


def test_verification_failure_is_nonzero(conn, tmp_path, monkeypatch):
    make_partial(conn)
    real = mig.fingerprint
    calls = {"n": 0}

    def changing(c, t):
        calls["n"] += 1
        count, digest = real(c, t)
        return (count, digest if calls["n"] == 1 else "different")

    monkeypatch.setattr(mig, "fingerprint", changing)
    assert mig.run_migration(conn, "requests", True, tmp_path) == mig.EXIT_VERIFY_FAILED
