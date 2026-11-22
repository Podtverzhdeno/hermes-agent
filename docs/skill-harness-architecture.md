# Hermes skill harness v1 — contracts, threat model and rollout

Status: **experimental pilot, not a runtime sandbox**. Branch-scoped design.
Repository baseline reviewed: fork HEAD 7e9100901819ee44c16b4ddcb79a6bcb7909f591
(2026-04-01); upstream had moved significantly by 2026-11-22. Rebase and
conflict assessment are mandatory before proposing an upstream merge.

## Scope and principle

A **skill** is domain knowledge and a procedural playbook in SKILL.md.
A **harness** is the execution framework around selection, preflight,
capabilities, evidence, verification, recovery and reporting. Do not conflate
them. A Markdown promise never substitutes for a host-side permission check.

This pilot provides:

1. An optional, **individual** harness.yaml next to SKILL.md;
2. Strict parse/type/shape checks in agent/skill_harness.py;
3. Surfacing the validated manifest in skill_view() responses;
4. A lookup-name/path guard and safer symlink boundaries for the skill reader
   and skill manager;
5. Twenty-seven individually scoped manifests for selected high-risk/high-value skills;
6. A repository-wide inventory auditor (117 SKILL.md at baseline) and targeted tests;
7. A validated skill_manage(write_harness) action with optimistic SHA-256 read-back;
8. An enforced size ceiling for linked references viewed under a harness;
9. Fail-closed agent-created skill scanning on denied, unresolved or missing scanners.

All older skills remain loadable without a manifest. Their response reports
harness_status=legacy and harness=null. Invalid existing manifests fail closed
at skill_view(). Neither status changes the core tool authorization model.

## Deliberate limitation: no enforcement yet

`capabilities.tools`, `side_effects`, approval conditions, tool-call budgets and
lifecycle stages are **advisory metadata**. They are returned to the model,
but the tool dispatcher does NOT currently enforce them. The one implemented
budget boundary is `max_reference_bytes` for skill_view(file_path=...) on a
skill that declares a harness. Legacy skills retain their historical behavior. Do not market this
as sandboxing, guaranteed approvals, timeout isolation or automatic rollback.
Existing Hermes host-level permissions still determine what is permitted.

Do not inject manifests into the system prompt on every tool call. Hermes
relies on stable prompts and caching; full manifests are loaded only when
the model requests an actual skill.

## Manifest format (version 1)

```yaml
schema_version: 1
skill: example
activation:
  when: ["Actual task needing this procedure"]
  not_when: ["Adjacent task better served elsewhere"]
capabilities:
  tools: ["read_file", "terminal"]
  side_effects: none  # none | local_write | external_write
  approval_required: []
lifecycle:
  preflight: ["Confirm repository and revision"]
  execute: ["Inspect the relevant changed code"]
  verify: ["Check each finding against a concrete scenario"]
  recover: ["Report blockers without inventing results"]
budget:
  max_tool_calls: 20
  max_reference_bytes: 32768
evidence:
  required: ["Revision and file:line evidence"]
output:
  format: "Verified review findings"
  acceptance: ["No unsupported blocker assertions"]
```

The validator rejects unknown keys, malformed structures, missing lifecycle
steps, oversized manifests (>32 KiB), false-positive bool-as-int budgets,
contradictory activation conditions, and external writes with no declared
approval conditions. A manifest must match the SKILL.md name. A symlinked
harness.yaml is rejected.

**This YAML is an extension to the project, not a claim that Agent Skills
requires harness.yaml.** The existing SKILL.md format remains portable.

## Risk-weighted pilot contracts

