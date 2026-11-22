"""Deterministic evaluation casebook and scoring for Hermes specialized Skills.

Pure-stdlib CLI; NO model calls, API keys, browser automation or writes
except an explicitly chosen --output path. The evaluator scores external
observations only: it CANNOT authenticate a reported tool invocation or
verifier receipt. Never claim live model improvements merely from fixtures.

Usage:
  python -m scripts.evaluate_specialized_skills export --root . --output cases.jsonl
  python -m scripts.evaluate_specialized_skills score --cases cases.jsonl --observations trials.jsonl
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path

from agent.skill_harness import load_skill_harness


class SkillEvalError(ValueError):
    pass


def _check_name(value, field):
    if not isinstance(value, str) or not value or len(value) > 256 or "\n" in value:
        raise SkillEvalError(field + " must be nonempty bounded text")
    return value


def create_casebook(root: Path) -> list[dict]:
    """One positive and negative observable case for each declared example."""
    cases = []
    root = Path(root).resolve()
    for tree_name in ("skills", "optional-skills"):
        tree = root / tree_name
        if not tree.is_dir():
            continue
        for file in sorted(tree.rglob("harness.json")):
            if file.is_symlink() or not (file.parent / "SKILL.md").is_file():
                continue
            name = file.parent.name
            # The one known discrepancy is the upstream legacy alias for LM
            # evaluation harness. Resolve identity from profile, then verify
            # its name from the actual SKILL.md.
            import json as _json
            raw = _json.loads(file.read_text(encoding="utf-8"))
            name = raw.get("skill", name)
            profile = load_skill_harness(file.parent, name)
            skill_doc = (file.parent / "SKILL.md").read_text(encoding="utf-8")
            if ("name: " + name) not in skill_doc.split("---", 2)[1]:
                raise SkillEvalError("SKILL.md name mismatch: " + str(file))
            for category in ("trigger", "do_not_trigger"):
                for index, prompt in enumerate(profile["routing"][category]):
                    source = file.parent.relative_to(root).as_posix()
                    case_key = source + "|" + category + "|" + str(index) + "|" + prompt
                    ident = sha256(case_key.encode("utf-8")).hexdigest()[:20]
                    cases.append({
                        "schema_version": 1,
                        "case_id": ident,
                        "skill": name,
                        "category": category,
                        "expected_loaded": category == "trigger",
                        "prompt": prompt,
                        "source": source,
                    })
    ids = [x["case_id"] for x in cases]
    if len(ids) != len(set(ids)):
        raise SkillEvalError("case identifier collision")
    return cases


def read_jsonl(path: Path, *, max_lines: int = 100000, max_bytes: int = 16_000_000) -> list[dict]:
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise SkillEvalError("input JSONL exceeds size limit")
    values = []
    with path.open("r", encoding="utf-8") as file:
        for i, line in enumerate(file, 1):
            if i > max_lines:
                raise SkillEvalError("too many JSONL records")
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SkillEvalError("invalid JSONL at line " + str(i)) from exc
            if not isinstance(value, dict):
                raise SkillEvalError("JSONL entries must be objects")
            values.append(value)
    return values


def wilson95(success: int, total: int) -> list[float] | None:
    """Binomial Wilson score interval, z=1.95996398454."""
    if not total:
        return None
    z = 1.95996398454
    p = success / total
    den = 1 + (z * z) / total
    mid = (p + (z * z) / (2 * total)) / den
    rad = (z / den) * math.sqrt(p * (1 - p) / total + (z * z) / (4 * total * total))
    return [round(max(0.0, mid - rad), 4), round(min(1.0, mid + rad), 4)]


def score_observations(cases: list[dict], observations: list[dict]) -> dict:
    """Score external observations. Does not attest event provenance."""
    lookup = {}
    for case in cases:
        if not isinstance(case, dict) or case.get("case_id") in lookup:
            raise SkillEvalError("invalid/duplicate casebook")
        if case.get("category") not in ("trigger", "do_not_trigger"):
            raise SkillEvalError("invalid case category")
        if type(case.get("expected_loaded")) is not bool:
            raise SkillEvalError("expected_loaded must be boolean")
        lookup[case["case_id"]] = case

    by_group = defaultdict(lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0,
                                    "reported_passes": 0, "reported_failures": 0,
                                    "unverified_outcomes": 0, "cost_usd": 0.0,
                                    "duration_seconds": 0.0, "tokens": 0})
    observed = {}
    for row in observations:
        if not isinstance(row, dict):
            raise SkillEvalError("invalid observation")
        key = row.get("case_id")
        if key not in lookup or row.get("skill") != lookup[key]["skill"]:
            raise SkillEvalError("observation is not in pinned casebook")
        model = _check_name(row.get("model"), "model")
        condition = row.get("condition")
        if condition not in ("with_skill", "without_skill"):
            raise SkillEvalError("unknown condition")
        if type(row.get("loaded")) is not bool:
            raise SkillEvalError("loaded must be a strict boolean")
        outcome = row.get("outcome", "not_checked")
        if outcome not in ("passed", "failed", "not_checked"):
            raise SkillEvalError("invalid outcome")
        for metric in ("cost_usd", "duration_seconds"):
            value = row.get(metric, 0)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise SkillEvalError(metric + " must be finite and nonnegative")
        tokens = row.get("tokens", 0)
        if type(tokens) is not int or tokens < 0:
            raise SkillEvalError("tokens must be nonnegative integer")
        record_key = (model, condition, key)
        if record_key in observed:
            raise SkillEvalError("duplicate trial for model, condition and case")
        observed[record_key] = row
        group = by_group[(model, condition, row["skill"])]
        expected = lookup[key]["expected_loaded"]
        group["tp" if expected and row["loaded"] else
              "fn" if expected else
              "fp" if row["loaded"] else "tn"] += 1
        group["reported_passes" if outcome == "passed" else
              "reported_failures" if outcome == "failed" else
              "unverified_outcomes"] += 1
        group["cost_usd"] += float(row.get("cost_usd", 0))
        group["duration_seconds"] += float(row.get("duration_seconds", 0))
        group["tokens"] += tokens

    result = []
    for (model, condition, skill), g in sorted(by_group.items()):
        precision_den = g["tp"] + g["fp"]
        recall_den = g["tp"] + g["fn"]
        specificity_den = g["tn"] + g["fp"]
        n = sum(g[k] for k in ("tp", "tn", "fp", "fn"))
        result.append({
            "model": model, "condition": condition, "skill": skill, "observations": n,
            "confusion": {k: g[k] for k in ("tp", "fp", "tn", "fn")},
            "precision": round(g["tp"] / precision_den, 4) if precision_den else None,
            "precision_ci95": wilson95(g["tp"], precision_den),
            "recall": round(g["tp"] / recall_den, 4) if recall_den else None,
            "recall_ci95": wilson95(g["tp"], recall_den),
            "specificity": round(g["tn"] / specificity_den, 4) if specificity_den else None,
            "reported_outcome_counts": {
                "passed": g["reported_passes"],
                "failed": g["reported_failures"],
                "not_checked": g["unverified_outcomes"],
            },
            "total_cost_usd": round(g["cost_usd"], 6),
            "total_tokens": g["tokens"],
            "total_duration_seconds": round(g["duration_seconds"], 3),
        })

    matched = []
    for (model, condition, case_id), row in observed.items():
        if condition != "with_skill":
            continue
        baseline = observed.get((model, "without_skill", case_id))
        if baseline is None:
            continue
        a = row.get("outcome", "not_checked")
        b = baseline.get("outcome", "not_checked")
        if a in ("passed", "failed") and b in ("passed", "failed"):
            matched.append((model, row["skill"], a, b))
    paired = {}
    for model, skill, a, b in matched:
        m = paired.setdefault((model, skill), {
            "both_passed": 0, "both_failed": 0,
            "with_only": 0, "without_only": 0,
        })
        key = ("both_passed" if a == "passed" and b == "passed" else
               "both_failed" if a == "failed" and b == "failed" else
               "with_only" if a == "passed" else "without_only")
        m[key] += 1
    paired_result = []
    for (model, skill), stats in sorted(paired.items()):
        paired_result.append({
            "model": model, "skill": skill,
            "paired_observations": sum(stats.values()),
            **stats, "net_reported_win": stats["with_only"] - stats["without_only"],
        })
    return {
        "schema_version": 1,
        "observations": len(observations),
        "casebook_size": len(cases),
        "routing_metrics": result,
        "paired_reported_outcomes": paired_result,
        "authenticates_external_evidence": False,
        "live_model_evaluation_performed": False,
        "warning": "Data are caller-supplied observations, not independently verified claims.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    exp.add_argument("--output", required=True)
    score = sub.add_parser("score")
    score.add_argument("--cases", required=True)
    score.add_argument("--observations", required=True)
    score.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            cases = create_casebook(Path(args.root))
            path = Path(args.output)
            if path.exists():
                raise SkillEvalError("refusing to overwrite existing casebook")
            with path.open("x", encoding="utf-8") as f:
                for c in cases:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
            print("Exported " + str(len(cases)) + " cases to " + str(path))
        else:
            result = score_observations(read_jsonl(Path(args.cases)),
                                        read_jsonl(Path(args.observations)))
            rendered = json.dumps(result, ensure_ascii=False, indent=2)
            if args.output:
                dest = Path(args.output)
                with dest.open("x", encoding="utf-8") as f:
                    f.write(rendered + "\n")
            else:
                print(rendered)
    except (SkillEvalError, OSError, ValueError) as exc:
        parser.exit(2, "Skill eval error: " + str(exc) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
