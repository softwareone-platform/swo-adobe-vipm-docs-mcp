"""
Adobe VIP Marketplace Docs MCP Server

Exposes two tools:
  - search_vipmp_docs(query)  : keyword search across the sitemap, returns matching pages
  - get_vipmp_page(path)      : fetch a specific doc page by its path

Pages are fetched on demand from developer.adobe.com and cached in memory (TTL: 1 hour).
"""

import re
import time
import httpx
from mcp.server.fastmcp import FastMCP
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Sitemap — extracted from the navigation tree on the docs index page.
# Each entry: (path, title, tags)
# Tags are used to improve keyword search recall.
# ---------------------------------------------------------------------------

SITEMAP: list[dict] = [
    # Introduction / Release notes
    {
        "path": "/vipmp/docs/",
        "title": "Introduction",
        "tags": ["overview", "introduction", "workflow", "order flow", "distributor", "reseller", "customer"],
    },
    {
        "path": "/vipmp/docs/release_notes/",
        "title": "Release Notes — Recent",
        "tags": ["release notes", "changelog", "recent", "updates"],
    },
    {
        "path": "/vipmp/docs/release_notes/upcoming_releases/",
        "title": "Release Notes — Upcoming",
        "tags": ["release notes", "upcoming", "roadmap", "future"],
    },

    # Authentication
    {
        "path": "/vipmp/docs/authentication/",
        "title": "API Authentication and Access",
        "tags": ["authentication", "auth", "access", "oauth", "credentials", "token"],
    },
    {
        "path": "/vipmp/docs/authentication/health_check/",
        "title": "Health Check",
        "tags": ["health check", "ping", "status", "connectivity"],
    },
    {
        "path": "/vipmp/docs/authentication/oauth_credentials/",
        "title": "Generate OAuth Credentials",
        "tags": ["oauth", "credentials", "token", "client id", "client secret", "authentication"],
    },

    # Reseller accounts
    {
        "path": "/vipmp/docs/reseller_account/",
        "title": "Reseller Accounts — Overview",
        "tags": ["reseller", "account", "partner", "distributor"],
    },
    {
        "path": "/vipmp/docs/reseller_account/create_reseller_account/",
        "title": "Create a Reseller Account",
        "tags": ["reseller", "create", "POST", "account", "new reseller"],
    },
    {
        "path": "/vipmp/docs/reseller_account/get_reseller_account/",
        "title": "Get Reseller Account Details",
        "tags": ["reseller", "get", "GET", "account details", "retrieve"],
    },
    {
        "path": "/vipmp/docs/reseller_account/get_reseller_list/",
        "title": "Get Reseller List",
        "tags": ["reseller", "list", "GET", "all resellers", "pagination"],
    },
    {
        "path": "/vipmp/docs/reseller_account/update_reseller_account/",
        "title": "Update a Reseller Account",
        "tags": ["reseller", "update", "PATCH", "PUT", "modify"],
    },

    # Customer accounts
    {
        "path": "/vipmp/docs/customer_account/",
        "title": "Customer Accounts — Overview",
        "tags": ["customer", "account", "overview"],
    },
    {
        "path": "/vipmp/docs/market_segments/",
        "title": "Market Segments",
        "tags": ["market segments", "commercial", "education", "government", "segment"],
    },
    {
        "path": "/vipmp/docs/customer_account/create_customer_account/",
        "title": "Create Customer Account",
        "tags": ["customer", "create", "POST", "new customer", "account"],
    },
    {
        "path": "/vipmp/docs/customer_account/get_customer_account/",
        "title": "Get Customer Account Details",
        "tags": ["customer", "get", "GET", "account details", "retrieve"],
    },
    {
        "path": "/vipmp/docs/customer_account/get_customer_list/",
        "title": "Get Customer List",
        "tags": ["customer", "list", "GET", "all customers", "pagination"],
    },
    {
        "path": "/vipmp/docs/customer_account/update_customer_account/",
        "title": "Update Customer Account",
        "tags": ["customer", "update", "PATCH", "PUT", "modify"],
    },
    {
        "path": "/vipmp/docs/customer_account/get_licenses/",
        "title": "Get Licenses Pending Partner Order",
        "tags": ["licenses", "pending", "GET", "customer licenses", "partner order"],
    },

    # Deployments
    {
        "path": "/vipmp/docs/deployment_management/",
        "title": "Deployments — Overview",
        "tags": ["deployment", "overview"],
    },
    {
        "path": "/vipmp/docs/deployment_management/create_deployment/",
        "title": "Create Deployment",
        "tags": ["deployment", "create", "POST"],
    },
    {
        "path": "/vipmp/docs/deployment_management/get_deployment/",
        "title": "Get Deployment Details",
        "tags": ["deployment", "get", "GET", "details"],
    },
    {
        "path": "/vipmp/docs/deployment_management/update_deployment/",
        "title": "Update a Deployment",
        "tags": ["deployment", "update", "PATCH", "PUT", "modify"],
    },

    # Orders
    {
        "path": "/vipmp/docs/order_management/",
        "title": "Orders — Overview",
        "tags": ["order", "overview", "cancel"],
    },
    {
        "path": "/vipmp/docs/order_management/create_order/",
        "title": "Create Order",
        "tags": ["order", "create", "POST", "new order", "purchase"],
    },
    {
        "path": "/vipmp/docs/order_management/order_scenarios/",
        "title": "Order Creation Scenarios",
        "tags": ["order", "scenarios", "examples", "use cases", "new", "renewal", "return"],
    },
    {
        "path": "/vipmp/docs/order_management/get_order/",
        "title": "Get Order Details",
        "tags": ["order", "get", "GET", "details", "retrieve"],
    },
    {
        "path": "/vipmp/docs/order_management/update_order/",
        "title": "Update Order",
        "tags": ["order", "update", "PATCH", "PUT", "cancel", "modify"],
    },

    # Subscriptions
    {
        "path": "/vipmp/docs/subscription_management/",
        "title": "Subscriptions — Overview",
        "tags": ["subscription", "overview", "auto-renewal"],
    },
    {
        "path": "/vipmp/docs/subscription_management/create_subscription/",
        "title": "Create Subscription",
        "tags": ["subscription", "create", "POST"],
    },
    {
        "path": "/vipmp/docs/subscription_management/get_details/",
        "title": "Get Details of a Specific Subscription",
        "tags": ["subscription", "get", "GET", "details", "single"],
    },
    {
        "path": "/vipmp/docs/subscription_management/get_details_for_customers/",
        "title": "Get All Subscriptions for a Customer",
        "tags": ["subscription", "list", "GET", "customer subscriptions", "all"],
    },
    {
        "path": "/vipmp/docs/subscription_management/update_subscription/",
        "title": "Update Subscription",
        "tags": ["subscription", "update", "PATCH", "PUT", "auto-renewal", "quantity", "modify"],
    },

    # Pricing & Notifications
    {
        "path": "/vipmp/docs/manage_pricing/",
        "title": "Price Lists",
        "tags": ["price list", "pricing", "pricelist", "POST", "currency", "offers", "3YC", "three-year commit"],
    },
    {
        "path": "/vipmp/docs/notification_management/",
        "title": "Notifications",
        "tags": ["notification", "webhook", "event", "callback", "push"],
    },

    # Operational workflows
    {
        "path": "/vipmp/docs/customer_account/three_year_commit/",
        "title": "Three-Year Commits (3YC)",
        "tags": ["3YC", "three year commit", "commitment", "price lock"],
    },
    {
        "path": "/vipmp/docs/customer_account/linked_membership/",
        "title": "Linked Memberships",
        "tags": ["linked membership", "membership", "link", "consolidation"],
    },
    {
        "path": "/vipmp/docs/customer_account/high_growth/",
        "title": "High Growth Offers — Overview",
        "tags": ["high growth", "HGO", "offers", "growth offer"],
    },
    {
        "path": "/vipmp/docs/customer_account/high_growth_scenarios/",
        "title": "High Growth Offer Scenarios",
        "tags": ["high growth", "HGO", "scenarios", "examples"],
    },
    {
        "path": "/vipmp/docs/customer_account/high_growth_apis/",
        "title": "Manage High Growth Offers through APIs",
        "tags": ["high growth", "HGO", "API", "manage"],
    },
    {
        "path": "/vipmp/docs/recommendations/",
        "title": "Recommendations — Overview",
        "tags": ["recommendations", "upsell", "cross-sell"],
    },
    {
        "path": "/vipmp/docs/recommendations/apis/",
        "title": "Manage Recommendations using APIs",
        "tags": ["recommendations", "API", "manage"],
    },
    {
        "path": "/vipmp/docs/recommendations/error_codes/",
        "title": "Error Codes — Recommendations",
        "tags": ["recommendations", "error codes", "errors"],
    },
    {
        "path": "/vipmp/docs/flex_discounts/",
        "title": "Flexible Discounts — Overview",
        "tags": ["flexible discounts", "flex discount", "discount"],
    },
    {
        "path": "/vipmp/docs/flex_discounts/apis/",
        "title": "Manage Flexible Discounts using APIs",
        "tags": ["flexible discounts", "API", "manage"],
    },
    {
        "path": "/vipmp/docs/flex_discounts/error_codes/",
        "title": "Error Codes — Flexible Discounts",
        "tags": ["flexible discounts", "error codes", "errors"],
    },
    {
        "path": "/vipmp/docs/mid_term/",
        "title": "Mid-Term Upgrades — Overview",
        "tags": ["mid-term", "upgrade", "mid term", "upsize"],
    },
    {
        "path": "/vipmp/docs/mid_term/apis/",
        "title": "Manage Mid-Term Upgrades through APIs",
        "tags": ["mid-term", "upgrade", "API", "manage"],
    },
    {
        "path": "/vipmp/docs/mid_term/error_codes/",
        "title": "Error Codes — Mid-Term Upgrades",
        "tags": ["mid-term", "upgrade", "error codes", "errors"],
    },
    {
        "path": "/vipmp/docs/mid_term/faq/",
        "title": "Mid-Term Upgrades FAQ",
        "tags": ["mid-term", "upgrade", "FAQ", "questions"],
    },

    # Business processes
    {
        "path": "/vipmp/docs/reseller_change/",
        "title": "Reseller Change Process — Overview",
        "tags": ["reseller change", "transfer", "reseller transfer", "change reseller"],
    },
    {
        "path": "/vipmp/docs/reseller_change/preview_transfer/",
        "title": "Preview a Reseller Transfer",
        "tags": ["reseller transfer", "preview", "GET"],
    },
    {
        "path": "/vipmp/docs/reseller_change/commit_transfer/",
        "title": "Commit a Reseller Transfer",
        "tags": ["reseller transfer", "commit", "POST"],
    },
    {
        "path": "/vipmp/docs/reseller_change/get_transfer/",
        "title": "Get Reseller Transfer Details",
        "tags": ["reseller transfer", "get", "GET", "details"],
    },
    {
        "path": "/vipmp/docs/migration/",
        "title": "Migrate to VIP Marketplace — Overview",
        "tags": ["migration", "VIP", "transfer", "migrate", "classic VIP"],
    },
    {
        "path": "/vipmp/docs/migration/preview_offers/",
        "title": "Preview Offers (Migration)",
        "tags": ["migration", "preview", "offers", "eligibility"],
    },
    {
        "path": "/vipmp/docs/migration/transfer_subscription/",
        "title": "Transfer Subscriptions (Migration)",
        "tags": ["migration", "transfer", "subscription", "POST"],
    },
    {
        "path": "/vipmp/docs/migration/get_transfer_details/",
        "title": "Get Transfer Details (Migration)",
        "tags": ["migration", "transfer", "get", "GET", "details"],
    },
    {
        "path": "/vipmp/docs/migration/migrate_hvd/",
        "title": "Migrate High Volume Discount (HVD) Customers",
        "tags": ["migration", "HVD", "high volume discount", "VIP to VIP MP"],
    },

    # Large Government Agencies (LGA)
    {
        "path": "/vipmp/docs/lga/",
        "title": "Large Government Agencies (LGA) — Overview",
        "tags": ["LGA", "large government agency", "government", "GOV", "discount", "federal", "state", "linked membership", "US", "Canada"],
    },
    {
        "path": "/vipmp/docs/lga/create",
        "title": "Create an LGA Customer",
        "tags": ["LGA", "large government agency", "create", "POST", "customer", "FEDERAL", "STATE", "marketSubSegments", "linked membership", "enroll"],
    },
    {
        "path": "/vipmp/docs/lga/migrate",
        "title": "Migrate LGA Customers from VIP to VIP Marketplace",
        "tags": ["LGA", "large government agency", "migration", "transfer", "VIP", "migrate", "preview", "FRL"],
    },
    {
        "path": "/vipmp/docs/lga/convert",
        "title": "Convert an Existing Government Customer to LGA",
        "tags": ["LGA", "large government agency", "convert", "GOV", "government", "PENDING_UPGRADE", "anniversary date", "AD", "renewal", "PATCH"],
    },
    {
        "path": "/vipmp/docs/lga/error-codes",
        "title": "Error Codes — LGA",
        "tags": ["LGA", "large government agency", "error codes", "errors", "1117", "1118", "1147", "1163", "1164", "1167", "1168", "5117"],
    },
    {
        "path": "/vipmp/docs/lga/references",
        "title": "LGA References",
        "tags": ["LGA", "large government agency", "references"],
    },

    # References
    {
        "path": "/vipmp/docs/references/api_headers/",
        "title": "API Request Headers",
        "tags": ["headers", "request headers", "x-api-key", "authorization", "content-type"],
    },
    {
        "path": "/vipmp/docs/references/idempotency/",
        "title": "Idempotency — Correlation ID Header",
        "tags": ["idempotency", "correlation id", "x-correlation-id", "duplicate requests"],
    },
    {
        "path": "/vipmp/docs/references/status_codes/",
        "title": "HTTP Status Codes",
        "tags": ["HTTP status codes", "200", "400", "404", "500", "error", "response codes"],
    },
    {
        "path": "/vipmp/docs/references/error_handling/",
        "title": "Status Codes and Error Handling",
        "tags": ["error handling", "error codes", "status codes", "errors", "troubleshooting"],
    },
    {
        "path": "/vipmp/docs/references/supported_locales/",
        "title": "Supported Countries and Locales",
        "tags": ["countries", "locales", "currency", "region", "supported"],
    },
    {
        "path": "/vipmp/docs/references/resources/",
        "title": "Resources and Fields",
        "tags": ["resources", "fields", "schema", "data model", "object reference"],
    },
    {
        "path": "/vipmp/docs/references/validations/",
        "title": "Validations and Regular Expressions",
        "tags": ["validation", "regex", "regular expressions", "field validation", "format"],
    },

    # Support
    {
        "path": "/vipmp/docs/support/",
        "title": "Support",
        "tags": ["support", "help", "contact"],
    },
]

