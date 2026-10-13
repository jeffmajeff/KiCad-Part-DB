import sqlite3

import pytest

from partsdb.db import connect, latest_version, migrate, schema_version


def test_migrate_creates_schema_and_sets_version(conn):
    assert schema_version(conn) == latest_version() >= 1
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
    }
    assert {
        "parts",
        "categories",
        "mpn_options",
        "offers",
        "designs",
        "design_usage",
        "tags",
        "part_tags",
        "parts_fts",
        "kicad_parts",
    } <= tables


def test_migrate_is_idempotent(conn):
    version = schema_version(conn)
    assert migrate(conn) == version


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO parts(ipn, category_id, description, symbol_ref, footprint_ref)"
            " VALUES ('X-0001', 999, 'd', 'A:B', 'C:D')"
        )


def test_lifecycle_check_constraint(conn):
    conn.execute("INSERT INTO categories(name, ipn_prefix) VALUES ('Resistor', 'RES')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO parts(ipn, category_id, description, symbol_ref, footprint_ref, lifecycle)"
            " VALUES ('RES-0001', 1, 'd', 'A:B', 'C:D', 'bogus')"
        )


def test_database_file_persists(tmp_path):
    path = tmp_path / "parts.sqlite"
    first = connect(path)
    migrate(first)
    first.close()
    second = connect(path)
    assert schema_version(second) == latest_version()
