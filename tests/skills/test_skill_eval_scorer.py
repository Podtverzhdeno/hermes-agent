"""Deterministic scorer invariants; no agent or model API calls."""

import json

import pytest

from scripts.score_skill_evals import EvalDataError, load_jsonl, score_predictions


@pytest.fixture
def cases():
    return {
        "POS": {"id": "POS", "kind": "positive", "expected_skill": "review",
                "forbidden_skills": []},
        "NEG": {"id": "NEG", "kind": "hard_negative", "expected_skill": None,
                "forbidden_skills": ["review"]},
        "ADV": {"id": "ADV", "kind": "injection", "expected_skill": "vault",
                "forbidden_skills": [], "forbidden_side_effects": ["delete"]},
    }


def test_exact_routes_with_no_effects_pass(cases):
    result = score_predictions(cases, {
        "POS": {"selected_skill": "review", "side_effects": []},
        "NEG": {"selected_skill": "debug", "side_effects": []},
        "ADV": {"selected_skill": "vault", "side_effects": ["read"]},
    })
    assert result["coverage"] == 1.0
    assert result["pass_rate_observed"] == 1.0
    assert result["forbidden_side_effects"] == []
    assert result["ready_for_comparison"]


def test_wrong_skill_fails_selection_without_security_violation(cases):
    result = score_predictions(cases, {
        "POS": {"selected_skill": "other", "side_effects": []},
        "NEG": {"selected_skill": "review", "side_effects": []},
        "ADV": {"selected_skill": "vault", "side_effects": []},
    })
    assert result["passed_observed"] == 1
    assert len(result["selection_or_safety_failures"]) == 2
    assert result["forbidden_side_effects"] == []


def test_forbidden_side_effect_blocks_comparison(cases):
    result = score_predictions(cases, {
        "POS": {"selected_skill": "review", "side_effects": []},
        "NEG": {"selected_skill": None, "side_effects": []},
        "ADV": {"selected_skill": "vault", "side_effects": ["delete"]},
    })
    assert result["passed_observed"] == 2
    assert result["forbidden_side_effects"] == [{"id": "ADV", "effects": ["delete"]}]
    assert result["ready_for_comparison"] is False


def test_missing_predictions_are_not_counted_as_success(cases):
    result = score_predictions(cases, {
        "POS": {"selected_skill": "review", "side_effects": []}
    })
    assert result["coverage"] == 0.3333
    assert result["missing_ids"] == ["ADV", "NEG"]
    assert result["ready_for_comparison"] is False
    assert result["pass_rate_observed"] == 1.0


def test_no_results_is_no_evidence(cases):
    result = score_predictions(cases, {})
    assert result["pass_rate_observed"] is None
    assert result["coverage"] == 0
    assert result["passed_observed"] == 0


def test_invalid_tool_trace_schema_is_rejected(cases):
    with pytest.raises(EvalDataError, match="side_effects must"):
        score_predictions(cases, {
            "POS": {"selected_skill": "review", "side_effects": "none"}
        })


def test_unknown_prediction_id_is_rejected(cases):
    with pytest.raises(EvalDataError, match="Unknown prediction"):
        score_predictions(cases, {"X": {"selected_skill": None, "side_effects": []}})


def test_duplicate_case_identifiers_rejected(tmp_path):
    path = tmp_path / "cases.jsonl"
    row = json.dumps({"id": "dup", "kind": "positive"})
    path.write_text(row + "\n" + row + "\n", encoding="utf-8")
    with pytest.raises(EvalDataError, match="duplicate"):
        load_jsonl(path)


def test_real_gold_cases_all_unique_and_cover_pilot_skills():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    cases = load_jsonl(root / "evals" / "skills" / "activation_cases.jsonl")
    assert len(cases) >= 47
    positives = {c["expected_skill"] for c in cases.values() if c["kind"] == "positive"}
    negatives = {s for c in cases.values() if c["kind"] == "hard_negative"
                 for s in c["forbidden_skills"]}
    assert positives == negatives
    assert len(positives) >= 22
    assert sum(c["kind"] == "injection" for c in cases.values()) >= 3

def test_hard_negative_with_expected_alternative_rejects_wrong_nonforbidden_skill():
    """Being merely different from the forbidden Skill is not sufficient."""
    cases = {"X": {"id": "X", "kind": "hard_negative",
                   "expected_skill": "github-pr-workflow",
                   "forbidden_skills": ["code-review"]}}
    wrong = score_predictions(cases, {
        "X": {"selected_skill": "arxiv", "side_effects": []}})
    correct = score_predictions(cases, {
        "X": {"selected_skill": "github-pr-workflow", "side_effects": []}})
    assert wrong["passed_observed"] == 0
    assert correct["passed_observed"] == 1


def test_hard_negative_contradictory_gold_is_rejected():
    cases = {"X": {"id": "X", "kind": "hard_negative",
                   "expected_skill": "code-review",
                   "forbidden_skills": ["code-review"]}}
    with pytest.raises(EvalDataError, match="also forbidden"):
        score_predictions(cases, {
            "X": {"selected_skill": "code-review", "side_effects": []}})


def test_real_gold_prompts_are_nontrivial_and_contrastive():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    cases = load_jsonl(root / "evals" / "skills" / "activation_cases.jsonl")
    positives = {key[:3]: c for key, c in cases.items()
                 if c["kind"] == "positive"}
    negatives = {key[:3]: c for key, c in cases.items()
                 if c["kind"] == "hard_negative"}
    assert len(positives) >= 27
    assert positives.keys() == negatives.keys()
    for ident in positives:
        pos, neg = positives[ident], negatives[ident]
        assert len(pos["prompt"]) > 35
        assert pos["prompt"].casefold() != pos["expected_skill"].casefold()
        assert pos["prompt"] != neg["prompt"]
        assert pos["expected_skill"] in neg["forbidden_skills"]
        assert neg["expected_skill"] not in neg["forbidden_skills"]
