"""Internal part number (IPN) generation.

An IPN is the category prefix plus a zero-padded counter, e.g. ``RES-0001``. The counter
lives on the category row and only ever increases, so an IPN is never reused, even if the
part that held it is later deleted.
"""

from __future__ import annotations

import re
import sqlite3

PREFIX_RE = re.compile(r"^[A-Z]{2,5}$")
IPN_RE = re.compile(r"^([A-Z]{2,5})-(\d{4,})$")


def format_ipn(prefix: str, seq: int) -> str:
    return f"{prefix}-{seq:04d}"


def parse_ipn(ipn: str) -> tuple[str, int]:
    """Split an IPN into (prefix, sequence). Raises ValueError if it is malformed."""
    match = IPN_RE.match(ipn)
    if not match:
        raise ValueError(f"not a valid IPN: {ipn!r}")
    return match.group(1), int(match.group(2))


def next_ipn(conn: sqlite3.Connection, category_id: int) -> str:
    """Reserve and return the next IPN for a category.

    Must be called inside the same transaction that inserts the part, so a failed insert
    rolls the counter back too.
    """
    row = conn.execute(
        "SELECT ipn_prefix, next_seq FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f"no category with id {category_id}")
    conn.execute("UPDATE categories SET next_seq = next_seq + 1 WHERE id = ?", (category_id,))
    return format_ipn(row["ipn_prefix"], row["next_seq"])
