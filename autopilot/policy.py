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
    "github.repo.delete": "R3",
    # Scoped local file edits require a separate realpath-checked service.
    "workspace.file.patch": "R1",
    "workspace.file.read": "R0",
    "obsidian.note.patch": "R2",
})

_GITHUB_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_CRITICAL = frozenset(("R3",))
_EXTERNAL = frozenset(("R2", "R3"))


def _canonical(value: Any) -> Any:
    """Reject non-JSON, NaN, non-string dict keys and nonfinite/huge payloads."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite action argument")
        return value
    if type(value) in (list, tuple):
        return [_canonical(item) for item in value]
    if type(value) is dict:
        if not all(type(k) is str for k in value):
            raise ValueError("action arguments must use string keys")
        return {key: _canonical(val) for key, val in value.items()}
    raise ValueError("unsupported action argument type")


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
                if any(segment in ("", ".", "..") for segment in branch.split("/")):
                    raise PolicyDenied("unsafe branch name")
            if intent.capability == "github.pr.create":
                if not all(
                    isinstance(intent.arguments.get(key), str)
                    and intent.arguments[key].strip()
                    for key in ("head", "base")
                ):
                    raise PolicyDenied("PR head/base must be explicit")
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