| Skill | Core risk | Specialized preflight | Proof of completion |
|---|---|---|---|
| code-review | Unsupported findings | revision, context, invariants | line-anchored evidence |
| systematic-debugging | Trial-and-error patches | reproducer and baseline | targeted regression |
| test-driven-development | Unverified change | test seam and isolation | red/green traces |
| subagent-driven-development | Conflicting writes | immutable task ownership | independent review/integration |
| github-pr-workflow | Unauthorized merge/secret exposure | account, branch, base, SHA | verified PR + CI conclusion |
| github-code-review | Stale/false PR comments | PR head and diff | confirmed anchors |
| arxiv | Citation hallucination | identifiers and search scope | versioned source/limitations |
| obsidian | Destructive edits/concurrency | canonical vault + writable subtree | readback and hashes |
| google-workspace | Unrequested external messages | scope/account/resource ID | operation receipt |
| native-mcp | Tool poisoning/overprivilege | server trust and schemas | read-only probe + inventory |
| github-auth | Secret disclosure / wrong identity | scoped identity and safe credential store | redacted auth and read access checks |
| github-repo-management | Irreversible admin changes | owner, branch rules, approval scope | before/after receipt and resource IDs |
| github-issues | Token scraping, duplicate or unauthorized issue writes | account, issue, existing state | read-back of issue URL, labels and comments |
| mcporter | Untrusted MCP tools and surprise writes | server identity, schema, side-effect scope | tool execution and resource receipt |
| ocr-and-documents | Private file exfiltration, incorrect OCR | confidentiality, source/pages and local tooling | page-grounded extraction with uncertainty |
| fastmcp | Vulnerable tool surface or public exposure | protocol, tool permissions, transport | schema tests, valid/invalid calls and cleanup |
| notion | Duplicate writes or wrong resource scope | integration ID, page/data-source and revision | before/after resource read-back |
| pytorch-fsdp | Stale APIs / GPU cost / deadlock | torch version, ranks, baseline, checkpoints | measured per-rank tests and save/load |

These are initial **hypotheses**, not proven quality gains. Compare against
the baseline before expanding. Avoid mass-copying an identical manifest to
all 100+ skills; each needs its own intent, risk profile and acceptance tests.

## Security scanner and durable harness edits

After the pilot, skill_manage(action="write_harness") validates the entire
manifest against the canonical SKILL.md name. Updates require the existing
manifest_sha256 returned by skill_view(), and mutations run the existing
security scanner. This is intended to avoid accidental unreviewed changes;
the underlying security scanner remains a heuristic and can miss attacks.

For approved manifests, skill_view() checks the declared byte ceiling of
linked references before reading them. It returns code=reference_too_large
when the file is too large; this is a real guard, not merely a prose rule.

Inventory at the initial fork revision: **117** Skills (74 bundled + 43
optional), **0** per-skill harness manifests; 44 SKILL.md files were
greater than 10 KiB. This expanded pilot specializes 27 Skills, i.e. about 23%
of baseline inventory. Avoid interpreting coverage as a quality metric.

## Workflow for a hardened v2

1. **Index.** Load only names/descriptions and stable path; record source
   identity, version and content digest. Avoid recursive rescans on each turn.
2. **Route.** Evaluate positive and *negative* triggers; log false activations
   and missed triggers, not merely top-1 ranking.
3. **Admit.** Host computes effective capabilities = intersection of user
   grant, provider scope, platform policy, tool availability and declared
   skill requirements. Skill text is *never* a source of elevated authority.
4. **Prepare.** Pin dependencies; check OS, resource limits, credentials,
   environment, network egress and sandbox availability. Keep secret values
   out of skill content and model-visible traces.
5. **Execute.** Route every tool call through an independent policy decision
   point. Bind approvals to user, skill version, tool name, operation, target,
   scope and expiry; deny cross-skill permission inheritance.
6. **Observe.** Attach operation IDs, sanitized logs, input/output hashes,
   external artifact receipts, latency, tool costs and redacted traces.
7. **Verify.** Compare the result to the skill-specific acceptance contract
   using deterministic checks first and a reviewer only when needed.
8. **Recover.** Reconcile uncertain external writes before retrying. Prefer
   idempotency keys, bounded retries, checkpointed state and reversible
   local work; do not promise rollback of a sent email.
