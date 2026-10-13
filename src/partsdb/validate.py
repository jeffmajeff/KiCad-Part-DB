"""Validation rules for new and edited parts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

LIFECYCLES = ("active", "nrnd", "eol", "obsolete")

# KiCad references look like 'Library:Name'.
LIB_REF_RE = re.compile(r"^[^:\s]+:[^:\s]+$")

# Fields that must be filled in for specific categories, keyed by IPN prefix.
REQUIRED_BY_PREFIX: dict[str, tuple[str, ...]] = {
    "RES": ("value", "package"),
    "CAP": ("value", "package"),
    "IND": ("value", "package"),
    "LED": ("package",),
}


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate_part(fields: Mapping[str, Any], category_prefix: str) -> list[str]:
    """Return a list of human-readable problems; an empty list means the part is valid.

    ``fields`` may contain: description, symbol_ref, footprint_ref, value, package,
    lifecycle, attributes (a dict).
    """
    errors: list[str] = []

    if _blank(fields.get("description")):
        errors.append("description is required")

    symbol = fields.get("symbol_ref")
    if _blank(symbol):
        errors.append("symbol_ref is required (format 'Library:Symbol')")
    elif not LIB_REF_RE.match(str(symbol)):
        errors.append(f"symbol_ref {symbol!r} must look like 'Library:Symbol'")

    footprint = fields.get("footprint_ref")
    if _blank(footprint):
        errors.append("footprint_ref is required (format 'Library:Footprint')")
    elif not LIB_REF_RE.match(str(footprint)):
        errors.append(f"footprint_ref {footprint!r} must look like 'Library:Footprint'")

    lifecycle = fields.get("lifecycle", "active")
    if lifecycle not in LIFECYCLES:
        errors.append(f"lifecycle {lifecycle!r} must be one of: {', '.join(LIFECYCLES)}")

    attributes = fields.get("attributes", {})
    if not isinstance(attributes, Mapping):
        errors.append("attributes must be a JSON object")

    for name in REQUIRED_BY_PREFIX.get(category_prefix, ()):
        if _blank(fields.get(name)):
            errors.append(f"{name} is required for category prefix {category_prefix}")

    return errors
