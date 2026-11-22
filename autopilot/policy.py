"""Pure, fail-closed policy decisions for proposed Autopilot actions.

No tool calls, filesystem writes or approvals occur in this module. The
trusted tool gateway must enforce the decision and revalidate the live
workspace / repo / lease before the actual external operation.

The LLM does not choose its own risk class or define allowed capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping


class PolicyDenied(PermissionError):
    """A capability or target is outside the owner's explicit policy."""


# Identity is an executable adapter name controlled by the host, not a free-form
# LLM tool label. An unknown adapter is denied. Critical adapters cannot be
# enabled by simply saying "autopilot on".
_CAPABILITY_RISKS = MappingProxyType({
    "github.repo.read": "R0",
    "github.pr.read": "R0",
    "github.checks.read": "R0",
    "github.branch.create": "R2",
    "github.pr.create": "R2",
    "github.issue.comment": "R2",
    "github.pr.merge": "R3",
    # Scoped local file edits require a separate realpath-checked service.
    "workspace.file.patch": "R1",
    "workspace.file.read": "R0",
    "obsidian.note.patch": "R2",
})

_GITHUB_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_GIT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,180}$")


def _safe_ref(value: Any) -> bool:
    if not isinstance(value, str) or not _GIT_REF.fullmatch(value):
        return False
    if ".." in value or "//" in value or value.endswith("."):
        return False
    if any(not part or part.startswith(".") or part.endswith(".lock")
           for part in value.split("/")):
        return False
    return True
_CRITICAL = frozenset(("R3",))
_EXTERNAL = frozenset(("R2", "R3"))


def _canonical(
    value: Any, *, _depth: int = 0, _seen: set[int] | None = None,
    _budget: list[int] | None = None,
) -> Any:
    """Return bounded JSON-shaped values; reject cycles, depth and size bombs.

    Input is untrusted: tool arguments may originate from a model or remote
    document. Do not exhaust recursion or CPU while preparing approvals.
    """
    if _depth > 32:
        raise ValueError("action arguments exceed maximum nesting depth")
    if _budget is None:
        _budget = [0]
    _budget[0] += 1
    if _budget[0] > 10000:
        raise ValueError("action arguments have too many nodes")
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        if len(value) > 65536:
            raise ValueError("action argument string too long")
        return value
    if type(value) is int:
        if value.bit_length() > 512:
            raise ValueError("action argument integer too large")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite action argument")
        return value
    if type(value) not in (list, tuple, dict):
        raise ValueError("unsupported action argument type")
    if _seen is None:
        _seen = set()
    identity = id(value)
    if identity in _seen:
        raise ValueError("cyclic action arguments are not allowed")
    _seen.add(identity)
    try:
        if type(value) in (list, tuple):
            return [
                _canonical(item, _depth=_depth + 1, _seen=_seen, _budget=_budget)
                for item in value
            ]
        if not all(type(k) is str for k in value):
            raise ValueError("action arguments must use string keys")
        return {
            key: _canonical(item, _depth=_depth + 1, _seen=_seen, _budget=_budget)
            for key, item in value.items()
        }
    finally:
        _seen.remove(identity)