9. **Exit.** Record what is verified, what is assumed, and side effects.
   Revoke ephemeral credentials/leases and release sandbox resources.

Implement this only after baseline evals and dispatcher integration tests.
Host capabilities should not change mid-conversation if that would invalidate
Hermes prompt/tool caching; when necessary, use dedicated child contexts with
fixed tool subsets, checked by the host rather than by model instructions.

## Threat model

Assets: API tokens, user files, email/calendar content, repository branches,
review authority, project memory and execution environments.

Trust boundaries:
- Untrusted SKILL.md from hub or external_dirs vs validated local policy;
- Skill instructions vs tool registry;
- MCP server descriptions and tool results vs user/host instructions;
- Agent read permissions vs write permissions;
- One agent's workspace vs another agent's concurrent edits.

Relevant attacks: instruction injection, malicious dependency install,
credential exfiltration, traversal and symlink escape, arbitrary workspace
mutation, stale-sha writes, duplicate external effects, resource exhaustion,
unsafe implicit account selection and unverifiable completion claims.

### Residual risks in this pilot

- The guard scanner is regex-based; it is not a complete supply-chain
  assessment. Review known false positives and install-confirmation flows.
- Agent-created skill mutation now **fails closed** on scanner "ask", block,
  missing scanner or scanner exception, with rollback attempts. This does not
  prove the scanner is complete: false negatives and TOCTOU remain.
- The new `write_harness` action checks an existing file SHA-256 before overwrite,
  but uses a best-effort compare-and-write, **not** an atomic cross-process CAS.
  Concurrent writers must still serialize or use a host-level file lock.
- Local filesystem containment checks can still have TOCTOU races; full
  mitigation needs descriptor-based filesystem operations, not just resolve().
- External skill roots are currently considered trusted by configuration;
  source provenance and actual execution constraints are distinct.
- Script dependencies and external APIs can evolve beyond SKILL.md examples;
  pin and test in a controlled environment.
- Most legacy skills have no individual harness; no claim of full coverage.

## Evaluation design and release gates

Use paired baseline/candidate runs on identical tasks and fixed inputs.
Each domain suite must have positive triggers, tempting negative triggers,
normal cases, ambiguous cases, error paths, and an adversarial tool-output
case. Include multiple OS/provider surfaces where relevant. Collect actual
traces and output artifacts, not self-assessed scores.

Primary metrics:
- Activation precision/recall, false-positive skill invocation;
- Task success and severity-weighted correctness;
- Evidence fidelity (does a cited file/line/paper actually support a claim?);
- Unauthorized side effects and credential leakage (**zero tolerance**);
- Recovery behavior on timeouts, conflicts and duplicated operations;
- Tool calls, tokens, wall time, external cost and failure rate;
- Regression rate on legacy skills and baseline workloads.

Suggested graduation gate (proposal, not yet measured):
- 0 unauthorized side effects and 0 confirmed secret disclosures on suite;
- 100% of schema/path/approval negative tests passing;
- No statistically meaningful regression on task success vs baseline;
- No deterioration of activation precision on adjacent-skill negatives;
- Exact results disclosed per platform and provider, with a holdout set.

A hard fail in authorization or data isolation blocks release regardless
of any weighted quality score. Do not report "10/10" based only on tests of
parser schemas; domain accuracy requires running the tasks.

## Commands

```bash
python -m scripts.audit_skill_harness --strict
python -m scripts.audit_skill_harness --json
python -m pytest tests/agent/test_skill_harness.py \
  tests/tools/test_skill_harness_integration.py \
  tests/tools/test_skill_manager_path_boundaries.py \
  tests/tools/test_skill_manager_guard_fail_closed.py \
  tests/tools/test_skill_manager_write_harness.py \
  tests/skills/test_pytorch_fsdp_archives.py -q
# Before merge:
python -m pytest tests/ -q
```

## Research references

- Agent Skills specification: https://agentskills.io/specification
- Client implementation / progressive disclosure:
  https://agentskills.io/client-implementation/adding-skills-support
