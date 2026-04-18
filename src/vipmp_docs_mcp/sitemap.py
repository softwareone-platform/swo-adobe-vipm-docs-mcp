"""
Sitemap of Adobe VIP Marketplace Partner API documentation.

Currently hand-curated. Phase 4 will add auto-refresh from the docs nav tree
and allow loading from a persisted `sitemap.json`.

Each entry:
    path:  Absolute docs path (starts with "/vipmp/docs/")
    title: Human-readable page title
    tags:  Extra search terms to improve recall on keyword matches
"""

from __future__ import annotations

from typing import TypedDict


class SitemapEntry(TypedDict):
    path: str
    title: str
    tags: list[str]


SITEMAP: list[SitemapEntry] = [
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

    # Large Government Agencies (LGA) — note: these use trailing-slashless paths in Adobe's docs
    {
        "path": "/vipmp/docs/lga/",
        "title": "Large Government Agencies (LGA) — Overview",
        "tags": ["LGA", "large government agency", "government", "GOV", "discount", "federal", "state", "linked membership", "US", "Canada"],
    },
    {
        "path": "/vipmp/docs/lga/create/",
        "title": "Create an LGA Customer",
        "tags": ["LGA", "large government agency", "create", "POST", "customer", "FEDERAL", "STATE", "marketSubSegments", "linked membership", "enroll"],
    },
    {
        "path": "/vipmp/docs/lga/migrate/",
        "title": "Migrate LGA Customers from VIP to VIP Marketplace",
        "tags": ["LGA", "large government agency", "migration", "transfer", "VIP", "migrate", "preview", "FRL"],
    },
    {
        "path": "/vipmp/docs/lga/convert/",
        "title": "Convert an Existing Government Customer to LGA",
        "tags": ["LGA", "large government agency", "convert", "GOV", "government", "PENDING_UPGRADE", "anniversary date", "AD", "renewal", "PATCH"],
    },
    {
        "path": "/vipmp/docs/lga/error-codes/",
        "title": "Error Codes — LGA",
        "tags": ["LGA", "large government agency", "error codes", "errors", "1117", "1118", "1147", "1163", "1164", "1167", "1168", "5117"],
    },
    {
        "path": "/vipmp/docs/lga/references/",
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


def normalize_path(path: str) -> str:
    """
    Canonical form: leading slash, NO trailing slash (except the bare root).

    Adobe's docs site is inconsistent: some pages only resolve without a
    trailing slash, others only with one. We store/compare canonically and
    let the fetcher try both variants on a 404.
    """
    if not path.startswith("/"):
        path = "/" + path
    # Strip trailing slash unless the whole path is just "/".
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def known_paths() -> set[str]:
    """Normalized set of known doc paths for membership checks."""
    return {normalize_path(e["path"]) for e in SITEMAP}


def find_by_path(path: str) -> SitemapEntry | None:
    """Look up a sitemap entry by path (normalized)."""
    normalized = normalize_path(path)
    for entry in SITEMAP:
        if normalize_path(entry["path"]) == normalized:
            return entry
    return None
