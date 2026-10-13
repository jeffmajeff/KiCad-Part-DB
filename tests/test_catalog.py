import json

import pytest

from partsdb import catalog


def test_add_part_returns_ipn_and_stores_fields(seeded):
    part = catalog.get_part(seeded, "res-0001")  # lookup is case-insensitive
    assert part["ipn"] == "RES-0001"
    assert part["category"] == "Resistor"
    assert part["value"] == "10k"
    assert part["footprint_ref"] == "Resistor_SMD:R_0402_1005Metric"
    assert part["preferred"] == 1
    assert json.loads(part["attributes"]) == {}


def test_attributes_are_stored_as_json(seeded):
    ipn = catalog.add_part(
        seeded,
        category="CAP",
        description="1uF 25V X5R",
        symbol_ref="Device:C",
        footprint_ref="Capacitor_SMD:C_0603_1608Metric",
        value="1uF",
        package="0603",
        attributes={"voltage": "25V", "dielectric": "X5R"},
    )
    stored = json.loads(catalog.get_part(seeded, ipn)["attributes"])
    assert stored == {"voltage": "25V", "dielectric": "X5R"}


def test_validation_errors_are_collected_and_nothing_is_written(seeded):
    with pytest.raises(catalog.ValidationError) as excinfo:
        catalog.add_part(
            seeded,
            category="RES",
            description="",
            symbol_ref="bad",
            footprint_ref="Resistor_SMD:R_0402_1005Metric",
        )
    assert len(excinfo.value.errors) >= 3  # description, symbol, value/package
    assert seeded.execute("SELECT COUNT(*) FROM parts").fetchone()[0] == 3


def test_mpn_and_manufacturer_must_come_together(seeded):
    with pytest.raises(catalog.ValidationError):
        catalog.add_part(
            seeded,
            category="ICM",
            description="mcu",
            symbol_ref="MCU:X",
            footprint_ref="Package:Y",
            mpn="ABC123",
        )


def test_unknown_category(seeded):
    with pytest.raises(catalog.NotFoundError):
        catalog.add_part(
            seeded, category="Widget", description="x", symbol_ref="A:B", footprint_ref="C:D"
        )


def test_duplicate_mpn_names_the_existing_part(seeded):
    with pytest.raises(catalog.DuplicateError, match="RES-0001"):
        catalog.add_part(
            seeded,
            category="RES",
            description="same part again",
            symbol_ref="Device:R",
            footprint_ref="Resistor_SMD:R_0402_1005Metric",
            value="10k",
            package="0402",
            manufacturer="yageo",  # manufacturer match is case-insensitive
            mpn="RC0402FR-0710KL",
        )


def test_add_alternate_mpn_gets_next_rank(seeded):
    catalog.add_mpn_option(seeded, "RES-0001", "Vishay", "CRCW040210K0FKED")
    options = catalog.get_mpn_options(seeded, catalog.get_part(seeded, "RES-0001")["id"])
    assert [(o["rank"], o["manufacturer"]) for o in options] == [(1, "Yageo"), (2, "Vishay")]


def test_duplicate_category_rejected(seeded):
    with pytest.raises(catalog.DuplicateError):
        catalog.add_category(seeded, "Resistors", "res")
    with pytest.raises(catalog.ValidationError):
        catalog.add_category(seeded, "Bad", "X")


def test_list_categories_counts_parts(seeded):
    counts = {r["ipn_prefix"]: r["part_count"] for r in catalog.list_categories(seeded)}
    assert counts == {"CAP": 1, "ICM": 1, "RES": 1}


@pytest.mark.parametrize(
    "query, expected",
    [
        ("10k", ["RES-0001"]),
        ("0402", ["RES-0001", "CAP-0001"]),  # preferred part sorts first
        ("ceramic", ["CAP-0001"]),
        ("100nF 0402", ["CAP-0001"]),  # every token must match
        ("STM32F405", ["ICM-0001"]),  # MPN prefix
        ("lqfp", ["ICM-0001"]),  # package prefix, case-insensitive
        ("RES-0001", ["RES-0001"]),
        ("nothing-matches-this", []),
        ('"; DROP TABLE parts; --', []),  # special characters are safe
    ],
)
def test_search_text(seeded, query, expected):
    assert [r["ipn"] for r in catalog.search(seeded, query)] == expected


def test_search_filters(seeded):
    assert [r["ipn"] for r in catalog.search(seeded, category="Capacitor")] == ["CAP-0001"]
    assert [r["ipn"] for r in catalog.search(seeded, lifecycle="nrnd")] == ["ICM-0001"]
    assert [r["ipn"] for r in catalog.search(seeded, preferred_only=True)] == ["RES-0001"]
    assert [r["ipn"] for r in catalog.search(seeded, "0402", category="RES")] == ["RES-0001"]


def test_search_with_no_query_lists_everything(seeded):
    assert len(catalog.search(seeded)) == 3


def test_search_index_follows_updates_and_deletes(seeded):
    with seeded:
        seeded.execute(
            "UPDATE parts SET value = '22k', description = '22k 1% resistor' WHERE ipn = 'RES-0001'"
        )
    assert catalog.search(seeded, "10k") == []
    assert [r["ipn"] for r in catalog.search(seeded, "22k")] == ["RES-0001"]
    with seeded:
        seeded.execute("DELETE FROM parts WHERE ipn = 'RES-0001'")
    assert catalog.search(seeded, "22k") == []


def test_kicad_view_exposes_primary_source(seeded):
    row = seeded.execute("SELECT * FROM kicad_parts WHERE ipn = 'RES-0001'").fetchone()
    assert dict(row) == {
        "ipn": "RES-0001",
        "symbol": "Device:R",
        "footprint": "Resistor_SMD:R_0402_1005Metric",
        "value": "10k",
        "description": "10k 1% thick film resistor",
        "datasheet": None,
        "category": "Resistor",
        "lifecycle": "active",
        "manufacturer": "Yageo",
        "mpn": "RC0402FR-0710KL",
    }
