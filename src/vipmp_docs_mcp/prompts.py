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

import re
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .supplement import get_section as _get_supplement_section


def _supplement_block(heading: str) -> str:
    """
    Render the SWO training-supplement section for ``heading`` as a
    Markdown block for inclusion in a walkthrough prompt, or a short
    placeholder if no section exists / the file is missing.

    Ends with an auto-extracted "Topics to weave" checklist of the
    supplement's H3 subheadings. Empirically — two iterations in —
    the LLM ignores supplement prose when it's just a block of text
    above the teaching flow, but covers named items from a bulleted
    checklist reliably. "globalSalesEnabled" on its own line near the
    flow instructions is stickier than the same fact buried in a
    paragraph of bullet context.
    """
    body = _get_supplement_section(heading)
    if not body:
        return (
            "> _SWO training supplement: no notes yet for this topic. "
            "Lean on Adobe's published docs and acknowledge that "
            "operational context is still being written._\n"
        )

    # Each H3 subsection in the supplement is a concrete topic to cover.
    # Emit them as a short checklist below the content.
    topics = re.findall(r"^###\s+(.+?)\s*$", body, re.MULTILINE)
    topics_block = ""
    if topics:
        topic_lines = "\n".join(f"- {t}" for t in topics)
        topics_block = (
            f"\n\n_Topics from the supplement to weave into the walkthrough "
            f"(each at the step where a learner would first encounter it):_\n\n"
            f"{topic_lines}\n"
        )

    return (
        f"**SWO training supplement — {heading}:**\n\n"
        f"{body}"
        f"{topics_block}\n\n---\n"
    )


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

    # ----------------------------------------------------------------
    # Training curriculum — onboarding router + six concept walkthroughs.
    #
    # These are the "learn how VIPMP works" prompts, designed to serve
    # both developers (who benefit from business context alongside the
    # API) and technical product managers (who benefit from seeing the
    # API surface alongside the business rules). Each walkthrough pulls
    # a section from the human-authored training supplement at
    # content/training-supplement.md and interleaves it with Adobe's
    # published docs fetched via the existing tools.
    # ----------------------------------------------------------------

    @mcp.prompt()
    def start_vipmp_learning(
        role: Literal["developer", "product_manager", "either"] = "either",
        goal: str | None = None,
    ) -> str:
        """
        Kick off a VIPMP learning session. Asks the learner's role and
        goal, then routes them to the right walkthrough prompt.

        Args:
            role: Which hat the learner is wearing. Default "either" —
                the curriculum serves both developers and technical PMs.
            goal: Free-text description of what they want to learn or
                build. Used to route to a specific walkthrough.
        """
        goal_line = (
            f"\n- **Goal:** {goal}"
            if goal
            else "\n- **Goal:** (not specified — ask me)"
        )
        return f"""I'd like to learn how Adobe VIP Marketplace (VIPMP) works.

- **Role:** {role}{goal_line}

You have six walkthrough prompts available that I can invoke next — each
covers one area with both business context and the API surface:

1. `learn_customer_lifecycle` — states, transitions, onboarding
2. `learn_ordering_flow` — placing an order end-to-end
3. `learn_3yc` — 3-Year Commit eligibility, math, enrollment
4. `learn_subscriptions_and_renewals` — coterm, auto-renew, proration
5. `learn_returns_and_refunds` — windows, rules, API sequence
6. `learn_auth_and_sandbox` — IMS, credentials, safe testing

Please:

1. Based on my goal (above), suggest the **best starting walkthrough**
   and give a one-sentence reason.
2. If my goal is empty or vague, ask me two short questions — what I'm
   trying to build or decide, and how much VIPMP exposure I already
   have — then pick based on my answers.
3. After the first walkthrough, suggest what to do next. The order
   above is the default sequence for a learner starting cold, but
   don't force it — skip topics that aren't relevant to my goal.
4. Throughout the session, remember I might be a {role} — frame
   examples accordingly. A developer wants code; a product manager
   wants decision criteria; "either" means blend both.

Be patient and concrete. Prefer examples to abstractions. If I ask
something the docs don't cover cleanly, say so plainly rather than
guessing.
"""

    @mcp.prompt()
    def learn_customer_lifecycle() -> str:
        """
        Walkthrough: VIPMP customer lifecycle. Covers the business
        states a customer passes through, the API transitions between
        them, and the gotchas that bite real implementations.
        """
        return f"""Teach me the VIPMP customer lifecycle — the business
state machine AND the API that implements it. I want this to serve
whether I'm about to write code against it or making product decisions
that depend on it, so don't shy away from either angle.

**Open with the big picture.** One short paragraph placing the
customer inside VIPMP's partner model — distributor → reseller →
customer → orders and subscriptions — before any API detail. A
newcomer needs that map to make sense of everything after.

{_supplement_block("Customer lifecycle")}
**Teaching flow:**

1. Fetch Adobe's published material first. Call `search_vipmp_docs`
   with `query="customer lifecycle"` and pull the top 2-3 pages via
   `get_vipmp_page`.
2. Explain the commercial states a customer moves through (pending,
   active, suspended, terminated, whatever Adobe actually documents) —
   what each means, when it's entered, who causes the transition.
3. Map each meaningful transition to its API surface. For each:
   - Endpoint (`describe_vipmp_endpoint` for the detail)
   - What body fields matter
   - What response / status-code indicates success vs "accepted but
     pending"
4. Surface the real errors: `list_vipmp_error_codes` with
   `query="customer"` — call out business meaning, not just the code.
5. Highlight the common traps explicitly. Examples worth checking:
   LGA vs GOV vs COM segmentation, MEA flag, 3YC carryover,
   one-way transitions.
6. End with two short "check my understanding" questions — not a
   quiz, just enough to surface gaps.

Open with one sentence on where you're starting, then go. If the SWO
supplement above is still TODO, say so and lean harder on Adobe's
docs.
"""

    @mcp.prompt()
    def learn_ordering_flow() -> str:
        """
        Walkthrough: VIPMP ordering flow end-to-end. Covers what an
        order means commercially, the API sequence to place one, and
        the failure modes that matter in production.
        """
        return f"""Teach me how VIPMP ordering works end-to-end —
from the commercial meaning of an order to the API sequence to place
one successfully. Tech + business context both welcome.

{_supplement_block("Ordering flow")}
**Teaching flow:**

1. Pull Adobe's docs. `search_vipmp_docs` with `query="create order"`
   and `query="order status"`; follow up with `get_vipmp_page` on the
   strongest hits.
2. Explain the commercial lifecycle of an order — what states it
   passes through, what each state means for the customer and the
   partner, and when the order is truly "live" vs merely accepted.
3. Walk the happy-path API sequence:
   - Prerequisites (customer account state, reseller linkage, etc.)
   - `POST /v3/orders` — call `describe_vipmp_endpoint` and explain
     the body shape plus any gotchas with offer IDs or quantities
   - Polling / webhook model for status — whichever Adobe actually
     documents
4. Show a minimum viable request body (ask `get_vipmp_code_examples`
   for a reference example) and annotate each field with why it
   matters.
5. Error handling: `list_vipmp_error_codes` with `query="orders"` —
   group by "fixable by the partner" vs "requires Adobe / SWO
   intervention."
6. End with one scenario-based question: "given customer X with
   state Y and target Z, walk me through what you'd do." Use it to
   check the learner mapped business → API correctly.

Be honest when Adobe's docs are ambiguous; note where you'd want
the SWO supplement to fill the gap.
"""

    @mcp.prompt()
    def learn_3yc() -> str:
        """
        Walkthrough: 3-Year Commit (3YC). Covers eligibility,
        commit-quantity math, enrollment flow, and the commercial
        consequences of under-consumption.
        """
        return f"""Teach me about the VIPMP 3-Year Commit (3YC) program
— what it is commercially, who's eligible, how the commit math works,
and how a partner enrolls a customer through the API.

{_supplement_block("3YC (3-Year Commit)")}
**Teaching flow:**

1. Ground it in docs. `search_vipmp_docs` with
   `query="three year commit 3YC"` — pull the overview page and any
   API-specific pages.
2. Business basics first:
   - What a 3YC is from the customer's perspective (pricing lock,
     commitment, anniversary date)
   - Who's eligible (segments, regions, licensing model cutoffs)
   - What the minimum commit quantity is, and per what unit
3. The math:
   - What "commit" actually means — minimum annual consumption?
     cumulative? per product?
   - How true-up / anniversary reconciliation works
   - What happens if the customer under-consumes
4. The API flow. `describe_vipmp_endpoint` for the 3YC-related
   endpoints; walk through a realistic enrollment from scratch.
5. `list_vipmp_error_codes` with `query="3yc"` — flag the ones a
   partner integration really needs to handle.
6. Close with a worked example: a hypothetical customer considering
   3YC with quantity X — would they qualify, is X below any floor,
   what's the year-1 vs year-3 pricing picture.

Quote documented limits verbatim — don't paraphrase numbers.
"""

    @mcp.prompt()
    def learn_subscriptions_and_renewals() -> str:
        """
        Walkthrough: subscriptions and renewals. Covers cotermination,
        auto-renew, proration for mid-term changes, and the API surface
        that makes it all go.
        """
        return f"""Teach me how VIPMP subscriptions and renewals work
— cotermination, auto-renew behaviour, proration for mid-term changes,
and the API surface underneath all of it.

{_supplement_block("Subscriptions and renewals")}
**Teaching flow:**

1. Adobe's docs first. `search_vipmp_docs` with
   `query="subscription"`, `query="renewal"`, `query="coterm"` —
   fetch the top hits via `get_vipmp_page`.
2. Cover the core concepts:
   - What a subscription is in VIPMP's model (per-product? per-offer?
     per-customer?) and how it relates to orders
   - Cotermination: what it means, why Adobe uses it, what
     anniversary date a new subscription lands on
   - Auto-renew: the default behaviour, what the partner controls,
     what happens if it's disabled
3. Proration and mid-term changes:
   - Adding seats vs upgrading tier — which endpoints, which bodies
   - How Adobe prorates charges, in rough terms
   - When a change creates a new subscription vs modifies the
     existing one
4. The renewal window itself:
   - How early renewals are represented in the API
   - What "renewal" actions are available pre-window vs in-window vs
     post-anniversary
5. `describe_vipmp_endpoint` for the two or three most important
   subscription endpoints. Show request + expected response.
6. `list_vipmp_error_codes` with `query="subscription"` and
   `query="renewal"` — flag the ones that come up during renewal
   windows specifically.
7. End with: "walk me through what the API calls look like if a
   customer wants to add 5 more seats to an active subscription 3
   months in." Let the learner attempt it.

Be explicit about where Adobe's docs paper over commercial nuance —
those are exactly the spots the SWO supplement will eventually fill.
"""

    @mcp.prompt()
    def learn_returns_and_refunds() -> str:
        """
        Walkthrough: returns and refunds. Covers the return window,
        what qualifies as a return vs cancellation vs downgrade,
        refund mechanics, and the API sequence for each.
        """
        return f"""Teach me how returns and refunds work in VIPMP —
the commercial rules (return windows, what qualifies, who gets
refunded) and the API sequence that implements them.

{_supplement_block("Returns and refunds")}
**Teaching flow:**

1. Adobe's docs. `search_vipmp_docs` with `query="return"` and
   `query="refund"`; `get_vipmp_page` on the strongest hits.
2. Clarify terminology upfront — in VIPMP, "return" vs "cancellation"
   vs "downgrade" have specific meanings. Get them straight before
   anything else.
3. The return window:
   - How long it is, measured from what event
   - What does and doesn't qualify (fully consumed? partial
     refund? invoiced yet?)
   - Whether the partner initiates or the customer
4. Refund mechanics:
   - Who processes the refund and on what timeline
   - Currency and rate quirks (if Adobe documents any)
   - When a refund is credit vs cash
5. API sequence for a return:
   - Which endpoint, which body, which response shape
   - `describe_vipmp_endpoint` for the return-related call
   - Expected status-code transitions after the call
6. `list_vipmp_error_codes` with `query="return"` — classify: past
   window, already invoiced, already consumed, etc. Each tells the
   partner something different about what to do next.
7. Close with one or two edge scenarios a real operator hits — e.g.
   partial return of a multi-seat order, or a return that crosses a
   renewal boundary. Walk through the decision.

If Adobe's docs are thin on refund mechanics (they often are — it's
partly a commercial process, not an API one), say so explicitly.
"""

    @mcp.prompt()
    def learn_auth_and_sandbox() -> str:
        """
        Walkthrough: authentication, IMS credentials, and safe use of
        the Adobe VIPMP sandbox. Covers what a partner actually needs
        to start making API calls without breaking production.
        """
        return f"""Teach me how authentication works against the VIPMP
API and how to use the sandbox safely. I want to make my first call
without accidentally touching production data.

{_supplement_block("Auth and sandbox")}
**Teaching flow:**

1. Start with the docs. `search_vipmp_docs` with
   `query="authentication"` and `query="sandbox"` — `get_vipmp_page`
   on the identity and sandbox pages.
2. Authentication model:
   - Adobe uses OAuth via IMS (Identity Management Services).
     Explain the relationship between the IMS Organization, the
     partner, and the service account.
   - Walk through getting an access token end-to-end: what
     credentials are needed, how the token is exchanged, token
     lifetime and refresh.
3. Environments:
   - Production vs sandbox URLs and what distinguishes them
   - Whether credentials are shared or separate
   - What state exists in sandbox (test customers? shared? reset
     when?) — if Adobe's docs don't say, say so.
4. First safe call: suggest a read-only endpoint the learner can
   hit in sandbox to confirm auth works before doing anything with
   side effects. `describe_vipmp_endpoint` for it.
5. Common auth errors: `list_vipmp_error_codes` with
   `query="authentication"` and `query="token"` — explain what each
   actually indicates.
6. Operational guidance — when to call Adobe support vs SWO's
   platform team vs check the docs again. Lean on the SWO
   supplement above if it has content; otherwise note the gap.
7. End with: "describe the minimum you need in place — credentials,
   env vars, code — to call one endpoint against sandbox." Let the
   learner list it; correct as needed.

Emphasise that the sandbox is the right place to experiment. Every
learner should feel comfortable making calls there before touching
production.
"""
