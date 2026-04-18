"""
Structured extractors for Adobe VIP Marketplace docs.

Adobe renders tables as nested `div.table` structures (not real `<table>`
elements): each row is a direct child `div` containing column `div`s.
These extractors target that shape to surface:

  - HTTP endpoints (method + path) from endpoint pages
  - Error codes + reasons from error-codes pages
  - Field schemas (name, type, required, description) from resource pages
  - Code examples (JSON / curl / etc.) from any page

None of these hit the network directly — they take pre-fetched HTML.
The server-side tool wrappers fetch via the disk cache.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from .logging_config import get_logger

log = get_logger("extractors")


# Markers Adobe uses to flag deprecation in prose. Conservative — we only
# match explicit language, not ambiguous phrases like "legacy" or "older".
DEPRECATION_RE = re.compile(
    r"\b(deprecated|will be removed|no longer supported?|sunset|end[- ]of[- ]life)\b",
    re.IGNORECASE,
)


def detect_deprecation(text: str) -> str | None:
    """
    Return a short excerpt of the sentence containing a deprecation marker,
    or None if no marker found. Used to surface *why* something is flagged.
    """
    if not text:
        return None
    match = DEPRECATION_RE.search(text)
    if not match:
        return None
    # Grab the sentence the match lives in.
    start = text.rfind(".", 0, match.start()) + 1
    end = text.find(".", match.end())
    if end == -1:
        end = len(text)
    sentence = text[start:end].strip()
    # Trim runaway sentences.
    if len(sentence) > 240:
        sentence = sentence[:237] + "..."
    return sentence


# ---------------------------------------------------------------------------
# Shared: div.table parser
# ---------------------------------------------------------------------------


def _parse_div_table(table: Tag) -> tuple[list[str], list[list[str]]]:
    """
    Extract (headers, rows) from an Adobe div.table.

    Each row is a direct child `div` of the table; each column is a direct
    child `div` of the row. Text content has <br/> newlines preserved as "\n".
    """
    rows = table.find_all("div", recursive=False)
    if not rows:
        return [], []

    def cells_of(row: Tag) -> list[str]:
        cells = row.find_all("div", recursive=False)
        out: list[str] = []
        for cell in cells:
            # Case 1: real <br/> tags (rare but possible).
            # Use a sentinel so strip=True doesn't discard the bare "\n".
            for br in cell.find_all("br"):
                br.replace_with("\n__VIPMP_BR__\n")
            raw = cell.get_text(separator=" ")
            raw = raw.replace("__VIPMP_BR__", "")
            # Case 2: Adobe encodes "<br />" as literal text ("&lt;br /&gt;")
            # inside cells — typically to break Type/Optional onto two lines.
            # Normalize those to real newlines.
            raw = re.sub(r"\s*<br\s*/?>\s*", "\n", raw)
            # Collapse whitespace within lines but preserve linebreaks.
            lines = [" ".join(line.split()) for line in raw.splitlines()]
            text = "\n".join(line for line in lines if line)
            out.append(text)
        return out

    headers = cells_of(rows[0])
    data_rows = [cells_of(r) for r in rows[1:] if r.find_all("div", recursive=False)]
    return headers, data_rows


def _find_tables(html: str) -> list[tuple[list[str], list[list[str]]]]:
    """Find every div.table on the page and parse each into (headers, rows)."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("div.table")
    return [_parse_div_table(t) for t in tables]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@dataclass
class Endpoint:
    method: str  # GET, POST, PATCH, PUT, DELETE
    path: str  # e.g. "/v3/customers"
    docs_path: str  # e.g. "/vipmp/docs/customer-account/create-customer-account"
    title: str  # human-readable doc title
    deprecated: bool = False
    deprecation_note: str | None = None

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "path": self.path,
            "docs_path": self.docs_path,
            "title": self.title,
            "deprecated": self.deprecated,
            "deprecation_note": self.deprecation_note,
        }


