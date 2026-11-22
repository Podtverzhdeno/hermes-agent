# Hermes Skills — host-enforced execution harness (architecture decision proposal)

**Status:** PROPOSED, NOT IMPLEMENTED.  
**Repository anchor:** Podtverzhdeno/hermes-agent, audited 2026-11-22.  
**Applies to:** local CLI, gateway sessions, MCP tools, terminal, browser,
connector API calls, delegates/subagents and resumed tasks.  
**Ownership:** security/agent runtime, not individual Skill authors.

## 1. Verified boundary today

- \`agent/skill_harness.py\` validates small declarative \`harness.yaml\` contracts.
  It explicitly returns \`enforcement: advisory_only\`. The declared
  \`capabilities.tools\` and \`approval_required\` are prose, not ACLs.
- \`agent/prompt_builder.py\` uses a bounded first positive/negative route hint
  to help selection. \`tools/skills_tool.py\` loads procedures, validates
  manifests and caps reference bytes on skill view.
- \`tools/registry.py::ToolRegistry.dispatch\` dispatches a registered handler
  without checking active Skill identity, capability grants or operation scope.
- \`tools/approval.py::check_all_command_guards\` guards terminal commands
  separately. Its current behavior explicitly allows some container
  environments, \`HERMES_YOLO_MODE\`/approvals.mode=off and certain noninteractive
  flows. This is **not** a security boundary for data/tool scope.
- A negative activation hint has no power to stop direct tool calls.
- The 74 hand-authored routing fixtures do not execute an agent or measure
  behavior. The corpus source scanner detects patterns, not vulnerabilities.

**Consequence:** the current 31 individual harnesses improve selection,
procedures and static QA, but must not be advertised as sandboxing,
least-privilege runtime enforcement, or a defense against a malicious Skill.

## 2. Objectives, invariants and non-goals

We need meaningful, measurable scope for **each** activated Skill:
resource restrictions, side effects, operation approval, budgets,
read-back evidence, safe retries, multi-agent delegation and revocation.
Invariant: **Skill content can ask for capabilities but cannot grant them**.

Core equations:

\`\`\`text
effective_grants = intersect(
    host_platform_policy,
    organization_policy,
    authenticated_user_grants,
    connector_principal_permissions,
    active_skill_scoped_permissions,
    session_and_delegation_limits
)
decision = allow only if:
    known_operation
    AND verified_identity
    AND target_within_granted_scope
    AND action_within_granted_effects
    AND valid_unexpired_approval_if_required
    AND atomic_budget_reservation_succeeds
\`\`\`

Unknown or unavailable control data => deny in enforcement mode. Error messages
must not reveal secrets or broad allowlists. Neither instructions in
SKILL.md nor tool-returned strings may mutate any host policy.

Non-goals for v1: solving all prompt injection; automatically sandboxing shell;
silently migrating existing user auth; guaranteeing third-party API idempotency;
treating an LLM "confidence" score as authority.

## 3. Trusted objects and provenance

Define a **host-owned** \`SkillExecutionContext\`, never chosen by LLM args:

\`\`\`python
@dataclass(frozen=True)
class SkillExecutionContext:
    invocation_id: str
    session_id: str
    principal_id: str
    skill_name: str
    skill_version: str
    skill_content_sha256: str
    harness_sha256: str
    origin: str  # signed/approved source identity, not a URL claim
    parent_invocation_id: str | None
    granted_operations: frozenset[str]
    allowed_resources: tuple[ResourceScope, ...]
    approval_receipts: tuple[str, ...]
    max_tool_calls: int
    max_cost_micro_usd: int | None
    deadline_monotonic: float
    policy_version: str
\`\`\`

The *context* is immutable, but budgets/revocations live in a host-owned,
atomic per-invocation counter. A unique ID or digest alone is not authority.
Bind approvals to principal, skill content digest, operation, canonical
resource ID, target account, amount/limits, expiry and a single-use or
explicitly repeatable semantic. On restart, reload from an authenticated
host store, never a serialized model message.

When Skill or harness bytes change after admission, invalidate approval and
require a new admission. Reject symlink replacement, ambiguous duplicate
skill names, untrusted source changes and provenance mismatch.

## 4. Capability catalog (machine-meaningful, not tool-name prose)

Each *registered tool adapter* declares externally maintained operation
metadata. A handler cannot self-certify as harmless based on a remote MCP
annotation. Minimum taxonomy:

| Effect | Examples | Default in protected scopes |
|---|---|---|
| \`read_public\` | search public repo or model card | narrow grant |
| \`read_private\` | vault note, email, private issue | explicit resource principal |
| \`local_write\` | edit approved repo file | ownership/path constraint |
| \`external_write\` | issue comment, Notion mutation | exact target/action approval |
| \`upload\` | PDF/image/model/CSV transfer | source classification + target approval |
| \`install_exec\` | pip/npx, scripts, extension | isolated environment and separate approval |
| \`delete\` | remove repo or remote records | confirmed irreversible target |
| \`credential_access\` | OAuth/token use | managed principal; never raw token return |
| \`paid_operation\` | video/LLM job/monitor | price cap + no duplicate-submit |
| \`network_listener\` | MCP HTTP bind | interface, port, auth and lifetime scope |
| \`delegate\` | child-agent invocation | subset-only grants and budgets |

A single tool may offer several effects depending on validated arguments.
For example, an MCP tool listing is **not** the same effect as
\`mcp.call\` targeting an unknown remote write; a terminal tool is an opaque
program runner, not a safe read even if the command starts with "cat".

A remote MCP tool annotation is a hint only. No annotation => unknown
effect => manual classification or deny in enforcement mode.

## 5. Dispatch integration design

All action paths must share the same decision point; do not only
instrument \`ToolRegistry.dispatch\`.

\`\`\`text
skill_view() -> validate / snapshot / admit
                     |
                     v
           host-created execution context
                     |
          [LLM suggests tool name+args]
                     |
                     v
         canonicalize args + resolve target
                     |
       policy.check(context, tool, effect)
         |              |
        deny        atomically reserve budget
         |              |
    redacted error      approval if needed
                        |
                  provider/tool invoke
                        |
                receipt + redacted trace
                        |
                  verify/read-back
                        |
                  charge/release budget
\`\`\`

Entry points to inventory before enabling enforcement:
- \`tools/registry.py::dispatch\`
- \`model_tools.py\` sync/async handlers and any direct map bypasses
- \`tools/terminal_tool.py\`, \`tools/code_execution_tool.py\`
- \`tools/mcp_tool.py\` dynamic discovery/calls and OAuth
- browser/web tools, file write tools, external connectors and provider SDKs
- \`tools/delegate_tool.py\` and resumed/parallel agent entrypoints
- gateway queue/replay, CLI approvals and scheduled/background tasks

Adapter-level enforcement must mediate tools invoking further tools.
For terminal/code execution, a Python dispatcher check cannot contain
arbitrary subprocess, filesystem or network behavior; enforce a restricted
container/OS principal and egress policy in addition to admission. Keep
current unsafe shell/YOLO modes **outside** protected Skill scopes by policy,
not by changing global flags silently.

## 6. Approval, budgets, replay and result semantics

Represent an action in three parts:
\`(resource_identity, canonical_operation, normalized_arguments_digest)\`.
The principal authorizes that exact intent, not a textual regex pattern.
Bulk operations require either a reviewed explicit allowlist or an
independently enforced constraint and limit.

Use monotonic deadlines and atomic counters covering parallel/reentrant
calls, including child agents. A budget denial never authorizes borrowing
from a sibling or unrelated session. Limit tool call count, bytes read,
bytes uploaded, money, elapsed walltime, concurrency and rate.

For external side effects use durable operation IDs and store:
\`queued / submitted / applied / verified / failed / uncertain\`.
On timeout query target state first. Only automatically retry
idempotent operations or provider-supported idempotency keys; otherwise
stop as \`uncertain\` and surface reconciliation instructions.
A bare HTTP 2xx or LLM assertion does not equal verified success.

For provider failures, a missing read-back receipt remains explicitly
unverified, never silently upgraded to success.

## 7. Delegation and revocation

Child context =
\`parent context ∩ requested child scope ∩ organization/platform grants\`.
Delegated call must bind parent identity, immutable Skill digests and
resource ownership. Cross-agent messages and shared Obsidian Markdown are
data, not policy updates. When a parent loses authorization, descendants
lose it atomically, including running callbacks before their next effect.

Define stable ownership of source files and narrow mutable resources.
Use version/ETag/CAS checks for repository writes, and descriptor-based
filesystem access where available. Optimistic SHA checks alone are
insufficient against a concurrent symlink or target replacement.

## 8. Failure-injection and attack test matrix

All required before claiming "enforced":

1. malicious SKILL.md asks for new tool permission => denied
2. changed harness SHA after approval => denied + re-admission
3. malicious MCP tool description claims "readOnly" while invoking write
4. GitHub issue body requests reading credential files => no secret access
5. private PDF requests covert upload via OCR fallback => no upload
6. Notion post/update is duplicated by timeout => one mutation or uncertain
7. Xitter client attempts to reuse Hermes shared .env => denied
8. FastMCP file root symlink swap and concurrent replacement => sandboxed
9. hosted tool call bypasses registry entrypoint => common guard catches
10. tool served by different GitHub account than approved => denied
11. direct terminal invocation / subprocess helper bypass => contained
12. user approval expires during a long-running call => no new effects
13. child agent asks for parent-private file outside delegated scope => denied
14. gateway resume/replay with stale token or new args => denied
15. budget exceeded during parallel tool calls => atomic refusal
16. prompt-injection across skill references, OCR pages and web output
17. disable-approval/Yolo setting under protected context => not a bypass
18. missing provider read-back => output status \`unverified\`, never success

Test on Windows native, Linux and supported macOS; include actual tools,
CLI/gateway, concurrency, process crashes and provider emulators. Fakes
can prove local logic but never prove an external account's real state.

## 9. Rollout and measurable release criteria

**Phase A — observation:** add immutable execution IDs, typed effect
classification, redacted audit receipts and zero-authority dry-run
decisions. Compare with existing session behavior and collect bypass cases.

**Phase B — protected fifteen:** enable per-call enforcement first for
fifteen newly hardened high-impact Skills (Github Issues, mcporter,
OCR/Documents, FastMCP, Notion, Hugging Face Hub, Xitter, inference.sh,
Parallel, 1Password, Himalaya, Webhook Subscriptions, AgentMail,
Find My and iMessage). Require manual review for ambiguous effects, no broad "allow all"
fallback.

**Phase C — remaining pilot 22:** add compatible effect adapters; verify
parent/child and gateway semantics. Only then change default enforcement.

**Phase D — remaining 86:** inventory, audit, design individualized
capability scopes; no mass-copied policy.

Quality gates:
- Zero unauthorized external writes/secret reads in attack-suite runs.
- Zero silent credential/account scope expansions.
- Every write has canonical receipt or explicit uncertain state.
- Task completion rate, routing precision/recall, false denials, cost, tool
  count, tail latency and human override rate measured on paired runs.
- Compare no-skill, manually selected skill, and automatically selected skill
  baseline with pinned model/tool versions and a sealed holdout set.
- A green YAML/pytest CI alone is insufficient for these gates.

## 10. Priority risks and decision

**P0**: no real dispatcher enforcement; terminal/containers/YOLO and gateway
entrypoints require a unified decision boundary.  
**P0**: untrusted tool and Skill text can induce actions despite good YAML.  
**P1**: external writes may duplicate on ambiguous retries.  
**P1**: OS-level isolation missing for attacker-controlled local files.  
**P1**: real model task-success, cost and error rates not yet measured.  
**P2**: missing per-Skill contracts for 86 Skills.

Decision: retain existing v1 \`harness.yaml\` as **advisory metadata only**.
Create host-owned, opt-in enforcement after an explicit inventory of *all*
execution paths; reject a superficial "policy interceptor" that covers
only registry dispatch. Production promotion requires receipts, negative
tests and actual baseline-to-candidate model task evaluations.

## Sources (primary specifications and project code)

- Agents Skills progressive disclosure: https://agentskills.io/specification
- MCP tools and annotation trust: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- OWASP Agentic Skills Top 10: https://owasp.github.io/www-project-agentic-skills-top-10/
- OpenAI Agents guardrails and tool approvals:
  https://developers.openai.com/api/docs/guides/agents/guardrails-approvals
- Hermes fork: \`agent/skill_harness.py\`, \`tools/registry.py\`,
  \`tools/approval.py\`, \`agent/prompt_builder.py\`, \`tools/skills_tool.py\`

## 11. Additional verified gateway and secrets risks

The 2026-11-22 code inspection identified a second implementation boundary:
`gateway/platforms/webhook.py` uses `DEFAULT_HOST = '0.0.0.0'` and
supports a special `INSECURE_NO_AUTH` configuration for testing.
Although the Skill guide now recommends loopback and signed events,
nothing in `harness.yaml` overrides the gateway process's actual defaults.
Before enabling webhooks under protected scopes, require explicit user
confirmation of bind interface, validate public exposure, block insecure
test mode in production and verify anti-replay retention after restart.

Likewise `optional-skills/security/1password/SKILL.md` cannot by itself
prevent `op read` from printing secrets. OS/process isolation and host
tool-result redaction are required; suppressing a sample in Markdown
is procedure improvement rather than enforced confidentiality.

## 12. Private communication and location boundary

The bundled AgentMail Skill previously proposed storing its API key in
plaintext MCP config while running unpinned `npx -y`; this is not a safe
automatic bootstrap. The revised Skill separates account setup, package
install, inbox creation and actual SMTP-like send authority. The host still
must enforce token injection, recipient scope and retry idempotency.

Find My uses screenshot/vision automation and can expose third-party
locations; local screenshot creation is a privacy-impacting side effect.
Bounded use, strict file scope, no unintended network upload and
explicit monitoring expiration must be enforced beyond the guide.

iMessage may send SMS when requested iMessage is unavailable. Provider
service selection, recipient canonicalization, message content and
attachment identity must be part of the approval receipt; otherwise
an 'approved send' can target the wrong transport or person.
