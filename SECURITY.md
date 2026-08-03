# Security Policy

## Supported versions

Only the latest released version receives security fixes. This project follows a
rolling release model — there are no long-term support branches.

| Version | Supported |
| ------- | --------- |
| Latest release | Yes |
| Anything older | No — upgrade first |

## Reporting a vulnerability

Please report privately through GitHub rather than in a public issue:

**[Open a private security advisory](https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/security/advisories/new)**

This project is maintained by one person, so please allow around a week for an
acknowledgement and a couple of weeks for a full assessment. Valid reports will
get a fix and a published advisory crediting you. If a report turns out not to
be applicable, you will get a written explanation of why.

Please get in touch before publishing. If something looks urgent and you have
not heard back, a nudge is welcome.

## What a report should include

The more of this you can provide, the faster it can be assessed:

- The version affected (`pip show vipmp-docs-mcp`), and the tool or prompt name.
- Exact arguments that trigger it.
- Observed behaviour versus expected behaviour.
- For anything involving network traffic: a captured request or packet trace
  showing the destination host. Timing measurements on their own are hard to act
  on — the threat model below explains why.

Reports without a reproducer are still worth sending, but they may take longer
to work through, and some cannot be confirmed either way.

## Threat model

This is a local, read-only documentation server. It runs over stdio under an MCP
client on the operator's own machine. It has no listening socket, no
authentication surface, no credential store, and no write path outside its own
cache directory. The operator and the caller are the same party.

That shape determines what counts as a vulnerability here.

### In scope

- Any outbound request to a host other than `developer.adobe.com` (documentation
  fetches) or `raw.githubusercontent.com` (the optional remote index).
- Any filesystem read or write outside the documented cache directory, including
  path traversal via a tool argument.
- Arbitrary code execution, deserialisation flaws, or dependency confusion.
- Cache poisoning that causes fabricated documentation to be served as genuine.
- Secrets or local file contents leaking into tool output.

### Out of scope

The following are intended behaviour rather than defects:

- **Prompt arguments appearing in prompt output.** `review_request_body`,
  `debug_error_code`, and the other `@mcp.prompt()` handlers are templates. They
  interpolate arguments the operator supplies into a message sent to the
  operator's own model. There is no trust boundary between the two, and a
  template that omitted its arguments would have no function. These are prompts
  rather than tools, so they are not returned by `tools/list`.
- **Outbound HTTP to `developer.adobe.com`.** Tools that may fetch on a cache
  miss are declared `openWorldHint=True` for this reason. Response latency
  therefore varies with cache state, which can resemble a timing side channel.
  It does not indicate a request to any other host: the base URL is a module
  constant in `fetcher.py` with no environment, configuration, or parameter
  override.
- **Documentation content influencing the model.** Page text is fetched from
  Adobe and returned to the caller's LLM. Trusting Adobe's documentation site is
  inherent to what this server does. A compromise of that site would be a real
  risk, but it is not something this project can fix.
- **Denial of service against the local process.** The operator controls their
  own client and can restart it.

If you think something in this list deserves reconsidering for a deployment
model I have not anticipated, please say so — the boundaries above describe the
server as it is used today, not a refusal to look again.

## A note on automated scanners

Scanner output is a reasonable starting point and is welcome. Because this
server is an unusual shape, two patterns tend to produce findings that do not
hold up: reading `prompts/list` as though the entries were tools, and inferring
SSRF from response timing when the server has a documented upstream it is
expected to fetch from. Checking a finding against the source before reporting
saves time on both sides.