_VERB = re.compile(r"^(GET|POST|PATCH|PUT|DELETE)$", re.IGNORECASE)


def extract_endpoints(html: str, docs_path: str, title: str) -> list[Endpoint]:
    """
    Find endpoint(s) on a single docs page.

    Matches `div.table` with headers containing "Endpoint" and "Method".
    A page may expose multiple endpoints (rare but possible).

    Also scans the full page text for deprecation markers — if the page
    as a whole mentions deprecation, every endpoint on it inherits the
    hint, since Adobe typically deprecates at the endpoint level rather
    than at individual columns of the endpoint table.
    """
    endpoints: list[Endpoint] = []

    # Page-level deprecation scan (cheap — one regex over cleaned page text).
    soup = BeautifulSoup(html, "html.parser")
    for sel in ("nav", "footer", "script", "style", "header"):
        for t in soup.select(sel):
            t.decompose()
    page_text = soup.get_text(separator=" ", strip=True)
    page_deprecation = detect_deprecation(page_text)

    for headers, rows in _find_tables(html):
        header_lower = [h.lower() for h in headers]
        if not ({"endpoint", "method"} <= set(header_lower)):
            continue
        try:
            ep_idx = header_lower.index("endpoint")
            m_idx = header_lower.index("method")
        except ValueError:
            continue
        for row in rows:
            if len(row) <= max(ep_idx, m_idx):
                continue
            method = row[m_idx].strip().upper()
            path = row[ep_idx].strip()
            if not _VERB.match(method) or not path:
                continue
            endpoints.append(
                Endpoint(
                    method=method,
                    path=path,
                    docs_path=docs_path,
                    title=title,
                    deprecated=page_deprecation is not None,
                    deprecation_note=page_deprecation,
                )
            )
    return endpoints


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------


@dataclass
class ErrorCode:
    code: str  # "1117" or "INVALID_LM_MIGRATION_LEVEL"
    reason: str  # short explanation
    endpoint: str | None = None  # "POST /v3/customers" or None
    response: str | None = None  # raw error response text
    docs_path: str | None = None  # where this was documented

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "reason": self.reason,
            "endpoint": self.endpoint,
            "response": self.response,
            "docs_path": self.docs_path,
        }


def extract_error_codes(html: str, docs_path: str | None = None) -> list[ErrorCode]:
    """
    Find error-code tables on a page.

    Recognises both shapes:
      - [Endpoint, Error Code, Error Response, Reason] — numeric codes
      - [REASON_CODE, Description] — symbolic reason codes
    """
    codes: list[ErrorCode] = []
    for headers, rows in _find_tables(html):
        header_lower = [h.lower() for h in headers]

        # Numeric-code layout
        if {"error code", "reason"} <= set(header_lower):
            try:
                code_idx = header_lower.index("error code")
                reason_idx = header_lower.index("reason")
            except ValueError:
                continue
            ep_idx = header_lower.index("endpoint") if "endpoint" in header_lower else None
            resp_idx = (
                header_lower.index("error response")
                if "error response" in header_lower
                else None
            )
            for row in rows:
                if len(row) <= max(
                    code_idx,
                    reason_idx,
                    ep_idx if ep_idx is not None else 0,
                    resp_idx if resp_idx is not None else 0,
                ):
                    continue
                codes.append(
                    ErrorCode(
                        code=row[code_idx].strip(),
                        reason=row[reason_idx].strip(),
                        endpoint=row[ep_idx].strip() if ep_idx is not None else None,
                        response=row[resp_idx].strip() if resp_idx is not None else None,
                        docs_path=docs_path,
                    )
                )
            continue

        # Symbolic reason-code layout
        if "reason_code" in header_lower or "reasoncode" in header_lower:
            try:
                code_idx = next(
                    i for i, h in enumerate(header_lower) if "reason" in h and "code" in h
                )
                desc_idx = next(
                    (i for i, h in enumerate(header_lower) if "description" in h),
                    code_idx + 1,
                )
            except StopIteration:
                continue
            for row in rows:
                if len(row) <= max(code_idx, desc_idx):
                    continue
                codes.append(
                    ErrorCode(
                        code=row[code_idx].strip(),
                        reason=row[desc_idx].strip() if desc_idx < len(row) else "",
                        docs_path=docs_path,
                    )
                )
    return codes


