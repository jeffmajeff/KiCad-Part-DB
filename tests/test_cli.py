import pytest

from partsdb.cli import main


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "sub" / "parts.sqlite")
    assert main(["--db", path, "init"]) == 0
    return path


def run(db, *args):
    return main(["--db", db, *args])


def test_init_is_repeatable(db, capsys):
    assert run(db, "init") == 0
    assert "already at schema version" in capsys.readouterr().out


def test_commands_need_an_initialised_database(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "missing.sqlite"), "categories"]) == 1
    assert "parts init" in capsys.readouterr().err


def test_add_search_show_flow(db, capsys):
    assert run(db, "add-category", "Resistor", "RES") == 0
    assert (
        run(
            db,
            "add",
            "--category",
            "RES",
            "--description",
            "10k 1% resistor",
            "--symbol",
            "Device:R",
            "--footprint",
            "Resistor_SMD:R_0402_1005Metric",
            "--value",
            "10k",
            "--package",
            "0402",
            "--manufacturer",
            "Yageo",
            "--mpn",
            "RC0402FR-0710KL",
            "--attr",
            "tolerance=1%",
        )
        == 0
    )
    assert capsys.readouterr().out.strip().endswith("RES-0001")

    assert run(db, "search", "10k", "0402") == 0
    out = capsys.readouterr().out
    assert "RES-0001" in out and "Yageo" in out

    assert run(db, "show", "RES-0001") == 0
    out = capsys.readouterr().out
    assert "tolerance:" in out and "Source (primary): Yageo RC0402FR-0710KL" in out

    assert run(db, "add-mpn", "RES-0001", "Vishay", "CRCW040210K0FKED") == 0
    assert run(db, "show", "RES-0001") == 0
    assert "Source (alt 2): Vishay CRCW040210K0FKED" in capsys.readouterr().out

    assert run(db, "categories") == 0
    assert "RES" in capsys.readouterr().out


def test_validation_failure_exits_2_and_lists_problems(db, capsys):
    run(db, "add-category", "Resistor", "RES")
    capsys.readouterr()
    code = run(
        db,
        "add",
        "--category",
        "RES",
        "--description",
        "r",
        "--symbol",
        "R",
        "--footprint",
        "Resistor_SMD:R_0402_1005Metric",
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "symbol_ref" in err and "value is required" in err


def test_search_with_no_results_exits_1(db, capsys):
    assert run(db, "search", "nothing") == 1
    assert "no matching parts" in capsys.readouterr().out


def test_bad_attr_is_rejected(db, capsys):
    run(db, "add-category", "Resistor", "RES")
    code = run(
        db,
        "add",
        "--category",
        "RES",
        "--description",
        "r",
        "--symbol",
        "Device:R",
        "--footprint",
        "A:B",
        "--value",
        "1k",
        "--package",
        "0402",
        "--attr",
        "oops",
    )
    assert code == 1
    assert "KEY=VALUE" in capsys.readouterr().err
