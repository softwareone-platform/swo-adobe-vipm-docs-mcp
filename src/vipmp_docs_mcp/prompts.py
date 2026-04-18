"""
MCP Prompts — reusable prompt templates the MCP client can offer to users.

Tools are invoked by Claude. Prompts are invoked by humans (via a
prompt-picker in the client UI) and expand into a conversation starter
that pre-fills context, suggests which tools to call, and asks the right
questions.

Each prompt below returns a Markdown string. The client will inject it
as the user's next message.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    """Register all VIPMP prompts on the given FastMCP instance."""

    @mcp.prompt()
    def review_request_body(endpoint: str, body_json: str) -> str:
        """
        Validate a JSON request body against the documented VIPMP schema
        for a given endpoint.

        Args:
            endpoint: The documented endpoint, e.g. "POST /v3/customers".
            body_json: The JSON body to check, as a string.
        """
        return f"""I'd like you to review this JSON request body against the VIPMP schema.

**Endpoint:** `{endpoint}`

**Body:**
```json
{body_json}
```

Please:
1. Call `search_vipmp_docs` with a query matching the endpoint
   (e.g. "{endpoint.split()[-1].strip('/').split('/')[-1].replace('-', ' ')}")
   to find the right docs page.
2. Call `get_vipmp_schema` with the relevant resource name to fetch the
   field definitions.
3. For each field in my body, check:
   - Is it a valid field name on this resource?
   - Is the type correct? (e.g. String vs Integer, date format)
   - Are there constraints (Max length, regex, enum values) it violates?
   - Are any required fields missing?
4. Call `list_vipmp_error_codes` with the endpoint to surface the
   specific errors my body could produce.
5. Summarise: valid, and/or a prioritised list of issues to fix.

Be specific — quote the docs verbatim when flagging problems.
"""

    @mcp.prompt()
    def debug_error_code(code: str, endpoint: str | None = None) -> str:
        """
        Diagnose a VIPMP error code the user is hitting. Surfaces the docs
        for the code, what triggers it, and how to fix.

        Args:
            code: The error code (e.g. "1117", "5117", "INVALID_LM_MIGRATION_LEVEL").
            endpoint: Optional endpoint it was triggered by (e.g.
                "POST /v3/customers") — tightens the diagnosis.
        """
        endpoint_hint = (
            f" on `{endpoint}`" if endpoint else " (endpoint not specified)"
        )
        return f"""I'm hitting VIPMP error code **{code}**{endpoint_hint}. Help me understand it and fix it.

Please:
1. Call `list_vipmp_error_codes` with `query="{code}"` to find the exact
   documentation for this code.
2. If multiple pages define it (codes are reused across endpoints), pick
   the entry that matches the endpoint I mentioned — or, if none does,
   list all occurrences so I can say which one I'm hitting.
3. Call `get_vipmp_page` on the docs_path that defined the code to read
   the full page context (precondition, expected response shape, etc.).
4. If the error is about field validation, call `get_vipmp_schema` for
   the relevant resource and cross-reference the field constraints.
5. Summarise:
   - **What triggers this:** one sentence
   - **Request conditions:** what state causes it
   - **How to fix:** concrete next steps, with a sample corrected request
     body if applicable

If the code isn't documented, say so plainly — don't make something up.
"""

    @mcp.prompt()
    def draft_order(
        customer_id: str,
        offers: str,
        market_segment: str = "COM",
    ) -> str:
        """
        Walk through creating a VIPMP order from scratch: prerequisites,
        schema, request body, and expected response.

        Args:
            customer_id: The existing customer's ID.
            offers: Comma-separated offer IDs (or a rough description — the
                model can look up actual IDs from the price list docs).
            market_segment: Market segment code (default "COM" for Commercial).
        """
        return f"""Help me draft a VIPMP `POST /v3/orders` request.

**Context:**
- Customer ID: `{customer_id}`
- Target offers: {offers}
- Market segment: {market_segment}

Please:
1. Call `search_vipmp_docs` with `query="create order"` to fetch the
   Create Order docs page.
2. Call `get_vipmp_schema` with `resource_name="order"` (and any nested
   types like "order item") to get the full field list.
3. Walk me through the prerequisites:
   - Does the customer account need to exist and be in a specific state?
   - Do I need a reseller relationship? Deployment?
   - Any 3YC, LGA, or high-growth considerations for this customer/segment?
4. Produce a valid JSON request body for my inputs. Explicitly flag any
   fields where you're guessing (e.g. optional fields I didn't specify).
5. Call `get_vipmp_code_examples` with the create-order docs path and
   `language="json"` to show me a reference example next to yours.
6. Show the expected 201 response shape and the error codes I should
   handle (call `list_vipmp_error_codes` with `query="orders"`).

Be explicit about any assumptions. If the schema demands something I
haven't told you about, ask me for it rather than inventing a value.
"""

    @mcp.prompt()
    def summarize_recent_changes(
        since: str | None = None,
        area: str | None = None,
    ) -> str:
        """
        Summarise what's changed in the VIPMP API since a given date,
        optionally narrowed to a specific area of the docs.

        Args:
            since: ISO date ("YYYY-MM-DD"). Defaults to the last ~30 days
                if omitted — leave blank for "what's new recently".
            area: Optional topic filter — e.g. "orders", "3YC",
                "flexible discounts", "LGA", "subscriptions". Matches
                against release titles and bodies.
        """
        from datetime import date, timedelta

        effective_since = since or (date.today() - timedelta(days=30)).isoformat()
        area_line = f"\n- **Narrow to area:** {area}" if area else ""
        area_filter_step = (
            f"   After gathering, filter all three sets to entries whose "
            f"title or body mentions {area!r} (case-insensitive). Drop the rest.\n"
            if area
            else ""
        )
        scope_note = (
            f" in area {area!r}" if area else ""
        )
        return f"""Summarise what's changed in the VIPMP API recently.

