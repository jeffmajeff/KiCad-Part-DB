"""Parts catalog operations: the only module that reads and writes part data.

The CLI, the KiCad plugin and any future UI call these functions rather than writing SQL.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from typing import Any

from partsdb.ipn import PREFIX_RE, next_ipn
from partsdb.validate import validate_part


class CatalogError(Exception):
    """Base class for expected, user-facing failures."""


class ValidationError(CatalogError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class NotFoundError(CatalogError):
    pass


class DuplicateError(CatalogError):
    pass


# --- categories -------------------------------------------------------------------------


def add_category(conn: sqlite3.Connection, name: str, prefix: str) -> sqlite3.Row:
    name = name.strip()
    prefix = prefix.strip().upper()
    if not name:
        raise ValidationError(["category name is required"])
    if not PREFIX_RE.match(prefix):
        raise ValidationError([f"prefix {prefix!r} must be 2 to 5 letters"])
    try:
        with conn:
            conn.execute("INSERT INTO categories(name, ipn_prefix) VALUES (?, ?)", (name, prefix))
    except sqlite3.IntegrityError as exc:
        raise DuplicateError(
            f"category name or prefix already exists ({name!r}, {prefix!r})"
        ) from exc
    return get_category(conn, prefix)


def get_category(conn: sqlite3.Connection, key: str) -> sqlite3.Row:
    """Look a category up by name (case-insensitive) or by IPN prefix."""
    row = conn.execute(
        "SELECT * FROM categories WHERE lower(name) = lower(?) OR ipn_prefix = upper(?)",
        (key.strip(), key.strip()),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"no category matching {key!r}")
    return row


def list_categories(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM parts p WHERE p.category_id = c.id) AS part_count "
        "FROM categories c ORDER BY c.name"
    ).fetchall()


# --- parts ------------------------------------------------------------------------------


def add_part(
    conn: sqlite3.Connection,
    *,
    category: str,
    description: str,
    symbol_ref: str,
    footprint_ref: str,
    value: str | None = None,
    package: str | None = None,
    attributes: Mapping[str, Any] | None = None,
    datasheet_url: str | None = None,
    lifecycle: str = "active",
    preferred: bool = False,
    notes: str | None = None,
    manufacturer: str | None = None,
    mpn: str | None = None,
) -> str:
    """Validate and insert a part, returning its new IPN.

    If ``mpn`` is given, ``manufacturer`` is required and the pair is stored as the
    primary (rank 1) source.
    """
    cat = get_category(conn, category)
    attributes = dict(attributes or {})

    fields = {
        "description": description,
        "symbol_ref": symbol_ref,
        "footprint_ref": footprint_ref,
        "value": value,
        "package": package,
        "lifecycle": lifecycle,
        "attributes": attributes,
    }
    errors = validate_part(fields, cat["ipn_prefix"])
    if bool(mpn) != bool(manufacturer):
        errors.append("manufacturer and mpn must be given together")
    if errors:
        raise ValidationError(errors)

    if mpn and manufacturer:
        existing = _find_mpn(conn, manufacturer, mpn)
        if existing:
            raise DuplicateError(f"{manufacturer} {mpn} is already part {existing['ipn']}")

    with conn:
        ipn = next_ipn(conn, cat["id"])
        cursor = conn.execute(
            "INSERT INTO parts(ipn, category_id, description, value, package, attributes,"
            " symbol_ref, footprint_ref, datasheet_url, lifecycle, preferred, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ipn,
                cat["id"],
                description.strip(),
                value,
                package,
                json.dumps(attributes, sort_keys=True),
                symbol_ref,
                footprint_ref,
                datasheet_url,
                lifecycle,
                int(preferred),
                notes,
            ),
        )
        if mpn and manufacturer:
            _insert_mpn_option(conn, cursor.lastrowid, manufacturer, mpn, rank=1)
    return ipn


def add_mpn_option(
    conn: sqlite3.Connection, ipn: str, manufacturer: str, mpn: str, rank: int | None = None
) -> None:
    """Attach another manufacturer part number (e.g. a second source) to an existing part."""
    part = get_part(conn, ipn)
    existing = _find_mpn(conn, manufacturer, mpn)
    if existing:
        raise DuplicateError(f"{manufacturer} {mpn} is already part {existing['ipn']}")
    if rank is None:
        rank = conn.execute(
            "SELECT COALESCE(MAX(rank), 0) + 1 FROM mpn_options WHERE part_id = ?",
            (part["id"],),
        ).fetchone()[0]
    with conn:
        _insert_mpn_option(conn, part["id"], manufacturer, mpn, rank)


def get_part(conn: sqlite3.Connection, ipn: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT p.*, c.name AS category FROM parts p JOIN categories c ON c.id = p.category_id"
        " WHERE p.ipn = ?",
        (ipn.strip().upper(),),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"no part with IPN {ipn!r}")
    return row


def get_mpn_options(conn: sqlite3.Connection, part_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT mo.rank, m.name AS manufacturer, mo.mpn FROM mpn_options mo"
        " JOIN manufacturers m ON m.id = mo.manufacturer_id"
        " WHERE mo.part_id = ? ORDER BY mo.rank, mo.id",
        (part_id,),
    ).fetchall()


# --- search -----------------------------------------------------------------------------


def _fts_query(text: str) -> str | None:
    """Turn free text into an FTS5 query: every token must match, as a prefix."""
    tokens = [re.sub(r'["\s]', "", token) for token in text.split()]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None
    return " ".join(f'"{token}"*' for token in tokens)


def search(
    conn: sqlite3.Connection,
    query: str | None = None,
    *,
    category: str | None = None,
    lifecycle: str | None = None,
    preferred_only: bool = False,
    limit: int = 50,
) -> list[sqlite3.Row]:
    """Search parts by free text (IPN, description, value, package, MPN) plus filters."""
    sql = [
        "SELECT p.ipn, c.name AS category, p.value, p.package, p.description, p.lifecycle,",
        "       p.preferred, m.name AS manufacturer, mo.mpn AS mpn",
        "FROM parts p",
        "JOIN categories c ON c.id = p.category_id",
        "LEFT JOIN mpn_options mo ON mo.part_id = p.id AND mo.rank = 1",
        "LEFT JOIN manufacturers m ON m.id = mo.manufacturer_id",
    ]
    where: list[str] = []
    params: list[Any] = []

    fts = _fts_query(query) if query else None
    if query and fts is None:
        return []
    if fts:
        where.append(
            "(p.id IN (SELECT rowid FROM parts_fts WHERE parts_fts MATCH ?)"
            " OR p.id IN (SELECT part_id FROM mpn_options WHERE mpn LIKE ? ESCAPE '\\'))"
        )
        params.append(fts)
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"{escaped}%")
    if category:
        cat = get_category(conn, category)
        where.append("p.category_id = ?")
        params.append(cat["id"])
    if lifecycle:
        where.append("p.lifecycle = ?")
        params.append(lifecycle)
    if preferred_only:
        where.append("p.preferred = 1")

    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY p.preferred DESC, p.ipn LIMIT ?")
    params.append(limit)
    return conn.execute("\n".join(sql), params).fetchall()


# --- helpers ----------------------------------------------------------------------------


def _find_mpn(conn: sqlite3.Connection, manufacturer: str, mpn: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT p.ipn FROM mpn_options mo"
        " JOIN manufacturers m ON m.id = mo.manufacturer_id"
        " JOIN parts p ON p.id = mo.part_id"
        " WHERE lower(m.name) = lower(?) AND mo.mpn = ?",
        (manufacturer.strip(), mpn.strip()),
    ).fetchone()


def _insert_mpn_option(
    conn: sqlite3.Connection, part_id: int, manufacturer: str, mpn: str, rank: int
) -> None:
    manufacturer = manufacturer.strip()
    row = conn.execute(
        "SELECT id FROM manufacturers WHERE lower(name) = lower(?)", (manufacturer,)
    ).fetchone()
    if row is None:
        manufacturer_id = conn.execute(
            "INSERT INTO manufacturers(name) VALUES (?)", (manufacturer,)
        ).lastrowid
    else:
        manufacturer_id = row["id"]
    conn.execute(
        "INSERT INTO mpn_options(part_id, manufacturer_id, mpn, rank) VALUES (?, ?, ?, ?)",
        (part_id, manufacturer_id, mpn.strip(), rank),
    )
