"""Fail-closed policy contract tests; no live API or filesystem writes."""

import pytest

from autopilot.policy import ActionIntent, ActionPolicy, PolicyDenied


def allow(*caps, revision="policy:v1", critical=False):
    return ActionPolicy(
        allowed_projects=frozenset({"hermes"}),
        allowed_roles=frozenset({"A0", "A1"}),
        allowed_capabilities=frozenset(caps),
        allowed_repositories=frozenset({"Podtverzhdeno/hermes-agent"}),
        permit_critical=critical,
        policy_revision=revision,
    )


def intent(capability="github.repo.read", arguments=None, target="Podtverzhdeno/hermes-agent",
           role="A1", revision="git:abc"):
    return ActionIntent(
        project="hermes", actor_role=role, capability=capability,
        target=target, revision=revision, arguments=arguments or {},
    )


def test_default_policy_deny():
    with pytest.raises(PolicyDenied):
        ActionPolicy().evaluate(intent())


def test_unknown_capability_denied_even_if_allowlisted():
    with pytest.raises(PolicyDenied):
        allow("terminal.yolo").evaluate(intent("terminal.yolo"))


def test_read_operation_requires_explicit_scope_and_never_approval():
    dec = allow("github.repo.read").evaluate(intent())
    assert dec.risk == "R0"
    assert not dec.requires_owner_approval
    assert not dec.requires_secondary_confirmation
    assert dec.digest.startswith("sha256:")


def test_repository_scope_and_role_both_required():
    policy = allow("github.repo.read")
    with pytest.raises(PolicyDenied):
        policy.evaluate(intent(target="OtherOrg/other"))
    with pytest.raises(PolicyDenied):
        policy.evaluate(intent(role="unapproved"))


def test_pr_proposal_requires_exact_owner_approval():
    p = allow("github.pr.create")
    spec = intent("github.pr.create", {"head": "autopilot/task-1", "base": "main"})
    d = p.evaluate(spec)
    assert d.risk == "R2"
    assert d.requires_owner_approval
    assert not d.requires_secondary_confirmation
    assert d.digest != spec.digest


def test_digest_binds_target_actor_revision_args_and_policy():
    p1 = allow("github.pr.create", revision="policy:v1")
    p2 = allow("github.pr.create", revision="policy:v2")
    base = {"head": "autopilot/task-1", "base": "main"}
    spec = intent("github.pr.create", base)
    d0 = p1.evaluate(spec).digest
    assert d0 != p2.evaluate(spec).digest
    assert d0 != p1.evaluate(intent("github.pr.create", {**base, "head": "autopilot/other"})).digest
    assert d0 != p1.evaluate(intent("github.pr.create", base, role="A0")).digest
    assert d0 != p1.evaluate(intent("github.pr.create", base, revision="git:later")).digest


def test_json_key_order_does_not_change_approval_digest():
    p = allow("github.pr.create")
    a = intent("github.pr.create", {"base": "main", "head": "autopilot/task-1",
                                    "metadata": {"z": [3, 2], "a": True}})
    b = intent("github.pr.create", {"metadata": {"a": True, "z": [3, 2]},
                                    "head": "autopilot/task-1", "base": "main"})
    assert a.digest == b.digest
    assert p.evaluate(a).digest == p.evaluate(b).digest


def test_arguments_are_recursively_frozen_not_mutable_after_digest():
    spec = intent("github.pr.create", {"head": "autopilot/task-1", "base": "main",
                                       "meta": {"notes": ["a"]}})
    before = spec.digest
    with pytest.raises(TypeError):
        spec.arguments["head"] = "autopilot/other"
    with pytest.raises(TypeError):
        spec.arguments["meta"]["notes"][0] = "b"
    assert spec.digest == before


def test_owner_policy_allowlists_are_immutable_after_creation():
    source = {"github.repo.read"}
    p = ActionPolicy(allowed_projects={"hermes"}, allowed_roles={"A1"},
                     allowed_capabilities=source,
                     allowed_repositories={"Podtverzhdeno/hermes-agent"})
    source.add("github.pr.merge")
    assert "github.pr.merge" not in p.allowed_capabilities


