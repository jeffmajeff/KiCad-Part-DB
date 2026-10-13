import pytest

from partsdb import catalog
from partsdb.ipn import format_ipn, next_ipn, parse_ipn


def test_format_and_parse_round_trip():
    assert format_ipn("RES", 1) == "RES-0001"
    assert format_ipn("CAP", 12345) == "CAP-12345"
    assert parse_ipn("RES-0042") == ("RES", 42)


@pytest.mark.parametrize("bad", ["res-0001", "RES0001", "RES-1", "R-0001", ""])
def test_parse_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_ipn(bad)


def test_sequences_are_per_category(seeded):
    cap = catalog.get_category(seeded, "CAP")
    res = catalog.get_category(seeded, "RES")
    assert next_ipn(seeded, cap["id"]) == "CAP-0002"
    assert next_ipn(seeded, res["id"]) == "RES-0002"


def test_ipn_is_never_reused_after_delete(seeded):
    assert catalog.get_part(seeded, "RES-0001")
    with seeded:
        seeded.execute("DELETE FROM parts WHERE ipn = 'RES-0001'")
    ipn = catalog.add_part(
        seeded,
        category="RES",
        description="1k resistor",
        symbol_ref="Device:R",
        footprint_ref="Resistor_SMD:R_0402_1005Metric",
        value="1k",
        package="0402",
    )
    assert ipn == "RES-0002"


def test_failed_insert_does_not_burn_a_number(seeded):
    with pytest.raises(catalog.DuplicateError):
        catalog.add_part(
            seeded,
            category="RES",
            description="dup",
            symbol_ref="Device:R",
            footprint_ref="Resistor_SMD:R_0402_1005Metric",
            value="10k",
            package="0402",
            manufacturer="Yageo",
            mpn="RC0402FR-0710KL",
        )
    row = seeded.execute("SELECT next_seq FROM categories WHERE ipn_prefix = 'RES'").fetchone()
    assert row["next_seq"] == 2