# ---------------------------------------------------------------------------
# Field schemas
# ---------------------------------------------------------------------------


@dataclass
class SchemaField:
    name: str
    type: str  # "String", "Date", "String (Enum)", etc.
    required: bool | None  # True/False/None if unspecified
    description: str
    constraints: str | None = None  # "Max: 35 characters"
    deprecated: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
            "constraints": self.constraints,
            "deprecated": self.deprecated,
        }


@dataclass
class SchemaResource:
    name: str  # "Customer", "linkedMembership"
    level: int  # heading level — 2 for top-level, 3 for nested
    fields: list[SchemaField]
    docs_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "level": self.level,
            "fields": [f.to_dict() for f in self.fields],
            "docs_path": self.docs_path,
        }


def _parse_type_cell(text: str) -> tuple[str, bool | None]:
    """
    Split the Type column into (type_name, required).

    Adobe embeds "Optional" / "(read only)" on a second line inside the cell.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "", None
    type_name = lines[0]
    required: bool | None = None
    for extra in lines[1:]:
        lower = extra.lower()
        if "optional" in lower:
            required = False
        elif "required" in lower:
            required = True
        # "read only" / annotations don't change required-ness
    return type_name, required


def extract_schemas(html: str, docs_path: str | None = None) -> list[SchemaResource]:
    """
    Extract field-schema tables. Each `<h2>` or `<h3>` immediately followed
    by a `div.table` with columns [Property, Type, Description, Range/Limits]
    becomes a SchemaResource.
    """
    soup = BeautifulSoup(html, "html.parser")
    resources: list[SchemaResource] = []

    # Iterate all h2/h3 elements; for each, check if the next significant
    # sibling is a div.table with the schema column layout.
    for heading in soup.find_all(["h2", "h3"]):
        sibling = heading.find_next_sibling()
        # Skip whitespace-only siblings.
        while sibling and isinstance(sibling, str) and not sibling.strip():
            sibling = sibling.find_next_sibling()
        if not isinstance(sibling, Tag):
            continue
        if sibling.name != "div" or "table" not in (sibling.get("class") or []):
            continue
        headers, rows = _parse_div_table(sibling)
        header_lower = [h.lower() for h in headers]
        if "property" not in header_lower or "type" not in header_lower:
            continue

        prop_idx = header_lower.index("property")
        type_idx = header_lower.index("type")
        desc_idx = header_lower.index("description") if "description" in header_lower else None
        limits_idx = next(
            (i for i, h in enumerate(header_lower) if "range" in h or "limit" in h), None
        )

        fields: list[SchemaField] = []
        for row in rows:
            if len(row) <= max(prop_idx, type_idx):
                continue
            name = row[prop_idx].strip()
            type_name, required = _parse_type_cell(row[type_idx])
            desc = row[desc_idx].strip() if desc_idx is not None and desc_idx < len(row) else ""
            constraints = (
                row[limits_idx].strip()
                if limits_idx is not None and limits_idx < len(row)
                else None
            )
            if not name:
                continue
            fields.append(
                SchemaField(
                    name=name,
                    type=type_name,
                    required=required,
                    description=desc,
                    constraints=constraints or None,
                    deprecated=detect_deprecation(desc) is not None,
                )
            )

        if fields:
            level = int(heading.name[1])
            resources.append(
                SchemaResource(
                    name=heading.get_text(strip=True),
                    level=level,
                    fields=fields,
                    docs_path=docs_path,
                )
            )
    return resources


# ---------------------------------------------------------------------------
# Code examples
# ---------------------------------------------------------------------------


@dataclass
class CodeExample:
    language: str | None  # "json", "python", "bash", etc.
    code: str
    nearby_heading: str | None = None  # nearest preceding heading, if any

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "code": self.code,
            "nearby_heading": self.nearby_heading,
        }


_LANG_RE = re.compile(r"language-([\w+-]+)")


# ---------------------------------------------------------------------------
# Validation rules (field name -> regex)
# ---------------------------------------------------------------------------


@dataclass
class ValidationRule:
    """A single field validation rule from Adobe's regex reference page."""

    field_name: str  # e.g. "companyName", "firstName"
    resource: str  # e.g. "CompanyProfile", "Contact"
    pattern: str  # Java-style regex, e.g. "^[\\\\p{L}\\\\p{N} ]{1,80}$"
    notes: str | None = None

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "resource": self.resource,
            "pattern": self.pattern,
            "notes": self.notes,
        }


