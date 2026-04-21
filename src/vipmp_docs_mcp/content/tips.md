# VIPMP Tips

Human-authored operational tips that complement Adobe's published API
docs. Surfaced through the `get_vipmp_tips(topic)` MCP tool when a user
explicitly asks for tips on a topic.

Adobe's documentation is a strong API reference but a shallow training
resource. It tells you *what* an endpoint does; it rarely tells you
*why* the rule exists, when it matters in practice, what breaks in
production, or how the commercial side of SoftwareOne's business
interprets it. This file captures that tribal knowledge so it's
accessible from an MCP client as SWO-specific context, separate from
Adobe's official docs (which the `learn_*` walkthroughs cover).

## How this file is used

Each `## H2` below is a topic. When a user asks the assistant for tips
on a topic (e.g. *"give me tips on the customer lifecycle"*), the
assistant calls `get_vipmp_tips("Customer lifecycle")` which returns
the matching section verbatim. The `learn_*` walkthrough prompts do
NOT pull from this file — they stay grounded in Adobe's live docs so
walkthroughs are citable. Tips are where SWO-contributed content lives.

## How to contribute

- Short bullet points beat long prose. Learners skim.
- Prefer concrete examples ("if the customer is LGA and picks
  coterm = 23 months, 1118 fires because...") over abstract rules.
- Call out gotchas explicitly with a **Gotcha:** prefix so the
  assistant can weight them appropriately.
- Note when a rule is SWO-operational (how we run the business) vs
  Adobe-commercial (how the program itself works). Both are useful.
- Dated entries ("as of 2026-Q1, sandbox latency can spike to ~8s
  around the 15th") beat undated ones — commercial rules drift.
- It's fine to leave a section empty. TODOs are visible and trackable.

---

## Customer lifecycle

### `globalSalesEnabled` — creating a customer outside the distributor's region

- Boolean flag on `POST /v3/customers`. When `true`, the customer's address
  can be in a country the distributor doesn't normally cover.
- **Normal rule:** the customer's country must fall within the distributor's
  geographic region. Creation fails otherwise.
- **What `globalSalesEnabled: true` does:** waives that geographic check.
  Adobe-commercial — the flag is part of the API contract, not an SWO
  convention.
- **Segment:** Commercial (COM) only. EDU and GOV customers can't use it.
- **Example.** A customer registered in Morocco can be created under a
  United States distributor. Without the flag, the same request is
  rejected.
- **Mutability:**
  - **Enabling** (`false` → `true`): unrestricted. Toggle anytime via the
    Update Customer API.
  - **Disabling** (`true` → `false`): only while the customer has no active
    subscriptions in deployment locations created under the customer. See
    the Deployments API for how deployment locations relate to subscription
    geography.
- **Gotcha:** don't default to `true`. The geographic rule exists for tax
  and compliance reasons; waiving it needs a real commercial justification
  (multinational master agreement, subsidiary billing consolidation, etc.).
  Confirm with the deal owner before setting it.

---

_More topics to capture in this section (TODO):_

- _What does "active" vs "pending" vs "suspended" mean commercially?_
- _Typical SWO flow when onboarding a new reseller's first customer._
- _Which lifecycle transitions are one-way, and which are reversible?_
- _Common mistakes when creating a customer (MEA flag, 3YC flag, LGA markets)._

## Ordering flow

_TODO. Worth capturing here:_

- _Commercial meaning of order status transitions._
- _When a "successful" API response does NOT mean the order is live._
- _How SWO handles partial failures and out-of-band reconciliation._
- _Real-world ordering gotchas (pricing refresh windows, market-specific timing)._

## 3YC (3-Year Commit)

_TODO. Worth capturing here:_

- _Eligibility rules beyond what the API enforces._
- _How commit quantity math works and what happens at true-up._
- _When mid-term upgrades are free vs require a new commit._
- _Commercial impact of under-consumption._

## Subscriptions and renewals

_TODO. Worth capturing here:_

- _Cotermination semantics and why Adobe's dates can look surprising._
- _Auto-renew default behaviour vs what SWO configures._
- _Proration rules for mid-term changes (add seats, upgrade tier)._
- _What to check before a renewal window closes._

## Returns and refunds

_TODO. Worth capturing here:_

- _The return window from a SWO commercial standpoint._
- _Which changes qualify as returns vs cancellations vs downgrades._
- _Refund mechanics — who initiates, how long it takes, currency quirks._
- _Common reasons a return fails (past window, already invoiced, etc.)._

## Auth and sandbox

_TODO. Worth capturing here:_

- _How SWO's IMS Organization is structured (prod vs sandbox)._
- _What credentials you actually need and where to get them._
- _Safe vs unsafe experiments in sandbox (what resets, what doesn't)._
- _When to call Adobe support vs SWO platform team._