- OpenAI, "Testing Agent Skills Systematically with Evals":
  https://developers.openai.com/blog/eval-skills
- OpenAI, "Shell + Skills + Compaction":
  https://developers.openai.com/blog/skills-shell-tips
- OWASP AI Agent Security Cheat Sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
- OWASP Agentic Skills Top 10:
  https://owasp.github.io/www-project-agentic-skills-top-10/

## Corrective hardening pass — 2026-11-22

The initial 22-manifest pilot had **10 broken activation exclusions**:
`activation.not_when: undefined` is not a list and caused validation to fail
closed for those Skills. This was a functionality regression, not just missing
metadata. The corrective commit replaces each placeholder with two domain-
specific negative routing examples and adds catalog tests that reject such
placeholder exclusions for every manifest.

Five additional per-Skill contracts now cover `github-issues`, `mcporter`,
`ocr-and-documents`, `fastmcp`, and `notion`. The issue Skill no longer
extracts GitHub credentials from local secrets; it uses an existing GitHub
provider or authenticated `gh` session. The PDF Skill now treats remote
conversion of private content as a separate, explicitly authorized operation,
and recognizes that PyMuPDF can optionally OCR through Tesseract.

This still does **not** grant manifest-declared capabilities, perform domain
task evaluations, prevent all TOCTOU races, or demonstrate runtime isolation.
An individual harness is a **contract**, not a security boundary. Validate
the full skills corpus on each change; the tests and source audit are evidence
of schema and content integrity, not model performance.

### Additional verification references

- GitHub CLI issue documentation: https://cli.github.com/manual/gh_issue_edit
- PyMuPDF OCR: https://pymupdf.readthedocs.io/en/latest/ocr/index.html
- MCP guidance on annotation trust: https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/
- OWASP Agentic Skills Top 10: https://owasp.github.io/www-project-agentic-skills-top-10/

### Suggested next engineering layer (not implemented here)

1. Add host-side `SkillExecutionContext` with immutable skill identity, content
   digest, grants, resource scopes, tool budgets and structured operation IDs.
2. Enforce every tool invocation at the central dispatcher using a scoped policy
   decision point; never accept capability annotations as authority.
3. Add skill-specific paired baseline/candidate eval cases with seeded
   fixtures, adversarial content and read-back receipts. Report task success,
   cost, activation precision and safety regressions separately.
4. For cross-process filesystem modifications, replace optimistic SHA checks
   with atomic compare-and-swap or descriptor-based operations.
5. Keep each Skill's versioned reference documentation current; re-verify
   technical APIs and examples before promotion to production.

### Routing evaluation corpus v2 (static fixtures, **not** observed runs)

The hand-authored corpus now has 27 normal task prompts, 27 **genuine**
adjacent-skill exclusion prompts, and eight injected-content scenarios.
Previously the negative prompts accidentally described **positive** cases
for their forbidden Skill, while the positive prompts were merely Skill names.
Those fixtures would punish correct routing and overstate activation quality.

The scorer now checks a declared expected *alternative* on hard negatives
where provided, not merely that the forbidden Skill was avoided.
It still needs trusted agent traces and does **not** execute a model.
The matching static tests guard only data integrity and scoring semantics.

Metrics from this dataset are intentionally **unreported** until baseline
and candidate runs are captured with the same prompt, model, harness,
tool registry and resource state. Future corpus expansions should add
paraphrases, ambiguity, mixed requests, partial tool errors and multiple
languages, then keep a sealed holdout set.

### Second-pass domain hardening — 2026-11-22

Individual harness manifests are not sufficient when the corresponding SKILL.md
contains obsolete API calls or unsafe runtime defaults. The GitHub Issues,
PDF/OCR, Notion, mcporter and FastMCP procedures were audited individually.

Notion: corrected the 2025-09-03 database/data-source distinction, switched
row creation to the selected data_source_id, switched database creation to
POST /v1/databases with initial_data_source.properties, and documented
2026-03-11 as a newer version with breaking field changes. The former
2025-09-03 latest-version claim and wrong creation endpoint were defects.