BASE_URL = "https://developer.adobe.com"
CACHE_TTL_SECONDS = 3600  # 1 hour

# In-memory cache: path -> {"content": str, "fetched_at": float}
_cache: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_page(path: str) -> str:
    """Fetch a doc page and return cleaned Markdown-style plain text."""
    now = time.time()
    cached = _cache.get(path)
    if cached and (now - cached["fetched_at"]) < CACHE_TTL_SECONDS:
        return cached["content"]

    url = BASE_URL + path
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; VIPMPDocsMCP/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove nav, footer, script, style, breadcrumb noise
    for tag in soup.select("nav, footer, script, style, .gatsby-highlight, header"):
        tag.decompose()

    # Find main content area
    main = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile(r"content|main|body", re.I))
    target = main if main else soup

    # Extract text, preserving some structure
    lines = []
    for element in target.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li", "pre", "code", "th", "td"]):
        tag = element.name
        text = element.get_text(separator=" ", strip=True)
        if not text:
            continue
        if tag == "h1":
            lines.append(f"\n# {text}\n")
        elif tag == "h2":
            lines.append(f"\n## {text}\n")
        elif tag == "h3":
            lines.append(f"\n### {text}\n")
        elif tag in ("h4", "h5"):
            lines.append(f"\n#### {text}\n")
        elif tag == "pre":
            lines.append(f"\n```\n{text}\n```\n")
        elif tag == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)

    content = "\n".join(lines).strip()
    content = re.sub(r"\n{3,}", "\n\n", content)  # collapse excessive blank lines

    _cache[path] = {"content": content, "fetched_at": now}
    return content