def _freeze(value: Any) -> Any:
    """Recursively freeze all caller-provided action arguments."""
    if type(value) is dict:
        return MappingProxyType({key: _freeze(v) for key, v in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(v) for key, v in value.items()}
    if type(value) is tuple:
        return [_thaw(item) for item in value]
    return value


def _nonempty(field_name: str, text: str) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > 1024:
        raise ValueError(field_name + " must be a bounded nonempty string")
    return text


@dataclass(frozen=True)
class ActionIntent:
    project: str
    actor_role: str
    capability: str
    target: str
    revision: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for field_name in ("project", "actor_role", "capability", "target", "revision"):
            _nonempty(field_name, getattr(self, field_name))
        if type(self.arguments) is not dict:
            raise ValueError("arguments must be a plain JSON mapping")
        clean = _canonical(dict(self.arguments))
        encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 65536:
            raise ValueError("action arguments exceed 64 KiB")
        object.__setattr__(self, "arguments", _freeze(clean))

    @property
    def digest(self) -> str:
        """Digest covers the actual application-intent tuple, not prose."""
        payload = {
            "version": 1,
            "project": self.project,
            "actor_role": self.actor_role,
            "capability": self.capability,
            "target": self.target,
            "revision": self.revision,
            "arguments": _thaw(self.arguments),
        }
        wire = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return "sha256:" + sha256(wire.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ActionDecision:
    risk: str
    requires_owner_approval: bool
    requires_secondary_confirmation: bool
    digest: str
    reason: str


@dataclass(frozen=True)
class ActionPolicy:
    """Explicit scope allowlist. Defaults deny ALL capabilities and writes.

    A gateway must validate OS paths, git branch contents and live resource
    identities independently; a pure policy object cannot grant OS isolation.
    """

    allowed_projects: frozenset[str] = frozenset()
    allowed_roles: frozenset[str] = frozenset()
    allowed_capabilities: frozenset[str] = frozenset()
    allowed_repositories: frozenset[str] = frozenset()
    # Never permit R3 without an owner controlled global feature flag, in
    # addition to approval at the exact operation boundary.
    permit_critical: bool = False
    policy_revision: str = "policy:v1"

    def __post_init__(self):
        for field_name in ("allowed_projects", "allowed_roles",
                           "allowed_capabilities", "allowed_repositories"):
            values = getattr(self, field_name)
            if not isinstance(values, (set, frozenset, tuple, list)):
                raise ValueError(field_name + " must be an iterable allowlist")
            for value in values:
                _nonempty(field_name, value)
            object.__setattr__(self, field_name, frozenset(values))
        if type(self.permit_critical) is not bool:
            raise ValueError("permit_critical must be a boolean")
        _nonempty("policy_revision", self.policy_revision)

    def evaluate(self, intent: ActionIntent) -> ActionDecision:
        risk = _CAPABILITY_RISKS.get(intent.capability)
        if risk is None:
            raise PolicyDenied("unknown capability is denied by default")
        if intent.project not in self.allowed_projects:
            raise PolicyDenied("project outside owner's allowlist")
        if intent.actor_role not in self.allowed_roles:
            raise PolicyDenied("actor role outside owner's allowlist")
        if intent.capability not in self.allowed_capabilities:
            raise PolicyDenied("capability not enabled by owner")
        if risk in _CRITICAL and not self.permit_critical:
            raise PolicyDenied("critical external operation disabled")
        if intent.capability.startswith("github."):
            if not _GITHUB_REPO.fullmatch(intent.target):
                raise PolicyDenied("invalid repository target")
            if intent.target not in self.allowed_repositories:
                raise PolicyDenied("repository outside owner's allowlist")
            if intent.capability == "github.branch.create":
                branch = intent.arguments.get("branch")
                if not isinstance(branch, str) or not branch.startswith("autopilot/"):
                    raise PolicyDenied("only task-specific autopilot branches may be created")
                if not _safe_ref(branch):
                    raise PolicyDenied("unsafe Git branch ref")
            if intent.capability == "github.pr.create":
                if not all(_safe_ref(intent.arguments.get(key))
                           for key in ("head", "base")):
                    raise PolicyDenied("PR head/base must be explicit safe refs")
            if intent.capability == "github.pr.merge":
                number = intent.arguments.get("pull_number")
                expected_sha = intent.arguments.get("expected_head_sha")
                if not (type(number) is int and number > 0
                        and isinstance(expected_sha, str)
                        and re.fullmatch(r"[0-9a-fA-F]{40}", expected_sha)):
                    raise PolicyDenied("merge requires exact PR number and expected 40-hex head SHA")
            if intent.capability == "github.issue.comment":
                issue_number = intent.arguments.get("issue_number")
                body = intent.arguments.get("body")
                if not (type(issue_number) is int and issue_number > 0
                        and isinstance(body, str) and 0 < len(body) <= 8192):
                    raise PolicyDenied("comment needs exact issue number and bounded body")
        else:
            # No path can be considered trustworthy until a scoped local file
            # service can canonicalize and check it on the destination host.
            raise PolicyDenied("local/Obsidian path requires a trusted scoped path adapter")
        return ActionDecision(
            risk=risk,
            requires_owner_approval=risk in _EXTERNAL,
            requires_secondary_confirmation=risk in _CRITICAL,
            digest="sha256:" + sha256(
                json.dumps(
                    {"intent": intent.digest, "policy_revision": self.policy_revision},
                    sort_keys=True, separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            reason="permitted proposal; gateway must enforce remaining guards",
        )
