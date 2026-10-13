# KiCad-Part-DB

A personal database of every component used in your PCBA designs, plus a KiCad interface for
dropping those parts into a new design's BOM quickly.

**Status:** milestone 1 (foundation). The schema, core library and `parts` CLI exist. The KiCad
integration, BOM import and supplier sync come in later milestones.

## Architecture in one paragraph

One SQLite file is the source of truth. A Python core library (`partsdb`) is the only code that
reads or writes it. KiCad reads parts through its built-in Database Library (a `.kicad_dbl` file
plus ODBC) pointed at the `kicad_parts` view, and a thin KiCad plugin adds search and one-click
placement. A scheduled job refreshes supplier price, stock and lifecycle into a cache table, so
the editor never calls supplier APIs.

## Quick start

```sh
uv venv && uv pip install -e ".[dev]"      # or: python -m venv .venv && pip install -e ".[dev]"
parts init                                   # creates data/parts.sqlite
parts add-category Resistor RES
parts add-category Capacitor CAP
parts add --category RES --description "10k 1% thick film resistor" \
  --symbol Device:R --footprint Resistor_SMD:R_0402_1005Metric \
  --value 10k --package 0402 --manufacturer Yageo --mpn RC0402FR-0710KL
parts search 10k 0402
parts show RES-0001
```

Use `--db PATH` or the `PARTSDB_DB` environment variable to point at a different database.

## Commands

| Command | What it does |
| --- | --- |
| `parts init` | Create the database or apply pending schema migrations |
| `parts add-category NAME PREFIX` | Add a category with a 2-5 letter IPN prefix |
| `parts categories` | List categories and part counts |
| `parts add ...` | Add a part; prompts for missing required fields when run in a terminal |
| `parts add-mpn IPN MANUFACTURER MPN` | Add an alternate source to an existing part |
| `parts search [TEXT ...]` | Search by value, package, description, MPN or IPN, with filters |
| `parts show IPN` | Show one part in full |

## Key conventions

- **IPN** (internal part number) is the category prefix plus a counter, e.g. `RES-0001`. It is
  never reused, even after a part is deleted. MPNs may change; the IPN does not.
- **Symbol and footprint** are stored as KiCad references (`Library:Name`) and must exist in
  your KiCad libraries.
- **Category-specific specs** (tolerance, voltage, dielectric) live in a JSON `attributes` column,
  so a new category needs no migration.
- **Schema changes** are numbered SQL files in `src/partsdb/db/migrations/`, applied in order by
  `parts init`. The version is tracked in `PRAGMA user_version`.

## Development

```sh
pytest          # unit tests run against in-memory SQLite; KiCad is not needed
ruff check .    # lint
```

## Roadmap

1. **Foundation** (this milestone): schema, migrations, core library, `parts add`.
2. **Backfill:** `parts import-bom` to load past designs and fill `design_usage`.
3. **KiCad chooser:** generate the `.kicad_dbl` file and document ODBC setup.
4. **Search plugin and sync:** in-editor search, used-in view, supplier clients, lifecycle warnings.
