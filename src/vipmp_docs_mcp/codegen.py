"""
Runnable code-snippet emitter for VIPMP endpoints.

Given an endpoint string (and optionally a partial body), produce a
self-contained snippet in one of several languages. The snippet is
scaffolding — consumers still need to fill in auth tokens and a real
request body, but the shape of the call is schema-correct.

Supported languages (lowercase keys, case-insensitive input):
    - "curl"           — POSIX-compatible curl command
    - "powershell"     — Windows PowerShell Invoke-RestMethod
    - "python"         — httpx.Client usage
    - "csharp"         — HttpClient usage with System.Text.Json

When no body is supplied, we build a placeholder body from the schema
(fills required fields with type-appropriate dummy values).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .extractors import SchemaField, SchemaResource
from .index import get_active_index
from .validator import _parse_endpoint, resolve_schema

# Placeholder base URL. Adobe's production IMS-mounted base URL is
# typically provided per-partner; we document this in the snippet rather
# than guessing.
DEFAULT_BASE_URL_PLACEHOLDER = "${VIPMP_BASE_URL}"
DEFAULT_TOKEN_PLACEHOLDER = "${VIPMP_ACCESS_TOKEN}"
DEFAULT_API_KEY_PLACEHOLDER = "${VIPMP_API_KEY}"


SUPPORTED_LANGUAGES = ("curl", "powershell", "python", "csharp")


@dataclass
class CodeSnippet:
    language: str
    code: str
    notes: list[str]  # Informational prose shown alongside the snippet

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "code": self.code,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Placeholder body construction
# ---------------------------------------------------------------------------


def _placeholder_value(field: SchemaField) -> object:
    """Return a schema-appropriate placeholder for a required field with no value supplied."""
    from .validator import _normalise_type

    t = _normalise_type(field.type)
    if t == "string":
        return f"<{field.name}>"
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return False
    if t == "array":
        return []
    if t == "object":
        return {}
    return f"<{field.name}>"


def _build_placeholder_body(schema: SchemaResource) -> dict:
    """
    Construct a starter body from the schema.

    If the schema has any explicitly-required fields, use only those —
    gives the minimum valid shape. If nothing is explicitly required
    (Adobe often marks fields "Optional" but leaves the rest implicit),
    fall back to including every field as a placeholder, so the snippet
    shows the full shape the developer might fill in.

    Read-only fields (typically server-assigned IDs) are always omitted
    from the placeholder body.
    """
    body: dict = {}

    def is_read_only(f: SchemaField) -> bool:
        return "read only" in (f.name or "").lower() or "read only" in (f.type or "").lower()

    required_fields = [f for f in schema.fields if f.required and not is_read_only(f)]
    # Fall back to every non-read-only field when nothing is explicitly required
    # (Adobe's docs often mark fields "Optional" and leave the rest implicit).
    source = required_fields or [f for f in schema.fields if not is_read_only(f)]

    for f in source:
        body[f.name] = _placeholder_value(f)
    return body


# ---------------------------------------------------------------------------
# Per-language emitters
# ---------------------------------------------------------------------------


def _emit_curl(method: str, url: str, body: dict | None) -> str:
    lines = [
        f"curl -X {method} '{url}' \\",
        f"  -H 'Authorization: Bearer {DEFAULT_TOKEN_PLACEHOLDER}' \\",
        f"  -H 'X-Api-Key: {DEFAULT_API_KEY_PLACEHOLDER}' \\",
        "  -H 'Content-Type: application/json'",
    ]
    if body is not None and method in {"POST", "PATCH", "PUT"}:
        body_str = json.dumps(body, indent=2)
        # Heredoc with single-quoted marker passes the body verbatim — no
        # quoting/escaping needed for embedded apostrophes, backticks, or
        # `$` sequences. Beats `-d '...'` which breaks on any single quote
        # in a string value.
        lines[-1] = lines[-1] + " \\"
        lines.append("  --data-binary @- <<'JSON'")
        lines.append(body_str)
        lines.append("JSON")
    return "\n".join(lines)


def _emit_powershell(method: str, url: str, body: dict | None) -> str:
    lines = [
        "$headers = @{",
        f"    'Authorization' = 'Bearer {DEFAULT_TOKEN_PLACEHOLDER}'",
        f"    'X-Api-Key'     = '{DEFAULT_API_KEY_PLACEHOLDER}'",
        "    'Content-Type'  = 'application/json'",
        "}",
        "",
    ]
    if body is not None and method in {"POST", "PATCH", "PUT"}:
        body_str = json.dumps(body, indent=4)
        lines.extend([
            "$body = @'",
            body_str,
            "'@",
            "",
            f"Invoke-RestMethod -Uri '{url}' -Method {method} `",
            "    -Headers $headers -Body $body",
        ])
    else:
        lines.extend([
            f"Invoke-RestMethod -Uri '{url}' -Method {method} -Headers $headers",
        ])
    return "\n".join(lines)


def _emit_python(method: str, url: str, body: dict | None) -> str:
    lines = [
        "import httpx",
        "",
        "headers = {",
        '    "Authorization": f"Bearer {access_token}",   # set access_token above',
        f'    "X-Api-Key":     "{DEFAULT_API_KEY_PLACEHOLDER}",',
        '    "Content-Type":  "application/json",',
        "}",
    ]
    if body is not None and method in {"POST", "PATCH", "PUT"}:
        body_str = json.dumps(body, indent=4)
        lines.append("")
        lines.append(f"body = {body_str}")
        lines.append("")
        lines.append("with httpx.Client(timeout=15.0) as client:")
        lines.append(
            f'    response = client.{method.lower()}("{url}", headers=headers, json=body)'
        )
    else:
        lines.append("")
        lines.append("with httpx.Client(timeout=15.0) as client:")
        lines.append(
            f'    response = client.{method.lower()}("{url}", headers=headers)'
        )
    lines.extend([
        "    response.raise_for_status()",
        "    result = response.json()",
    ])
    return "\n".join(lines)


def _emit_csharp(method: str, url: str, body: dict | None) -> str:
    http_verb = {
        "GET": "Get",
        "POST": "Post",
        "PATCH": "Patch",
        "PUT": "Put",
        "DELETE": "Delete",
    }[method]
    lines = [
        "using System.Net.Http;",
        "using System.Net.Http.Headers;",
        "using System.Net.Http.Json;",
        "",
        "using var client = new HttpClient();",
        "client.DefaultRequestHeaders.Authorization =",
        f'    new AuthenticationHeaderValue("Bearer", "{DEFAULT_TOKEN_PLACEHOLDER}");',
        f'client.DefaultRequestHeaders.Add("X-Api-Key", "{DEFAULT_API_KEY_PLACEHOLDER}");',
        "",
    ]
    if body is not None and method in {"POST", "PATCH", "PUT"}:
        body_str = json.dumps(body, indent=4)
        lines.append("var body = new")
        # crude C# anonymous object from JSON — show as JSON-literal comment
        lines.append("{")
        lines.append("    // replace the following with your typed record or anonymous object")
        lines.append("};")
        lines.append("")
        lines.append(
            f'var response = await client.{http_verb}AsJsonAsync("{url}", body);'
        )
        lines.append("")
        lines.append("// Example body shape (from the VIPMP schema):")
        for line in body_str.splitlines():
            lines.append(f"// {line}")
    else:
        lines.append(f'var response = await client.{http_verb}Async("{url}");')
    lines.extend([
        "",
        "response.EnsureSuccessStatusCode();",
        "var payload = await response.Content.ReadAsStringAsync();",
    ])
    return "\n".join(lines)


_EMITTERS = {
    "curl": _emit_curl,
    "powershell": _emit_powershell,
    "python": _emit_python,
    "csharp": _emit_csharp,
}


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def generate_snippet(
    endpoint: str,
    body_json: str | None = None,
    language: str = "curl",
) -> CodeSnippet | str:
    """
    Build a code snippet for hitting a VIPMP endpoint.

    Returns a CodeSnippet on success, or a plain error string on failure.
    """
    language = language.lower().strip()
    if language not in _EMITTERS:
        return (
            f"Unsupported language {language!r}. "
            f"Supported: {', '.join(SUPPORTED_LANGUAGES)}."
        )

    parsed = _parse_endpoint(endpoint)
    if not parsed:
        return (
            f"Could not parse endpoint {endpoint!r}. Expected "
            "'METHOD /path' (e.g. 'POST /v3/customers')."
        )
    method, path = parsed

    idx = get_active_index()
    if idx is None:
        return "No index available. Call `rebuild_vipmp_index` first."

    schema = None
    docs_path = None
    if method in {"POST", "PATCH", "PUT"}:
        schema, docs_path, _err = resolve_schema(idx, endpoint)

    # Assemble request body
    body: dict | None = None
    notes: list[str] = []

    if method in {"POST", "PATCH", "PUT"}:
        if body_json:
            import json as _json
            try:
                body = _json.loads(body_json)
                notes.append("Used the JSON body you supplied.")
            except _json.JSONDecodeError as exc:
                return f"`body` is not valid JSON: {exc}"
        elif schema is not None:
            body = _build_placeholder_body(schema)
            missing = [f.name for f in schema.fields if f.required]
            notes.append(
                f"Built a placeholder body from the schema — "
                f"{len(missing)} required field(s). Replace `<name>` "
                "placeholders with real values."
            )
        else:
            body = {}
            notes.append(
                "No schema found on the endpoint's docs page — "
                "using an empty body. Fill in manually from the docs."
            )

    url = DEFAULT_BASE_URL_PLACEHOLDER + path
    code = _EMITTERS[language](method, url, body)

    notes.append(
        f"Set `{DEFAULT_BASE_URL_PLACEHOLDER}` to your VIPMP base URL and "
        f"`{DEFAULT_TOKEN_PLACEHOLDER}` / `{DEFAULT_API_KEY_PLACEHOLDER}` to "
        "credentials obtained via Adobe's IMS OAuth flow."
    )
    if docs_path:
        notes.append(f"Reference: {docs_path}")

    return CodeSnippet(language=language, code=code, notes=notes)