mcporter: npx can fetch and execute remote packages; discovered server
entries and tool descriptions are not trust grants. Configuration, OAuth,
remote writes and stdio launches need explicit authority. Errors after a
non-idempotent tool call must be reconciled before retry.

FastMCP: use an authorized isolated environment; do not register clients or
deploy HTTP servers by default. The bundled file processor formerly allowed
unbounded reads from arbitrary absolute paths. It now requires explicit
MCP_FILE_ROOT, rejects traversal/absolute/symlink paths, bounds bytes and
previews, and refuses unknown/oversized inputs. The real helper is exercised
by tests with a stub FastMCP host; this does not require provider credentials.

**Residual risk:** Python path checks are not a full OS security boundary
and cannot remove all filesystem TOCTOU races. A hostile shared directory
also requires process and OS-level isolation. Source-level tests do not
demonstrate actual domain success against remote APIs.

Primary references:
- https://developers.notion.com/docs/upgrade-guide-2025-09-03
- https://developers.notion.com/docs/upgrade-guide-2026-03-11
- https://mcporter.sh/install.html
- https://blog.gofastmcp.com/3mufbh2vcv22o

### Whole-catalog risk-guided expansion — 2026-11-22

A new scanner traverses every SKILL.md and reports only path, line and rule,
without exposing matched instructions or credentials. The first real run
found 166 heuristic observations across 117 Skills, of which six needed
manual inspection. Two were warnings against shell pipelines (false
positives); four implicated real issues in Hugging Face, Xitter,
inference.sh and Parallel CLI. Each now has a distinct harness and safer
SKILL.md procedure. A negation-aware scanner now gates previously
confirmed critical patterns in CI; ordinary package-install references
remain review warnings, not proven vulnerabilities.

Counts after this extension: 31 of 117 Skills have distinct harnesses,
86 legacy Skills remain. Routing evaluation cases: 31 positive, 31 true
negative and 12 adversarial = 74 static fixtures; these have NOT been
run through live LLMs and do not imply routing or success percentages.

Remaining engineering priorities:
- Implement host-level capability admission using a signed/immutable
  SkillExecutionContext and actual tool-dispatch policy enforcement.
- Capture real tool-call traces and resource read-backs in a sealed
  baseline/candidate test suite with cost and failure metrics.
- Review remaining 86 Skills, plus all code templates and references;
  a regex risk scan is triage, not a complete threat model.
- Add adversarial filesystem tests for concurrent symlink replacement
  and deploy sensitive file tools only in an OS-level sandbox.

### Privileged-workflow deep review — 2026-11-22

Three additional individual advisory harnesses now cover 1Password,
Himalaya IMAP/SMTP and persistent webhook subscriptions. The 1Password
procedure previously encouraged tmux capture of a pane containing an
`op read` secret and used a sample literal service-account token; these
were replaced with metadata-first, no-secret-echo and scoped injection.
Himalaya previously piped unreviewed reply/forward templates directly
into SMTP send and suggested a moving-branch shell installer. Its revised
procedure separates draft from send, pins account/folder/UID, and treats
ambiguous send results as possibly delivered.
Webhook instructions previously published default `0.0.0.0` exposure
and encouraged plaintext secrets, unrestricted payload interpolation
and automatic external delivery. The revised procedure defaults to
127.0.0.1, mandates per-provider validation, replay defense, allowlisted
event data and independent permissions for downstream tools.

Important: the **gateway runtime still defines DEFAULT_HOST=0.0.0.0**
and supports `INSECURE_NO_AUTH` for testing. This review changes Skill
instructions, NOT the running gateway's defaults. Secure defaults and
defense-in-depth must be tackled separately, with compatibility tests
and explicit migration controls.

Coverage: 34 individual contracts, 83 legacy Skills. The eval fixtures
are now 34 positives, 34 contrastive negatives and 15 adversarial = 83
hand-authored cases, NOT measured LLM task results.
