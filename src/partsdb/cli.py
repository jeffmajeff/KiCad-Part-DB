"""Command line interface: ``parts <command>``."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from partsdb import __version__, catalog
from partsdb.catalog import CatalogError, ValidationError
from partsdb.db import connect, latest_version, migrate, schema_version

DEFAULT_DB = "data/parts.sqlite"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parts", description="Personal PCBA parts database.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--db",
        default=os.environ.get("PARTSDB_DB", DEFAULT_DB),
        help=f"path to the SQLite database (default: $PARTSDB_DB or {DEFAULT_DB})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database or apply pending migrations")

    p = sub.add_parser("add-category", help="add a part category")
    p.add_argument("name", help="e.g. 'Resistor'")
    p.add_argument("prefix", help="2-5 letter IPN prefix, e.g. RES")

    sub.add_parser("categories", help="list categories")

    p = sub.add_parser("add", help="add a part (prompts for missing required fields)")
    p.add_argument("--category", help="category name or IPN prefix")
    p.add_argument("--description")
    p.add_argument("--symbol", help="KiCad symbol, e.g. Device:R")
    p.add_argument("--footprint", help="KiCad footprint, e.g. Resistor_SMD:R_0402_1005Metric")
    p.add_argument("--value")
    p.add_argument("--package")
    p.add_argument("--manufacturer")
    p.add_argument("--mpn")
    p.add_argument("--datasheet")
    p.add_argument("--lifecycle", default="active")
    p.add_argument("--preferred", action="store_true")
    p.add_argument("--notes")
    p.add_argument(
        "--attr",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="category-specific attribute, repeatable (e.g. --attr tolerance=1%%)",
    )

    p = sub.add_parser("search", help="search parts")
    p.add_argument("query", nargs="*", help="free text: value, package, description, MPN, IPN")
    p.add_argument("--category")
    p.add_argument("--lifecycle")
    p.add_argument("--preferred", action="store_true", help="only preferred parts")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("show", help="show one part in full")
    p.add_argument("ipn")

    p = sub.add_parser("add-mpn", help="add an alternate manufacturer part number to a part")
    p.add_argument("ipn")
    p.add_argument("manufacturer")
    p.add_argument("mpn")

    return parser


def _open(path: str, *, create: bool) -> sqlite3.Connection:
    db_path = Path(path)
    if not create and not db_path.exists():
        raise CatalogError(f"database {path!r} not found; run 'parts init' first")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    if schema_version(conn) < latest_version():
        if not create:
            raise CatalogError(f"database {path!r} needs migration; run 'parts init'")
    return conn


def _ask(label: str, current: str | None) -> str | None:
    if current or not sys.stdin.isatty():
        return current
    answer = input(f"{label}: ").strip()
    return answer or None


def _parse_attrs(pairs: list[str]) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for pair in pairs:
        key, sep, val = pair.partition("=")
        if not sep or not key.strip():
            raise CatalogError(f"--attr {pair!r} must look like KEY=VALUE")
        attrs[key.strip()] = val.strip()
    return attrs


def _table(rows: Sequence[Sequence[object]], headers: Sequence[str]) -> str:
    cells = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [
        max(len(h), *(len(r[i]) for r in cells)) if cells else len(h) for i, h in enumerate(headers)
    ]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True)).rstrip()
    out = [line, "  ".join("-" * w for w in widths)]
    for row in cells:
        out.append("  ".join(v.ljust(w) for v, w in zip(row, widths, strict=True)).rstrip())
    return "\n".join(out)


def _cmd_init(args: argparse.Namespace) -> int:
    conn = _open(args.db, create=True)
    before = schema_version(conn)
    after = migrate(conn)
    if after == before:
        print(f"{args.db}: already at schema version {after}")
    else:
        print(f"{args.db}: migrated schema version {before} -> {after}")
    return 0


def _cmd_add_category(args: argparse.Namespace) -> int:
    conn = _open(args.db, create=False)
    cat = catalog.add_category(conn, args.name, args.prefix)
    print(f"added category {cat['name']} ({cat['ipn_prefix']})")
    return 0


def _cmd_categories(args: argparse.Namespace) -> int:
    conn = _open(args.db, create=False)
    rows = catalog.list_categories(conn)
    print(
        _table(
            [(r["ipn_prefix"], r["name"], r["part_count"]) for r in rows],
            ("PREFIX", "NAME", "PARTS"),
        )
    )
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    conn = _open(args.db, create=False)
    category = _ask("Category (name or prefix)", args.category)
    description = _ask("Description", args.description)
    symbol = _ask("KiCad symbol (Library:Symbol)", args.symbol)
    footprint = _ask("KiCad footprint (Library:Footprint)", args.footprint)
    if not all((category, description, symbol, footprint)):
        raise ValidationError(["category, description, --symbol and --footprint are required"])
    ipn = catalog.add_part(
        conn,
        category=category,
        description=description,
        symbol_ref=symbol,
        footprint_ref=footprint,
        value=args.value,
        package=args.package,
        attributes=_parse_attrs(args.attr),
        datasheet_url=args.datasheet,
        lifecycle=args.lifecycle,
        preferred=args.preferred,
        notes=args.notes,
        manufacturer=args.manufacturer,
        mpn=args.mpn,
    )
    print(ipn)
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    conn = _open(args.db, create=False)
    rows = catalog.search(
        conn,
        " ".join(args.query) or None,
        category=args.category,
        lifecycle=args.lifecycle,
        preferred_only=args.preferred,
        limit=args.limit,
    )
    if not rows:
        print("no matching parts")
        return 1
    print(
        _table(
            [
                (
                    r["ipn"] + ("*" if r["preferred"] else ""),
                    r["category"],
                    r["value"],
                    r["package"],
                    r["manufacturer"],
                    r["mpn"],
                    r["lifecycle"] if r["lifecycle"] != "active" else "",
                    r["description"],
                )
                for r in rows
            ],
            ("IPN", "CATEGORY", "VALUE", "PACKAGE", "MFR", "MPN", "LIFECYCLE", "DESCRIPTION"),
        )
    )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    conn = _open(args.db, create=False)
    part = catalog.get_part(conn, args.ipn)
    print(f"{part['ipn']}  {part['description']}")
    for label, key in (
        ("Category", "category"),
        ("Value", "value"),
        ("Package", "package"),
        ("Symbol", "symbol_ref"),
        ("Footprint", "footprint_ref"),
        ("Datasheet", "datasheet_url"),
        ("Lifecycle", "lifecycle"),
        ("Notes", "notes"),
    ):
        if part[key]:
            print(f"  {label + ':':<11}{part[key]}")
    if part["preferred"]:
        print("  Preferred:  yes")
    attrs = json.loads(part["attributes"])
    for key, val in sorted(attrs.items()):
        print(f"  {key + ':':<11}{val}")
    for opt in catalog.get_mpn_options(conn, part["id"]):
        role = "primary" if opt["rank"] == 1 else f"alt {opt['rank']}"
        print(f"  Source ({role}): {opt['manufacturer']} {opt['mpn']}")
    return 0


def _cmd_add_mpn(args: argparse.Namespace) -> int:
    conn = _open(args.db, create=False)
    catalog.add_mpn_option(conn, args.ipn, args.manufacturer, args.mpn)
    print(f"added {args.manufacturer} {args.mpn} to {args.ipn.upper()}")
    return 0


_COMMANDS = {
    "init": _cmd_init,
    "add-category": _cmd_add_category,
    "categories": _cmd_categories,
    "add": _cmd_add,
    "search": _cmd_search,
    "show": _cmd_show,
    "add-mpn": _cmd_add_mpn,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except ValidationError as exc:
        for error in exc.errors:
            print(f"error: {error}", file=sys.stderr)
        return 2
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
