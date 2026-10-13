from partsdb.validate import validate_part


def good(**overrides):
    fields = {
        "description": "10k resistor",
        "symbol_ref": "Device:R",
        "footprint_ref": "Resistor_SMD:R_0402_1005Metric",
        "value": "10k",
        "package": "0402",
        "lifecycle": "active",
        "attributes": {},
    }
    fields.update(overrides)
    return fields


def test_valid_part_has_no_errors():
    assert validate_part(good(), "RES") == []


def test_missing_required_fields_are_reported():
    errors = validate_part(good(description=" ", symbol_ref=None, footprint_ref=""), "ICM")
    assert len(errors) == 3
    assert any("description" in e for e in errors)
    assert any("symbol_ref" in e for e in errors)
    assert any("footprint_ref" in e for e in errors)


def test_library_refs_need_a_colon():
    errors = validate_part(good(symbol_ref="R", footprint_ref="Resistor_SMD/R_0402"), "RES")
    assert len(errors) == 2


def test_category_specific_requirements():
    assert validate_part(good(value=None), "RES") != []
    assert validate_part(good(package=""), "CAP") != []
    assert validate_part(good(value=None, package=None), "ICM") == []


def test_lifecycle_must_be_known():
    assert validate_part(good(lifecycle="retired"), "RES") != []
    assert validate_part(good(lifecycle="nrnd"), "RES") == []


def test_attributes_must_be_an_object():
    assert validate_part(good(attributes=["a"]), "RES") != []
