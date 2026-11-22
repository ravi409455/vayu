"""The shared cases in /shared/rule-vectors. The TypeScript and Kotlin suites run the same files."""
import json
from pathlib import Path

import pytest

from apps.forms.rules import FormSpec, evaluate, evaluate_form

VECTORS = Path(__file__).resolve().parents[4] / "shared" / "rule-vectors"
EVAL = json.loads((VECTORS / "eval_vectors.json").read_text())
FORM = json.loads((VECTORS / "form_vectors.json").read_text())
ROBUST = json.loads((VECTORS / "robust_vectors.json").read_text())


def same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return a == b
    return a == b


@pytest.mark.parametrize("case", EVAL, ids=[c["name"] for c in EVAL])
def test_eval_vector(case):
    assert same(evaluate(case["rule"], case["data"]), case["expected"])


@pytest.mark.parametrize("case", ROBUST, ids=[c["name"] for c in ROBUST])
def test_robust_vector(case):
    assert same(evaluate(case["rule"], case["data"]), case["expected"])


@pytest.mark.parametrize("case", FORM, ids=[c["name"] for c in FORM])
def test_form_vector(case):
    result = evaluate_form(FormSpec.from_dict(case["spec"]), case["answers"], case["today"],
                           case["overrides"])
    exp = case["expected"]
    for key, want in exp.get("visible", {}).items():
        assert result.visible[key] is want, f"visible[{key}]"
    for key, want in exp.get("required", {}).items():
        assert result.required[key] is want, f"required[{key}]"
    assert result.errors == exp["errors"]
    assert result.derived == exp["derived"]
    assert result.defects == exp["defects"]


def test_vector_files_are_substantial():
    assert len(EVAL) >= 50 and len(FORM) >= 60 and len(ROBUST) >= 1000
