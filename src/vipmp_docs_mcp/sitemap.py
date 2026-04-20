"""
Hand-authored metadata that complements Adobe's live sitemap.

Originally this module held a full hand-curated list of doc paths. That list
drifted once Adobe migrated their slug convention from underscores to
hyphens — see GitHub issue #6. The path list is now retired and replaced by
two narrow data structures:

* ``SitemapEntry`` — the TypedDict shape every other module expects for a
  sitemap entry, preserved here as a shared vocabulary.
* ``CURATED_TAGS`` — a ``{last-path-segment: [tags, ...]}`` dict used by
  ``autositemap.merge_curated_tags`` to add semantic tags (e.g. "3YC",
  "LGA", "HGO") onto entries Adobe sources. The live sitemap arrives
  from Adobe's ``/sitemap.xml`` via [autositemap.py](./autositemap.py);
  the tags below are what we contribute on top.

Adding entries here improves search recall by giving pages extra keywords
the title alone doesn't carry. Keys must match the page's final path
segment (hyphens, lowercase). Tag ordering is irrelevant — search treats
them as a set.
"""

from __future__ import annotations

from typing import TypedDict


class SitemapEntry(TypedDict):
    path: str
    title: str
    tags: list[str]


# Last-path-segment → semantic tags. Consumed by
# ``autositemap.merge_curated_tags`` to enrich live Adobe-sourced entries.
#
# When multiple pages share a last segment (e.g. ``.../flex-discounts/apis/``
# and ``.../mid-term/apis/``) only one tag list can win per key; the order
# below is the order that used to be encoded implicitly in the old SITEMAP
# list (last-wins, preserved for behaviour parity).
CURATED_TAGS: dict[str, list[str]] = {
    "api-headers": ["authorization", "content-type", "headers", "request headers", "x-api-key"],
    "apis": ["API", "manage", "mid-term", "upgrade"],
    "authentication": ["access", "auth", "authentication", "credentials", "oauth", "token"],
    "commit-transfer": ["POST", "commit", "reseller transfer"],
    "convert": ["AD", "GOV", "LGA", "PATCH", "PENDING_UPGRADE", "anniversary date", "convert", "government", "large government agency", "renewal"],
    "create": ["FEDERAL", "LGA", "POST", "STATE", "create", "customer", "enroll", "large government agency", "linked membership", "marketSubSegments"],
    "create-customer-account": ["POST", "account", "create", "customer", "new customer"],
    "create-deployment": ["POST", "create", "deployment"],
    "create-order": ["POST", "create", "new order", "order", "purchase"],
    "create-reseller-account": ["POST", "account", "create", "new reseller", "reseller"],
    "create-subscription": ["POST", "create", "subscription"],
    "customer-account": ["account", "customer", "overview"],
    "deployment-management": ["deployment", "overview"],
    "docs": ["customer", "distributor", "introduction", "order flow", "overview", "reseller", "workflow"],
    "error-codes": ["1117", "1118", "1147", "1163", "1164", "1167", "1168", "5117", "LGA", "error codes", "errors", "large government agency"],
    "error-handling": ["error codes", "error handling", "errors", "status codes", "troubleshooting"],
    "faq": ["FAQ", "mid-term", "questions", "upgrade"],
    "flex-discounts": ["discount", "flex discount", "flexible discounts"],
    "get-customer-account": ["GET", "account details", "customer", "get", "retrieve"],
    "get-customer-list": ["GET", "all customers", "customer", "list", "pagination"],
    "get-deployment": ["GET", "deployment", "details", "get"],
    "get-details": ["GET", "details", "get", "single", "subscription"],
    "get-details-for-customers": ["GET", "all", "customer subscriptions", "list", "subscription"],
    "get-licenses": ["GET", "customer licenses", "licenses", "partner order", "pending"],
    "get-order": ["GET", "details", "get", "order", "retrieve"],
    "get-reseller-account": ["GET", "account details", "get", "reseller", "retrieve"],
    "get-reseller-list": ["GET", "all resellers", "list", "pagination", "reseller"],
    "get-transfer": ["GET", "details", "get", "reseller transfer"],
    "get-transfer-details": ["GET", "details", "get", "migration", "transfer"],
    "health-check": ["connectivity", "health check", "ping", "status"],
    "high-growth": ["HGO", "growth offer", "high growth", "offers"],
    "high-growth-apis": ["API", "HGO", "high growth", "manage"],
    "high-growth-scenarios": ["HGO", "examples", "high growth", "scenarios"],
    "idempotency": ["correlation id", "duplicate requests", "idempotency", "x-correlation-id"],
    "lga": ["Canada", "GOV", "LGA", "US", "discount", "federal", "government", "large government agency", "linked membership", "state"],
    "linked-membership": ["consolidation", "link", "linked membership", "membership"],
    "manage-pricing": ["3YC", "POST", "currency", "offers", "price list", "pricelist", "pricing", "three-year commit"],
    "market-segments": ["commercial", "education", "government", "market segments", "segment"],
    "mid-term": ["mid term", "mid-term", "upgrade", "upsize"],
    "migrate": ["FRL", "LGA", "VIP", "large government agency", "migrate", "migration", "preview", "transfer"],
    "migrate-hvd": ["HVD", "VIP to VIP MP", "high volume discount", "migration"],
    "migration": ["VIP", "classic VIP", "migrate", "migration", "transfer"],
    "notification-management": ["callback", "event", "notification", "push", "webhook"],
    "oauth-credentials": ["authentication", "client id", "client secret", "credentials", "oauth", "token"],
    "order-management": ["cancel", "order", "overview"],
    "order-scenarios": ["examples", "new", "order", "renewal", "return", "scenarios", "use cases"],
    "preview-offers": ["eligibility", "migration", "offers", "preview"],
    "preview-transfer": ["GET", "preview", "reseller transfer"],
    "recommendations": ["cross-sell", "recommendations", "upsell"],
    "references": ["LGA", "large government agency", "references"],
    "release-notes": ["changelog", "recent", "release notes", "updates"],
    "reseller-account": ["account", "distributor", "partner", "reseller"],
    "reseller-change": ["change reseller", "reseller change", "reseller transfer", "transfer"],
    "resources": ["data model", "fields", "object reference", "resources", "schema"],
    "status-codes": ["200", "400", "404", "500", "HTTP status codes", "error", "response codes"],
    "subscription-management": ["auto-renewal", "overview", "subscription"],
    "support": ["contact", "help", "support"],
    "supported-locales": ["countries", "currency", "locales", "region", "supported"],
    "three-year-commit": ["3YC", "commitment", "price lock", "three year commit"],
    "transfer-subscription": ["POST", "migration", "subscription", "transfer"],
    "upcoming-releases": ["future", "release notes", "roadmap", "upcoming"],
    "update-customer-account": ["PATCH", "PUT", "customer", "modify", "update"],
    "update-deployment": ["PATCH", "PUT", "deployment", "modify", "update"],
    "update-order": ["PATCH", "PUT", "cancel", "modify", "order", "update"],
    "update-reseller-account": ["PATCH", "PUT", "modify", "reseller", "update"],
    "update-subscription": ["PATCH", "PUT", "auto-renewal", "modify", "quantity", "subscription", "update"],
    "validations": ["field validation", "format", "regex", "regular expressions", "validation"],
}


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