def test_critical_operation_rejected_by_default_even_if_allowlisted():
    with pytest.raises(PolicyDenied, match="critical"):
        allow("github.pr.merge").evaluate(intent("github.pr.merge"))
    with pytest.raises(PolicyDenied, match="exact PR number"):
        allow("github.pr.merge", critical=True).evaluate(intent("github.pr.merge"))
    decision = allow("github.pr.merge", critical=True).evaluate(
        intent("github.pr.merge", {"pull_number": 45,
                                  "expected_head_sha": "a" * 40}))
    assert decision.risk == "R3"
    assert decision.requires_owner_approval
    assert decision.requires_secondary_confirmation


@pytest.mark.parametrize("branch", [
    "main", "feature-any", "autopilot/../main", "autopilot//bad",
    "autopilot/.", "autopilot/..", "autopilot/a..b", "autopilot/abc.lock",
    "autopilot/foo bar", "autopilot/evil\nnext", "autopilot/bad;cmd", None,
])
def test_arbitrary_or_ambiguous_branch_denied(branch):
    p = allow("github.branch.create")
    with pytest.raises(PolicyDenied):
        p.evaluate(intent("github.branch.create", {"branch": branch}))


def test_valid_task_branch_requires_owner_approval():
    p = allow("github.branch.create")
    decision = p.evaluate(intent("github.branch.create", {"branch": "autopilot/work-42"}))
    assert decision.requires_owner_approval


def test_missing_pr_base_or_head_denied():
    p = allow("github.pr.create")
    with pytest.raises(PolicyDenied):
        p.evaluate(intent("github.pr.create", {"head": "autopilot/a"}))
    with pytest.raises(PolicyDenied):
        p.evaluate(intent("github.pr.create", {"base": "main"}))
    with pytest.raises(PolicyDenied):
        p.evaluate(intent("github.pr.create",
                          {"head": "autopilot/evil; command", "base": "main"}))
    with pytest.raises(PolicyDenied):
        p.evaluate(intent("github.pr.create",
                          {"head": "autopilot/good", "base": "main..other"}))


def test_path_capabilities_denied_until_scoped_adapter_exists():
    p = allow("workspace.file.read", "obsidian.note.patch")
    with pytest.raises(PolicyDenied, match="scoped path adapter"):
        p.evaluate(intent("workspace.file.read", target="/tmp/secret"))
    with pytest.raises(PolicyDenied, match="scoped path adapter"):
        p.evaluate(intent("obsidian.note.patch", target="C:\\Vault\\secret.md"))


def test_invalid_argument_types_fail_at_construction():
    with pytest.raises(ValueError):
        intent(arguments={"bad": float("nan")})
    with pytest.raises(ValueError):
        intent(arguments={"bad": float("inf")})
    with pytest.raises(ValueError):
        intent(arguments={1: "x"})
    with pytest.raises(ValueError):
        intent(arguments={"bad": object()})
    with pytest.raises(ValueError):
        intent(arguments={"data": "x" * 70000})


def test_reused_revision_does_not_authorize_new_target():
    p = allow("github.repo.read")
    a = intent()
    b = intent(target="Podtverzhdeno/other")
    with pytest.raises(PolicyDenied):
        p.evaluate(b)
    assert a.digest != b.digest


def test_unsupported_repository_deletion_stays_denied_even_with_critical_flag():
    policy = allow("github.repo.delete", critical=True)
    with pytest.raises(PolicyDenied, match="unknown capability"):
        policy.evaluate(intent("github.repo.delete"))


def test_comment_requires_exact_issue_and_bounded_message():
    policy = allow("github.issue.comment")
    with pytest.raises(PolicyDenied):
        policy.evaluate(intent("github.issue.comment", {"body": "hi"}))
    with pytest.raises(PolicyDenied):
        policy.evaluate(intent("github.issue.comment",
                               {"issue_number": 1, "body": "a" * 8193}))
    decision = policy.evaluate(intent("github.issue.comment",
                                     {"issue_number": 41, "body": "Bounded status."}))
    assert decision.requires_owner_approval


def test_merge_digest_binds_pr_number_and_exact_head():
    policy = allow("github.pr.merge", critical=True)
    a = intent("github.pr.merge", {"pull_number": 1, "expected_head_sha": "a" * 40})
    b = intent("github.pr.merge", {"pull_number": 1, "expected_head_sha": "b" * 40})
    assert policy.evaluate(a).digest != policy.evaluate(b).digest
