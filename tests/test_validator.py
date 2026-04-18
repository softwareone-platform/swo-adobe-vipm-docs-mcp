"""
Tests for the validator. Builds a synthetic IndexSnapshot so we don't
depend on live Adobe data.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from vipmp_docs_mcp.extractors import Endpoint, SchemaField, SchemaResource
from vipmp_docs_mcp.index import IndexSnapshot
from vipmp_docs_mcp.validator import (
    ISSUE_ERROR,
    ISSUE_INFO,
    ISSUE_WARNING,
    _normalise_type,
    _py_type_category,
    _type_compatible,
    resolve_schema,
    validate_body,
)


# ---------------------------------------------------------------------------
# Fixture: a synthetic index with one endpoint + request schema
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_index() -> IndexSnapshot:
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
                name="Customer (top-level resource)",
                level=3,
                docs_path="/vipmp/docs/customer-account/create-customer-account",
                fields=[
                    SchemaField(
                        name="externalReferenceId",
                        type="String",
                        required=False,
                        description="Your own ID for the customer.",
                        constraints="Max: 35 characters",
                    ),
                    SchemaField(
                        name="resellerId",
                        type="String",
                        required=True,
                        description="Reseller ID.",
                    ),
                    SchemaField(
                        name="orderCount",
                        type="Integer",
                        required=False,
                        description="How many orders this customer has placed.",
                        constraints="Max: 1000",
                    ),
                    SchemaField(
                        name="companyProfile",
                        type="CompanyProfile resource",
                        required=True,
                        description="Company profile object.",
                    ),
                    SchemaField(
                        name="legacyField",
                        type="String",
                        required=False,
                        description="Deprecated. Use newField instead.",
                        deprecated=True,
                    ),
                ],
            )
        ],
    )


@pytest.fixture
def patched_index(synthetic_index):
    """Patch get_active_index to return our synthetic index."""
    with patch("vipmp_docs_mcp.validator.get_active_index", return_value=synthetic_index):
        yield synthetic_index


# ---------------------------------------------------------------------------
# Type normalisation
# ---------------------------------------------------------------------------


class TestNormaliseType:
    def test_basic_types(self):
        assert _normalise_type("String") == "string"
        assert _normalise_type("Integer") == "integer"
        assert _normalise_type("Number") == "number"
        assert _normalise_type("Boolean") == "boolean"

    def test_parenthetical_modifiers_stripped(self):
        assert _normalise_type("String (Enum)") == "string"
        assert _normalise_type("String (datetime)") == "string"

    def test_array_and_object(self):
        assert _normalise_type("Array of Contact resources") == "array"
        assert _normalise_type("CompanyProfile resource") == "object"
        assert _normalise_type("Object") == "object"

    def test_unknown(self):
        assert _normalise_type("Frobble") == "unknown"


class TestPyTypeCategory:
    def test_basic(self):
        assert _py_type_category("x") == "string"
        assert _py_type_category(5) == "integer"
        assert _py_type_category(5.0) == "number"
        assert _py_type_category(True) == "boolean"  # not "integer"
        assert _py_type_category([]) == "array"
        assert _py_type_category({}) == "object"
        assert _py_type_category(None) == "null"


class TestTypeCompatible:
    def test_identity(self):
        assert _type_compatible("string", "string")

    def test_unknown_expected_passes(self):
        assert _type_compatible("unknown", "string")
        assert _type_compatible("unknown", "array")

    def test_integer_and_number_interchangeable(self):
        assert _type_compatible("number", "integer")
        assert _type_compatible("integer", "number")

    def test_mismatch(self):
        assert not _type_compatible("string", "integer")
        assert not _type_compatible("boolean", "string")


# ---------------------------------------------------------------------------
# Schema resolution
# ---------------------------------------------------------------------------


class TestResolveSchema:
    def test_found(self, synthetic_index):
        schema, docs_path, err = resolve_schema(synthetic_index, "POST /v3/customers")
        assert err is None
        assert schema is not None
        assert "Customer" in schema.name
        assert docs_path == "/vipmp/docs/customer-account/create-customer-account"

    def test_unknown_endpoint(self, synthetic_index):
        schema, docs_path, err = resolve_schema(synthetic_index, "GET /v3/nowhere")
        assert schema is None
        assert err is not None
        assert "not found" in err.lower()

    def test_malformed_endpoint(self, synthetic_index):
        schema, _, err = resolve_schema(synthetic_index, "not a proper endpoint")
        assert schema is None
        assert err is not None
        assert "parse" in err.lower()


# ---------------------------------------------------------------------------
# End-to-end validation
# ---------------------------------------------------------------------------


class TestValidateBody:
    def test_missing_required_field(self, patched_index):
        body = json.dumps({"externalReferenceId": "ABC"})  # missing resellerId + companyProfile
        r = validate_body("POST /v3/customers", body)
        assert not r.ok
        missing = [i for i in r.issues if i.level == ISSUE_ERROR and "missing" in i.message.lower()]
        fields_flagged = {i.field for i in missing}
        assert "resellerId" in fields_flagged
        assert "companyProfile" in fields_flagged

    def test_unknown_field_warns(self, patched_index):
        body = json.dumps({
            "resellerId": "R1",
            "companyProfile": {},
            "extraBogusField": "oops",
        })
        r = validate_body("POST /v3/customers", body)
        unknown = [i for i in r.issues if i.field == "extraBogusField"]
        assert unknown
        assert unknown[0].level == ISSUE_WARNING

    def test_string_too_long(self, patched_index):
        body = json.dumps({
            "resellerId": "R1",
            "companyProfile": {},
            "externalReferenceId": "x" * 100,
        })
        r = validate_body("POST /v3/customers", body)
        constraint_errors = [
            i for i in r.issues
            if i.level == ISSUE_ERROR and "too long" in i.message
        ]
        assert constraint_errors
        assert constraint_errors[0].field == "externalReferenceId"

    def test_numeric_max_exceeded(self, patched_index):
        body = json.dumps({
            "resellerId": "R1",
            "companyProfile": {},
            "orderCount": 9999,
        })
        r = validate_body("POST /v3/customers", body)
        num_errors = [
            i for i in r.issues
            if i.level == ISSUE_ERROR and "exceeds max" in i.message
        ]
        assert num_errors
        assert num_errors[0].field == "orderCount"

    def test_type_mismatch(self, patched_index):
        body = json.dumps({
            "resellerId": 12345,  # should be String
            "companyProfile": {},
        })
        r = validate_body("POST /v3/customers", body)
        type_errors = [
            i for i in r.issues
            if i.level == ISSUE_ERROR and "type mismatch" in i.message.lower()
        ]
        assert type_errors
        assert type_errors[0].field == "resellerId"

    def test_deprecated_field_warns(self, patched_index):
        body = json.dumps({
            "resellerId": "R1",
            "companyProfile": {},
            "legacyField": "still using it",
        })
        r = validate_body("POST /v3/customers", body)
        depr = [
            i for i in r.issues
            if i.level == ISSUE_WARNING and "deprecated" in i.message.lower()
        ]
        assert depr
        assert depr[0].field == "legacyField"

    def test_nested_object_info_note(self, patched_index):
        body = json.dumps({
            "resellerId": "R1",
            "companyProfile": {"name": "Acme"},
        })
        r = validate_body("POST /v3/customers", body)
        info_notes = [
            i for i in r.issues
            if i.level == ISSUE_INFO and "not recursively validated" in i.message
        ]
        assert info_notes

    def test_malformed_json(self, patched_index):
        r = validate_body("POST /v3/customers", "not valid json")
        assert not r.ok
        assert any("not valid JSON" in i.message for i in r.issues)

    def test_body_not_an_object(self, patched_index):
        r = validate_body("POST /v3/customers", "[1, 2, 3]")
        assert not r.ok
        assert any("must be a JSON object" in i.message for i in r.issues)

    def test_valid_body(self, patched_index):
        body = json.dumps({
            "resellerId": "R1",
            "companyProfile": {},
        })
        r = validate_body("POST /v3/customers", body)
        # companyProfile triggers an INFO note about nested, but no errors or warnings
        assert r.ok
        assert r.error_count == 0
        # Warning count includes only the warnings, not info notes
        assert r.warning_count == 0
