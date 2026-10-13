import pytest

from partsdb import catalog
from partsdb.db import connect, migrate


@pytest.fixture
def conn():
    connection = connect(":memory:")
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn):
    """A database with a few categories and parts."""
    catalog.add_category(conn, "Resistor", "RES")
    catalog.add_category(conn, "Capacitor", "CAP")
    catalog.add_category(conn, "IC - MCU", "ICM")
    catalog.add_part(
        conn,
        category="Resistor",
        description="10k 1% thick film resistor",
        symbol_ref="Device:R",
        footprint_ref="Resistor_SMD:R_0402_1005Metric",
        value="10k",
        package="0402",
        manufacturer="Yageo",
        mpn="RC0402FR-0710KL",
        preferred=True,
    )
    catalog.add_part(
        conn,
        category="Capacitor",
        description="100nF 16V X7R ceramic capacitor",
        symbol_ref="Device:C",
        footprint_ref="Capacitor_SMD:C_0402_1005Metric",
        value="100nF",
        package="0402",
        manufacturer="Murata",
        mpn="GRM155R71C104KA88D",
    )
    catalog.add_part(
        conn,
        category="IC - MCU",
        description="Cortex-M4 microcontroller",
        symbol_ref="MCU_ST_STM32F4:STM32F405RGTx",
        footprint_ref="Package_QFP:LQFP-64_10x10mm_P0.5mm",
        package="LQFP-64",
        manufacturer="STMicroelectronics",
        mpn="STM32F405RGT6",
        lifecycle="nrnd",
    )
    return conn