**Scope:**
- **Since:** {effective_since}{area_line}

Please:
1. Call `list_vipmp_releases` with `since="{effective_since}"` to get
   structured API-change entries.
2. Separately call `list_vipmp_releases` with `section="sandbox"` and the
   same `since` — Sandbox changes matter for testing even when they're
   not in the production stream.
3. Also call `list_vipmp_releases` with `section="upcoming"` — flag
   anything in the pipeline that's relevant.
{area_filter_step}4. Produce a summary grouped by theme (not by date) — e.g. "New
   endpoints", "New error codes", "Behaviour changes on existing
   endpoints", "Sandbox-only", "Still upcoming". Within each theme,
   cite the release date.
5. For each change, include a one-line "why this matters to a partner
   integration" note — don't just restate the title.
6. Flag any change that looks like a **breaking** or **deprecation** —
   those need explicit attention.

Keep it scannable: bullet points, not prose. Each release entry in the
output should include its date and a link back to the docs page so I
can drill in.

If there's nothing since {effective_since}{scope_note}, say so plainly
rather than padding with older content.
"""

    @mcp.prompt()
    def check_feature_status(feature: str) -> str:
        """
        Determine whether a VIPMP feature is live in production, shipping
        in Sandbox, upcoming, or not documented. Cross-references release
        notes with the docs index.

        Args:
            feature: A concise description of the feature (e.g.
                "Early Renewals", "Mid-term Upgrades", "LGA conversion",
                "Flexible Discounts for renewals").
        """
        return f"""I need to know the VIPMP release status of this feature:

**Feature:** {feature}

Please:
1. Call `list_vipmp_releases` (no date filter) and search the titles +
   bodies for the feature. Likely status buckets:
   - **Live in production** — found under `section="api_changes"`, with
     a specific date
   - **In Sandbox** — found under `section="sandbox"` but not yet in
     `api_changes`
   - **Upcoming** — found under `section="upcoming"`
   - **Not documented** — none of the above matched
2. If status is "Live", also call `search_vipmp_docs` with the feature
   name to find the canonical reference page for the feature and
   surface it.
3. If status is "Upcoming", note that Adobe's upcoming-releases page is
   sometimes a stub — treat any finding there as provisional and
   suggest I ask my Adobe contact for timing.
4. If status is "Not documented", don't make something up. Try once
   more with loose keywords from the feature name, then say the feature
   isn't in the docs index and suggest the user verify the feature name
   or check Adobe's partner channels.

Output:
- **Status:** one of the four buckets above
- **Release date** (if Live / in Sandbox)
- **Evidence:** the release entry or doc page you based the answer on
  — quote the relevant title and cite the docs path
- **Consequences for integrators:** any action items this status
  implies (e.g. "Safe to call now in production" vs "Do not ship until
  <date>" vs "Ask Adobe for ETA")

Be honest about uncertainty. "Probably live but the release entry is
ambiguous" is more useful than a confident guess.
"""

    @mcp.prompt()
    def check_3yc_eligibility(
        customer_id: str,
        desired_commit_quantity: int | None = None,
    ) -> str:
        """
        Walk through the 3-Year Commit (3YC) eligibility and enrollment
        rules for a specific customer.

        Args:
            customer_id: The customer ID to evaluate.
            desired_commit_quantity: Optional target commit quantity the
                customer is considering.
        """
        qty_line = (
            f"- Desired commit quantity: **{desired_commit_quantity}**"
            if desired_commit_quantity is not None
            else "- Desired commit quantity: (not specified — can help decide)"
        )
        return f"""Help me evaluate a VIPMP 3-Year Commit (3YC) case for a customer.

**Context:**
- Customer ID: `{customer_id}`
{qty_line}

Please:
1. Call `search_vipmp_docs` with `query="three year commit 3YC eligibility"`
   to find the 3YC docs pages.
2. Call `get_vipmp_page` on each relevant page — the 3YC overview, the
   3YC-related APIs, and any page about minimum commit quantities.
3. Call `get_vipmp_schema` with `resource_name="three year commit"` (or
   whatever resource names appear) for the field shapes.
4. Walk me through:
   - **Eligibility rules:** who can enroll, in what state, under what
     licensing model (Adobe has specific cut-offs)
   - **Minimum commit:** what's the floor, per segment/region
   - **Price-lock behaviour:** what stays fixed, what doesn't, and for
     how long
   - **Renewal / anniversary date** implications
   - **Enrollment API flow:** which endpoints to call in what order
5. If the customer's desired commit quantity is below any documented
   minimum, flag it and suggest a compliant alternative.
6. Call `list_vipmp_error_codes` with `query="3yc"` to surface error
   codes I should handle defensively.

Quote the docs directly when stating rules — don't paraphrase limits.
"""
