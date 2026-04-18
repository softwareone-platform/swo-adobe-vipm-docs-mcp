"""
Programmatic validator for VIPMP request bodies.

Takes a JSON body + an endpoint identifier; cross-checks every field
against the extracted schema (name, type, required-ness, constraints like
"Max: 35 characters") and returns a structured list of issues.

Scope (v1):
  - Top-level field validation only. Nested objects are not recursively
    validated yet — they'd need schema following (Customer → companyProfile
    → Address → …). We flag them as "not recursively validated".
  - Type strings in Adobe's docs are prose-ish ("String", "String (Enum)",
    "Array of Contact resources"). We parse common patterns pragmatically.
  - Constraint parsing handles the common shapes; unparsed constraints are
    reported as informational rather than errors.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .extractors import SchemaField, SchemaResource
from .index import IndexSnapshot, get_active_index
from .logging_config import get_logger

log = get_logger("validator")


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------


ISSUE_ERROR = "error"
ISSUE_WARNING = "warning"
ISSUE_INFO = "info"


@dataclass
class ValidationIssue:
    level: str  # ISSUE_ERROR / WARNING / INFO
    field: str | None  # top-level field path, or None for whole-body issues
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "field": self.field, "message": self.message}


@dataclass
class ValidationResult:
    endpoint: str  # "POST /v3/customers"
    schema_name: str | None  # resolved schema used for validation
    docs_path: str | None
    issues: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        return not any(i.level == ISSUE_ERROR for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.level == ISSUE_ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.level == ISSUE_WARNING)


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


def _normalise_type(type_str: str) -> str:
    """
    Collapse Adobe's prose types into a small set of categories we can check:
        "string" | "integer" | "number" | "boolean" | "array" | "object" | "unknown"
    """
    t = type_str.strip().lower()
    # Strip parenthetical modifiers (e.g. "String (Enum)", "String (datetime)")
    t = re.sub(r"\s*\(.*?\)\s*", "", t).strip()
    if t.startswith("array"):
        return "array"
    if t.endswith("resource") or t.endswith("resources") or t.endswith("object"):
        return "object"
    if t in {"string", "date", "datetime", "uuid", "email", "url", "uri"}:
        return "string"
    if t in {"integer", "int", "long", "short"}:
        return "integer"
    if t in {"number", "float", "double", "decimal"}:
        return "number"
    if t in {"boolean", "bool"}:
        return "boolean"
    return "unknown"


def _py_type_category(value: Any) -> str:
    if isinstance(value, bool):
        # Check before int — bool is a subclass of int.
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "unknown"


def _type_compatible(expected: str, actual: str) -> bool:
    """Soft type check. Unknown expected type always passes; integer and number are interchangeable."""
    if expected == "unknown":
        return True
    if expected == actual:
        return True
    # Adobe sometimes writes "Number" where "Integer" is also valid.
    # Adobe sometimes writes "Number" where "Integer" is also valid (and vice
    # versa — we treat int/number as interchangeable for soft checking).
    return {expected, actual} == {"integer", "number"}


# ---------------------------------------------------------------------------
# Constraint parsing
# ---------------------------------------------------------------------------


_MAX_CHARS_RE = re.compile(r"max[:\s]+(\d+)\s+char", re.IGNORECASE)
_MIN_CHARS_RE = re.compile(r"min[:\s]+(\d+)\s+char", re.IGNORECASE)
_MAX_VALUE_RE = re.compile(r"max[:\s]+(\d+)(?!\s*char)", re.IGNORECASE)
_MIN_VALUE_RE = re.compile(r"min[:\s]+(\d+)(?!\s*char)", re.IGNORECASE)


def _check_constraints(
    field: SchemaField, value: Any
) -> list[ValidationIssue]:
    """Best-effort constraint checking against Adobe's free-form limits prose."""
    c = field.constraints or ""
    if not c:
        return []
    issues: list[ValidationIssue] = []

    # Character length limits
    m = _MAX_CHARS_RE.search(c)
    if m and isinstance(value, str):
        limit = int(m.group(1))
        if len(value) > limit:
            issues.append(
                ValidationIssue(
                    ISSUE_ERROR,
                    field.name,
                    f"String too long: {len(value)} chars exceeds max {limit}.",
                )
            )
    m = _MIN_CHARS_RE.search(c)
    if m and isinstance(value, str):
        limit = int(m.group(1))
        if len(value) < limit:
            issues.append(
                ValidationIssue(
                    ISSUE_ERROR,
                    field.name,
                    f"String too short: {len(value)} chars below min {limit}.",
                )
            )

    # Numeric value limits
    m = _MAX_VALUE_RE.search(c)
    if m and isinstance(value, (int, float)) and not isinstance(value, bool):
        limit = int(m.group(1))
        if value > limit:
            issues.append(
                ValidationIssue(
                    ISSUE_ERROR,
                    field.name,
                    f"Value {value} exceeds max {limit}.",
                )
            )
    m = _MIN_VALUE_RE.search(c)
    if m and isinstance(value, (int, float)) and not isinstance(value, bool):
        limit = int(m.group(1))
        if value < limit:
            issues.append(
                ValidationIssue(
                    ISSUE_ERROR,
                    field.name,
                    f"Value {value} below min {limit}.",
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Endpoint → schema resolution
# ---------------------------------------------------------------------------


_ENDPOINT_RE = re.compile(r"^\s*(GET|POST|PATCH|PUT|DELETE)\s+(\S+)\s*$", re.IGNORECASE)


def _parse_endpoint(endpoint: str) -> tuple[str, str] | None:
    """Parse 'POST /v3/customers' into ('POST', '/v3/customers')."""
    m = _ENDPOINT_RE.match(endpoint)
    if not m:
        return None
    return m.group(1).upper(), m.group(2)


def resolve_schema(
    idx: IndexSnapshot, endpoint: str
) -> tuple[SchemaResource | None, str | None, str | None]:
    """
    Locate the request schema for an endpoint string.

    Returns (schema, endpoint_docs_path, error_message). On success the
    third value is None; on failure the first two are None and the third
    describes what went wrong.
    """
    parsed = _parse_endpoint(endpoint)
    if not parsed:
        return None, None, (
            f"Could not parse endpoint {endpoint!r}. Expected "
            "'METHOD /path' (e.g. 'POST /v3/customers')."
        )
    method, path = parsed

    # Exact endpoint lookup.
    matches = [
        ep for ep in idx.endpoints if ep.method == method and ep.path == path
    ]
    if not matches:
        # Be lenient about path variants — try matching just the last segment.
        suffix = path.rstrip("/").split("/")[-1]
        loose = [
            ep
            for ep in idx.endpoints
            if ep.method == method and ep.path.rstrip("/").endswith(suffix)
        ]
        if not loose:
            return None, None, (
                f"Endpoint {method} {path} not found in index. "
                "Try `list_vipmp_endpoints` to see documented endpoints."
            )
        matches = loose

    ep = matches[0]
    schemas_here = [s for s in idx.schemas if s.docs_path == ep.docs_path]

    if not schemas_here:
        return None, ep.docs_path, (
            f"Endpoint {method} {path} is documented at "
            f"{ep.docs_path} but no request schema was extracted from that "
            "page — there may not be a documented request body, or the "
            "docs may use a non-standard structure."
        )

    # Heuristic: if multiple schemas, prefer one whose name doesn't suggest
    # a response / nested type. Otherwise take the first.
    primary = None
    for s in schemas_here:
        lower = s.name.lower()
        if "response" in lower:
            continue
        primary = s
        break
    if primary is None:
        primary = schemas_here[0]

    return primary, ep.docs_path, None


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def validate_body(endpoint: str, body_json: str) -> ValidationResult:
    """
    Validate a JSON body against the documented VIPMP request schema.
    See module docstring for scope and limitations.
    """
    idx = get_active_index()
    if idx is None:
        return ValidationResult(
            endpoint=endpoint,
            schema_name=None,
            docs_path=None,
            issues=[
                ValidationIssue(
                    ISSUE_ERROR,
                    None,
                    "No index available. Call `rebuild_vipmp_index` first.",
                )
            ],
        )

    # Parse body
    try:
        body = json.loads(body_json)
    except json.JSONDecodeError as exc:
        return ValidationResult(
            endpoint=endpoint,
            schema_name=None,
            docs_path=None,
            issues=[
                ValidationIssue(
                    ISSUE_ERROR,
                    None,
                    f"Body is not valid JSON: {exc}",
                )
            ],
        )

    if not isinstance(body, dict):
        return ValidationResult(
            endpoint=endpoint,
            schema_name=None,
            docs_path=None,
            issues=[
                ValidationIssue(
                    ISSUE_ERROR,
                    None,
                    f"Request body must be a JSON object (got {type(body).__name__}).",
                )
            ],
        )

    schema, docs_path, err = resolve_schema(idx, endpoint)
    if err:
        return ValidationResult(
            endpoint=endpoint,
            schema_name=None,
            docs_path=docs_path,
            issues=[ValidationIssue(ISSUE_ERROR, None, err)],
        )

    assert schema is not None  # resolve_schema guarantees this when err is None
    field_map = {f.name: f for f in schema.fields}
    issues: list[ValidationIssue] = []

    # Unknown fields (not in schema)
    for key in body:
        if key not in field_map:
            issues.append(
                ValidationIssue(
                    ISSUE_WARNING,
                    key,
                    f"Unknown field — not documented on `{schema.name}`. "
                    "May be valid but undocumented; check docs.",
                )
            )

    # Required fields missing
    for name, f in field_map.items():
        if f.required and name not in body:
            issues.append(
                ValidationIssue(
                    ISSUE_ERROR,
                    name,
                    f"Required field missing. Type: {f.type}.",
                )
            )

    # Field-level checks
    for name, value in body.items():
        f = field_map.get(name)
        if f is None:
            continue

        # Deprecation warning
        if f.deprecated:
            issues.append(
                ValidationIssue(
                    ISSUE_WARNING,
                    name,
                    f"Field is deprecated in the docs. {f.description[:160]}",
                )
            )

        # Type check
        expected = _normalise_type(f.type)
        actual = _py_type_category(value)
        if actual == "null":
            # Null on a required field is effectively missing.
            if f.required:
                issues.append(
                    ValidationIssue(
                        ISSUE_ERROR,
                        name,
                        f"Required field is null. Type: {f.type}.",
                    )
                )
            continue
        if not _type_compatible(expected, actual):
            issues.append(
                ValidationIssue(
                    ISSUE_ERROR,
                    name,
                    f"Type mismatch: got {actual!r}, expected {expected!r} "
                    f"(docs say: {f.type}).",
                )
            )
            continue

        # Constraint checks
        issues.extend(_check_constraints(f, value))

        # Nested object note — we don't recursively validate yet.
        if actual == "object":
            issues.append(
                ValidationIssue(
                    ISSUE_INFO,
                    name,
                    "Nested object not recursively validated. "
                    "Check the nested resource's own schema with "
                    "`get_vipmp_schema`.",
                )
            )
        elif actual == "array" and value and isinstance(value[0], dict):
            issues.append(
                ValidationIssue(
                    ISSUE_INFO,
                    name,
                    f"Array of {len(value)} object(s) — items not recursively validated.",
                )
            )

    return ValidationResult(
        endpoint=endpoint,
        schema_name=schema.name,
        docs_path=docs_path,
        issues=issues,
    )
