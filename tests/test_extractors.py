"""Tests for the HTML extractors — the highest-risk component (depends on Adobe's DOM shape)."""

from __future__ import annotations

from vipmp_docs_mcp.extractors import (
    extract_code_examples,
    extract_endpoints,
    extract_error_codes,
    extract_schemas,
)


class TestExtractEndpoints:
    def test_finds_post_customers(self, endpoint_html: str):
        eps = extract_endpoints(endpoint_html, "/vipmp/docs/create", "Create Customer")
        assert len(eps) == 1
        assert eps[0].method == "POST"
        assert eps[0].path == "/v3/customers"
        assert eps[0].docs_path == "/vipmp/docs/create"
        assert eps[0].title == "Create Customer"

    def test_no_endpoint_table_returns_empty(self, flat_page_html: str):
        eps = extract_endpoints(flat_page_html, "/vipmp/docs/flat", "Flat Page")
        assert eps == []


class TestExtractErrorCodes:
    def test_numeric_codes(self, error_codes_html: str):
        codes = extract_error_codes(error_codes_html, docs_path="/vipmp/docs/lga/error-codes")
        numeric = [c for c in codes if c.code.isdigit()]
        assert len(numeric) == 2
        assert {c.code for c in numeric} == {"1117", "1118"}

    def test_endpoint_attribution(self, error_codes_html: str):
        codes = extract_error_codes(error_codes_html, docs_path="/x")
        code_1117 = next(c for c in codes if c.code == "1117")
        assert code_1117.endpoint == "POST /v3/customers"

    def test_reason_captured(self, error_codes_html: str):
        codes = extract_error_codes(error_codes_html)
        code_1117 = next(c for c in codes if c.code == "1117")
        assert "Coterm" in code_1117.reason

    def test_symbolic_codes(self, error_codes_html: str):
        codes = extract_error_codes(error_codes_html)
        symbolic = [c for c in codes if not c.code.isdigit()]
        assert any(c.code == "INVALID_LM_MIGRATION_LEVEL" for c in symbolic)

    def test_no_table_returns_empty(self, flat_page_html: str):
        assert extract_error_codes(flat_page_html) == []


class TestExtractSchemas:
    def test_finds_customer_resource(self, resources_html: str):
        schemas = extract_schemas(resources_html, docs_path="/vipmp/docs/refs")
        customer = next(s for s in schemas if "Customer" in s.name)
        assert len(customer.fields) == 2
        names = [f.name for f in customer.fields]
        assert "externalReferenceId" in names
        assert "customerId" in names

    def test_optional_marker_parses_to_required_false(self, resources_html: str):
        schemas = extract_schemas(resources_html)
        customer = next(s for s in schemas if "Customer" in s.name)
        ext_ref = next(f for f in customer.fields if f.name == "externalReferenceId")
        assert ext_ref.required is False
        assert ext_ref.type == "String"

    def test_read_only_annotation_preserved_in_type(self, resources_html: str):
        # `(read only)` is an annotation — doesn't change required-ness but
        # should appear somewhere so callers can flag it.
        schemas = extract_schemas(resources_html)
        customer = next(s for s in schemas if "Customer" in s.name)
        customer_id = next(f for f in customer.fields if f.name == "customerId")
        assert customer_id.required is None  # neither explicitly required nor optional
        # The (read only) marker was on line 2 of the Type cell.

    def test_nested_resource_captured(self, resources_html: str):
        schemas = extract_schemas(resources_html)
        nested = next(s for s in schemas if "linkedMembership" in s.name)
        assert nested.level == 3
        assert len(nested.fields) == 1

    def test_constraints_captured(self, resources_html: str):
        schemas = extract_schemas(resources_html)
        customer = next(s for s in schemas if "Customer" in s.name)
        ext_ref = next(f for f in customer.fields if f.name == "externalReferenceId")
        assert ext_ref.constraints == "Max: 35 characters"


class TestExtractCodeExamples:
    def test_finds_json_blocks(self, endpoint_html: str):
        examples = extract_code_examples(endpoint_html)
        assert len(examples) == 2
        assert all(ex.language == "json" for ex in examples)

    def test_language_filter(self, endpoint_html: str):
        examples = extract_code_examples(endpoint_html, language="json")
        assert len(examples) == 2
        assert extract_code_examples(endpoint_html, language="python") == []

    def test_nearby_heading(self, endpoint_html: str):
        examples = extract_code_examples(endpoint_html)
        headings = [ex.nearby_heading for ex in examples]
        assert "Request Body" in headings
        assert "Response body" in headings