def _score_entry(entry: dict, query: str) -> int:
    """Simple relevance score: count query term matches in title + tags."""
    terms = re.findall(r"\w+", query.lower())
    haystack = (entry["title"] + " " + " ".join(entry["tags"])).lower()
    return sum(1 for t in terms if t in haystack)


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "vipmp-docs",
    instructions=(
        "Use this server to look up Adobe VIP Marketplace Partner API documentation. "
        "Call search_vipmp_docs first to find relevant pages, then get_vipmp_page to read full content."
    ),
)


@mcp.tool()
def list_vipmp_docs() -> str:
    """
    Return the full sitemap of Adobe VIP Marketplace API documentation.
    Use this to browse all available topics or to find exact page paths.
    """
    lines = ["# Adobe VIP Marketplace Docs — Sitemap\n"]
    current_section = ""
    for entry in SITEMAP:
        # Derive a rough section header from path depth
        parts = [p for p in entry["path"].strip("/").split("/") if p]
        section = parts[1] if len(parts) > 1 else "root"
        if section != current_section:
            lines.append(f"\n## {section.replace('_', ' ').title()}")
            current_section = section
        lines.append(f"- **{entry['title']}** → `{entry['path']}`")
    return "\n".join(lines)


@mcp.tool()
def search_vipmp_docs(query: str, max_results: int = 5) -> str:
    """
    Search the Adobe VIP Marketplace API documentation by keyword or topic.
    Returns matching page titles, paths, and fetched content for the top results.

    Args:
        query: Search terms, e.g. "create order", "oauth token", "error codes", "3YC"
        max_results: Maximum number of pages to return (default 5, max 10)
    """
    max_results = min(max_results, 10)
    scored = [(entry, _score_entry(entry, query)) for entry in SITEMAP]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [(e, s) for e, s in scored if s > 0][:max_results]

    if not top:
        return (
            f"No pages matched '{query}'.\n\n"
            "Try calling list_vipmp_docs() to browse all available topics."
        )

    results = [f"# Search results for: '{query}'\n"]
    for entry, score in top:
        results.append(f"---\n## {entry['title']}\n**Path:** `{entry['path']}`\n")
        try:
            content = _fetch_page(entry["path"])
            # Truncate very long pages to keep responses manageable
            if len(content) > 6000:
                content = content[:6000] + "\n\n[...content truncated — call get_vipmp_page for full content...]"
            results.append(content)
        except Exception as exc:
            results.append(f"_(Could not fetch page: {exc})_")

    return "\n\n".join(results)


@mcp.tool()
def get_vipmp_page(path: str) -> str:
    """
    Fetch the full content of a specific Adobe VIP Marketplace documentation page.

    Args:
        path: The doc path, e.g. "/vipmp/docs/order_management/create_order/"
              Use list_vipmp_docs() or search_vipmp_docs() to find valid paths.
    """
    # Normalise path
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path = path + "/"

    # Check it's a known path (warn but still attempt if unknown)
    known_paths = {e["path"] for e in SITEMAP}
    warning = ""
    if path not in known_paths:
        warning = (
            f"⚠️  '{path}' is not in the known sitemap. Attempting fetch anyway.\n\n"
        )

    try:
        content = _fetch_page(path)
        url = BASE_URL + path
        return f"{warning}# {path}\n**Source:** {url}\n\n{content}"
    except httpx.HTTPStatusError as exc:
        return f"{warning}HTTP error fetching '{path}': {exc.response.status_code} {exc.response.reason_phrase}"
    except Exception as exc:
        return f"{warning}Error fetching '{path}': {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
