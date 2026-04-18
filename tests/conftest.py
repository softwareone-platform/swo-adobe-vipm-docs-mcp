"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_cache_path(tmp_path: Path) -> Path:
    """A temporary cache.json path — tests that exercise DocsCache use this."""
    return tmp_path / "cache.json"


@pytest.fixture
def endpoint_html() -> str:
    """Minimal synthetic HTML matching Adobe's endpoint-page shape."""
    return """
<html><body>
<main>
<h1>Create Customer Account</h1>
<p>Top-level description of the endpoint.</p>

<div class="table">
  <div>
    <div data-align="left">Endpoint</div>
    <div data-align="left">Method</div>
  </div>
  <div>
    <div data-align="left">/v3/customers</div>
    <div data-align="left">POST</div>
  </div>
</div>

<h2>Request Body</h2>
<pre><code class="language-json">{
  "resellerId": "5556667778",
  "externalReferenceId": "342"
}</code></pre>

<h2>Response body</h2>
<pre><code class="language-json">{
  "customerId": "1234567890"
}</code></pre>

<p>Tag marker: vipmp</p>
</main>
</body></html>
"""


@pytest.fixture
def error_codes_html() -> str:
    """Minimal synthetic HTML matching Adobe's error-codes-page shape."""
    return """
<html><body>
<main>
<h1>LGA Error Codes</h1>

<div class="table">
  <div>
    <div data-align="left">Endpoint</div>
    <div>Error Code</div>
    <div>Error Response</div>
    <div>Reason</div>
  </div>
  <div>
    <div data-align="left">POST /v3/customers</div>
    <div>1117</div>
    <div>400 BAD REQUEST&lt;br /&gt;Some fields invalid</div>
    <div>Coterm date exceeds 23 months for LGA customer.</div>
  </div>
  <div>
    <div data-align="left">GET /v3/linked_membership_groups</div>
    <div>1118</div>
    <div>400 BAD REQUEST</div>
    <div>When the country is invalid.</div>
  </div>
</div>

<h2 id="ineligible">Reason Codes</h2>
<div class="table">
  <div>
    <div>REASON_CODE</div>
    <div>Description</div>
  </div>
  <div>
    <div>INVALID_LM_MIGRATION_LEVEL</div>
    <div>Migration level is not LM.</div>
  </div>
</div>

<p>vipmp marker</p>
</main>
</body></html>
"""


@pytest.fixture
def resources_html() -> str:
    """Minimal synthetic HTML matching Adobe's resources-page shape."""
    return """
<html><body>
<main>
<h1>Resources and Fields</h1>

<h2 id="customer">Customer (top-level resource)</h2>
<div class="table">
  <div>
    <div data-align="left">Property</div>
    <div data-align="left">Type</div>
    <div data-align="left">Description</div>
    <div data-align="left">Range/Limits</div>
  </div>
  <div>
    <div data-align="left">externalReferenceId</div>
    <div data-align="left">String&lt;br /&gt;Optional</div>
    <div data-align="left">Your own ID for the customer.</div>
    <div data-align="left">Max: 35 characters</div>
  </div>
  <div>
    <div data-align="left">customerId</div>
    <div data-align="left">String&lt;br /&gt;(read only)</div>
    <div data-align="left">Adobe-assigned ID.</div>
    <div data-align="left"></div>
  </div>
</div>

<h3 id="linkedmembership">linkedMembership</h3>
<div class="table">
  <div>
    <div data-align="left">Property</div>
    <div data-align="left">Type</div>
    <div data-align="left">Description</div>
  </div>
  <div>
    <div data-align="left">id</div>
    <div data-align="left">String</div>
    <div data-align="left">Linked membership group ID.</div>
  </div>
</div>

<p>vipmp marker</p>
</main>
</body></html>
"""


@pytest.fixture
def flat_page_html() -> str:
    """HTML for a flat Adobe-style page: one h1 and a big body with paragraphs."""
    return """
<html><body>
<main>
<h1>Identity management and authentication</h1>
<p>The Commerce Partner APIs use Adobe's standard OAuth authentication method.</p>
<p>All API calls for a distributor originate from that distributor's IMS Organization.</p>
<p>To obtain a valid access token, generate a JWT and exchange it via the IMS exchange API.</p>
<p>Adobe provides credentials for the Sandbox environment. The authentication flow is the same.</p>
<p>vipmp marker</p>
</main>
</body></html>
"""
