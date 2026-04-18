"""Tests for the code snippet generator."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from vipmp_docs_mcp.codegen import (
    SUPPORTED_LANGUAGES,
    CodeSnippet,
    generate_snippet,
)
from vipmp_docs_mcp.extractors import Endpoint, SchemaField, SchemaResource
from vipmp_docs_mcp.index import IndexSnapshot


@pytest.fixture
def synthetic_index() -> IndexSnapshot:
    return IndexSnapshot(
        endpoints=[
            Endpoint(
                method="POST",
                path="/v3/customers",
                docs_path="/vipmp/docs/customer-account/create-customer-account",
                title="Create customer account",
            ),
            Endpoint(
                method="GET",
                path="/v3/customers/{id}",
                docs_path="/vipmp/docs/customer-account/get-customer-account",
                title="Get customer account",
            ),
        ],
        schemas=[
            SchemaResource(
                name="Customer",
                level=3,
                docs_path="/vipmp/docs/customer-account/create-customer-account",
                fields=[
                    SchemaField(name="resellerId", type="String", required=True, description=""),
                    SchemaField(name="externalReferenceId", type="String", required=False, description=""),
                ],
            )
        ],
    )


@pytest.fixture
def patched_index(synthetic_index):
    with (
        patch("vipmp_docs_mcp.codegen.get_active_index", return_value=synthetic_index),
        patch("vipmp_docs_mcp.validator.get_active_index", return_value=synthetic_index),
    ):
        yield synthetic_index


class TestGenerateSnippet:
    def test_unsupported_language(self, patched_index):
        result = generate_snippet("POST /v3/customers", language="ruby")
        assert isinstance(result, str)
        assert "Unsupported language" in result

    def test_malformed_endpoint(self, patched_index):
        result = generate_snippet("not an endpoint", language="curl")
        assert isinstance(result, str)
        assert "parse" in result.lower()

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_all_languages_emit_for_post(self, patched_index, lang):
        result = generate_snippet("POST /v3/customers", language=lang)
        assert isinstance(result, CodeSnippet)
        assert result.language == lang
        assert result.code
        assert "/v3/customers" in result.code
        assert result.notes

    def test_get_endpoint_omits_body(self, patched_index):
        result = generate_snippet("GET /v3/customers/{id}", language="python")
        assert isinstance(result, CodeSnippet)
        assert "body" not in result.code.lower() or "body" not in result.code
        assert "client.get(" in result.code

    def test_placeholder_body_uses_required_fields(self, patched_index):
        result = generate_snippet("POST /v3/customers", language="python")
        assert isinstance(result, CodeSnippet)
        # resellerId is required → should appear in the placeholder body.
        assert "resellerId" in result.code

    def test_user_body_is_used_verbatim(self, patched_index):
        custom_body = '{"customField": "customValue"}'
        result = generate_snippet(
            "POST /v3/customers", body_json=custom_body, language="python"
        )
        assert isinstance(result, CodeSnippet)
        assert "customField" in result.code
        assert "customValue" in result.code

    def test_malformed_user_body_errors(self, patched_index):
        result = generate_snippet(
            "POST /v3/customers", body_json="{not json}", language="python"
        )
        assert isinstance(result, str)
        assert "not valid JSON" in result

    def test_curl_includes_method_and_headers(self, patched_index):
        result = generate_snippet("POST /v3/customers", language="curl")
        assert isinstance(result, CodeSnippet)
        assert "curl -X POST" in result.code
        assert "Authorization: Bearer" in result.code
        assert "X-Api-Key" in result.code
        assert "Content-Type: application/json" in result.code

    def test_powershell_includes_invoke(self, patched_index):
        result = generate_snippet("POST /v3/customers", language="powershell")
        assert isinstance(result, CodeSnippet)
        assert "Invoke-RestMethod" in result.code
        assert "-Method POST" in result.code

    def test_csharp_uses_correct_verb(self, patched_index):
        result = generate_snippet("POST /v3/customers", language="csharp")
        assert isinstance(result, CodeSnippet)
        assert "PostAsJsonAsync" in result.code

    def test_notes_reference_docs_path(self, patched_index):
        result = generate_snippet("POST /v3/customers", language="curl")
        assert isinstance(result, CodeSnippet)
        note_text = " ".join(result.notes)
        assert "customer-account" in note_text