def extract_validations(html: str, docs_path: str | None = None) -> list[ValidationRule]:
    """
    Extract validation regexes from Adobe's `references/validations` page.

    The page structure is a single 4-column `div.table`:
        Field Name | Resource/Object | Regular Expression (Java String) | Notes

    Adobe publishes Java-style regexes; we store them verbatim. Translation
    to Python's `re` syntax (or use of a Java-compatible regex library
    like `regex`) happens at validation time.
    """
    rules: list[ValidationRule] = []
    for headers, rows in _find_tables(html):
        header_lower = [h.lower() for h in headers]
        # Match by content, not exact header strings — Adobe might tweak labels.
        if not any("field name" in h for h in header_lower):
            continue
        if not any("regular expression" in h or "regex" in h for h in header_lower):
            continue
        try:
            field_idx = next(
                i for i, h in enumerate(header_lower) if "field name" in h
            )
            resource_idx = next(
                i for i, h in enumerate(header_lower) if "resource" in h or "object" in h
            )
            regex_idx = next(
                i for i, h in enumerate(header_lower)
                if "regular expression" in h or "regex" in h
            )
        except StopIteration:
            continue
        notes_idx = next(
            (i for i, h in enumerate(header_lower) if "note" in h), None
        )

        for row in rows:
            if len(row) <= max(field_idx, resource_idx, regex_idx):
                continue
            field_name = row[field_idx].strip()
            resource = row[resource_idx].strip()
            pattern = row[regex_idx].strip()
            notes = (
                row[notes_idx].strip()
                if notes_idx is not None and notes_idx < len(row)
                else None
            )
            if not field_name or not pattern:
                continue
            rules.append(
                ValidationRule(
                    field_name=field_name,
                    resource=resource,
                    pattern=pattern,
                    notes=notes or None,
                )
            )

    log.info("extracted %d validation rules from %s", len(rules), docs_path or "page")
    return rules


def extract_code_examples(html: str, language: str | None = None) -> list[CodeExample]:
    """
    Return every `<pre><code>` block. If `language` is set, filter to only
    blocks where the code element has `class="language-<language>"`.

    The `nearby_heading` is the text of the nearest preceding h1/h2/h3,
    useful for labeling (e.g. "Request Body", "Response", "Example").
    """
    soup = BeautifulSoup(html, "html.parser")
    examples: list[CodeExample] = []
    for code in soup.select("pre > code"):
        # Language detection
        lang: str | None = None
        for cls in code.get("class") or []:
            match = _LANG_RE.match(cls)
            if match:
                lang = match.group(1).lower()
                break
        if language and (lang or "").lower() != language.lower():
            continue

        # Find nearest preceding heading
        heading_text: str | None = None
        for prev in code.find_all_previous(["h1", "h2", "h3"]):
            heading_text = prev.get_text(strip=True)
            break

        text = code.get_text()
        if text.strip():
            examples.append(
                CodeExample(language=lang, code=text, nearby_heading=heading_text)
            )
    return examples
