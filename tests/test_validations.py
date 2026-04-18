"""Tests for validation-rule extraction + regex enforcement in the validator."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from vipmp_docs_mcp.extractors import (
    Endpoint,
    SchemaField,
    SchemaResource,
    ValidationRule,
    extract_validations,
)
from vipmp_docs_mcp.index import IndexSnapshot
from vipmp_docs_mcp.validator import (
    _to_python_pattern,
    _unescape_java_source,
    validate_body,
)

# ---------------------------------------------------------------------------
# extract_validations
# ---------------------------------------------------------------------------


VALIDATIONS_HTML = """
<html><body><main>
<h1>Validations and regular expressions</h1>
<div class="table">
  <div>
    <div>Field Name</div>
    <div>Resource/Object</div>
    <div>Regular Expression (Java String)</div>
    <div>Notes</div>
  </div>
  <div>
    <div>companyName</div>
    <div>CompanyProfile</div>
    <div>^[a-zA-Z]{4,80}$</div>
    <div>Letters only</div>
  </div>
  <div>
    <div>firstName</div>
    <div>Contact</div>
    <div>^[a-zA-Z]{1,35}$</div>
    <div></div>
  </div>
</div>
<p>vipmp marker</p>
</main></body></html>
"""


class TestExtractValidations:
    def test_extracts_rules(self):
        rules = extract_validations(VALIDATIONS_HTML, docs_path="/x")
        assert len(rules) == 2
        names = {r.field_name for r in rules}
        assert names == {"companyName", "firstName"}

    def test_resource_captured(self):
        rules = extract_validations(VALIDATIONS_HTML)
        company = next(r for r in rules if r.field_name == "companyName")
        assert company.resource == "CompanyProfile"

    def test_pattern_captured(self):
        rules = extract_validations(VALIDATIONS_HTML)
        company = next(r for r in rules if r.field_name == "companyName")
        assert company.pattern == "^[a-zA-Z]{4,80}$"

    def test_notes_optional(self):
        rules = extract_validations(VALIDATIONS_HTML)
        first_name = next(r for r in rules if r.field_name == "firstName")
        # Empty notes cell should produce None, not empty string.
        assert first_name.notes is None

    def test_no_validations_table_returns_empty(self):
        assert extract_validations(
            "<html><body><main>vipmp marker — no tables</main></body></html>"
        ) == []


# ---------------------------------------------------------------------------
# Java-source unescaping
# ---------------------------------------------------------------------------


class TestUnescapeJavaSource:
    def test_doubles_collapsed(self):
        # Adobe ships strings like "\\\\p{L}" (4 backslashes in Python source =
        # 2 actual backslashes) which should become "\\p{L}" (1 backslash).
        # Using `r"..."` here so the test is readable.
        adobe_form = r"^[\\p{L}\\p{N}]{1,80}$"
        assert _unescape_java_source(adobe_form) == r"^[\p{L}\p{N}]{1,80}$"

    def test_no_doubles_passthrough(self):
        py_form = r"^[a-z]{1,5}$"
        assert _unescape_java_source(py_form) == py_form

    def test_quoted_chars_unescaped(self):
        adobe_form = r'^[a-z\\"]+$'
        assert _unescape_java_source(adobe_form) == r'^[a-z\"]+$'


class TestToPythonPattern:
    def test_unescapes_then_returns(self):
        adobe_form = r"^[\\p{L}]{1,80}$"
        out = _to_python_pattern(adobe_form)
        # Must NOT contain the Java-doubled form anymore.
        assert "\\\\p" not in out
        assert "\\p{L}" in out


# ---------------------------------------------------------------------------
# End-to-end: regex enforcement via validate_body
# ---------------------------------------------------------------------------


@pytest.fixture
def index_with_validations() -> IndexSnapshot:
    return IndexSnapshot(
        endpoints=[
            Endpoint(
                method="POST",
                path="/v3/customers",
                docs_path="/vipmp/docs/customer-account/create-customer-account",
                title="Create customer account",
            )
        ],
        schemas=[
            SchemaResource(
                name="Customer",
                level=3,
                docs_path="/vipmp/docs/customer-account/create-customer-account",
                fields=[
                    SchemaField(name="resellerId", type="String", required=True, description=""),
                    # firstName is NOT in the schema — it's on Contact, a nested
                    # resource. The validator should still apply the firstName
                    # regex rule as a cross-cutting check.
                ],
            )
        ],
        validations=[
            ValidationRule(
                field_name="firstName",
                resource="Contact",
                pattern=r"^[\\p{L}\\p{N} ]{1,35}$",  # Java-source style — doubled backslashes
                notes="Letters and digits only",
            )
        ],
    )


@pytest.fixture
def patched(index_with_validations):
    with patch(
        "vipmp_docs_mcp.validator.get_active_index",
        return_value=index_with_validations,
    ):
        yield index_with_validations


class TestRegexEnforcement:
    def test_valid_value_passes(self, patched):
        body = json.dumps({"resellerId": "R1", "firstName": "Alice"})
        r = validate_body("POST /v3/customers", body)
        regex_issues = [i for i in r.issues if "regex" in i.message.lower()]
        assert regex_issues == []

    def test_unicode_letters_accepted(self, patched):
        body = json.dumps({"resellerId": "R1", "firstName": "María"})
        r = validate_body("POST /v3/customers", body)
        regex_issues = [i for i in r.issues if "adobe" in i.message.lower()]
        assert regex_issues == []

    def test_disallowed_char_flagged(self, patched):
        body = json.dumps({"resellerId": "R1", "firstName": "Bob$"})
        r = validate_body("POST /v3/customers", body)
        regex_issues = [i for i in r.issues if "adobe" in i.message.lower()]
        assert len(regex_issues) == 1
        assert regex_issues[0].field == "firstName"

    def test_too_long_flagged(self, patched):
        body = json.dumps({"resellerId": "R1", "firstName": "a" * 100})
        r = validate_body("POST /v3/customers", body)
        regex_issues = [i for i in r.issues if "adobe" in i.message.lower()]
        assert len(regex_issues) == 1

    def test_field_not_in_active_schema_still_validated(self, patched):
        # firstName isn't on the Customer schema; the regex check should
        # still fire because it's a cross-cutting Adobe-published rule.
        body = json.dumps({"resellerId": "R1", "firstName": "x" * 200})
        r = validate_body("POST /v3/customers", body)
        regex_issues = [i for i in r.issues if "adobe" in i.message.lower()]
        assert regex_issues  # Should fire even though firstName isn't in field_map

    def test_no_rule_no_check(self, patched):
        body = json.dumps({"resellerId": "R1", "unrelatedField": "any value"})
        r = validate_body("POST /v3/customers", body)
        regex_issues = [i for i in r.issues if "adobe" in i.message.lower()]
        assert regex_issues == []

    def test_non_string_skipped(self, patched):
        # firstName as an integer — type check should fail elsewhere; the
        # regex check should silently skip non-string values.
        body = json.dumps({"resellerId": "R1", "firstName": 12345})
        r = validate_body("POST /v3/customers", body)
        regex_issues = [i for i in r.issues if "adobe" in i.message.lower()]
        assert regex_issues == []
