"""Rules must never crash: odd data (nulls, wrong types) gives a falsy result, on every platform.

Found by differential fuzzing: jsonlogic-rs raised ValueError on ~1/3 of mixed-type inputs where
json-logic-js returned a value, which would have been a 500 on submit while the browser looked fine.
"""
import itertools

import pytest

from apps.forms.rules import ALLOWED_OPS, BANNED_OPS, FormSpec, evaluate, evaluate_form, truthy

VALUES = [None, True, False, 0, 1, 2.5, "", "abc", "2026-10-14", ["a", "b"], [], {"a": 1}]
BINARY = ["==", "!=", "===", "!==", "<", "<=", ">", ">=", "in", "+"]
ITERATING = ["some", "all", "none", "filter", "reduce"]


@pytest.mark.parametrize("op", BINARY)
def test_binary_operators_never_raise(op):
    for a, b in itertools.product(VALUES, VALUES):
        evaluate({op: [{"var": "x"}, {"var": "y"}]}, {"x": a, "y": b})


@pytest.mark.parametrize("op", ["!", "!!"])
def test_unary_operators_never_raise(op):
    for a in VALUES:
        evaluate({op: [{"var": "x"}]}, {"x": a})


@pytest.mark.parametrize("op", ITERATING)
def test_iterating_operators_never_raise(op):
    for a in VALUES:
        rule = ({"reduce": [{"var": "x"}, {"+": [{"var": "current"}, {"var": "accumulator"}]}, 0]}
                if op == "reduce" else {op: [{"var": "x"}, {"in": [{"var": ""}, ["a", "b"]]}]})
        evaluate(rule, {"x": a})


def test_a_failing_rule_is_falsy_not_an_error():
    rule = {"in": ["x", {"var": "n"}]}  # `in` on a number cannot apply
    assert evaluate(rule, {"n": 5}) is None
    assert truthy(rule, {"n": 5}) is False


def test_form_evaluation_survives_a_rule_that_cannot_apply():
    spec = FormSpec.from_dict({"form": "inspection", "containers": [
        {"id": "p", "kind": "page"}, {"id": "s", "kind": "section", "parent": "p"}], "fields": [
        {"key": "nn", "type": "number", "section": "s"},
        {"key": "why", "type": "short_text", "section": "s",
         "show_if": {"in": ["x", {"var": "inspection.nn"}]}}]})
    result = evaluate_form(spec, {"inspection": {"nn": 5}}, "2026-10-14")
    assert result.visible["why"] is False


def test_the_supported_operator_set_is_small_and_disjoint_from_the_banned_set():
    assert not ALLOWED_OPS & BANNED_OPS
    assert {"-", "*", "/", "%", "min", "max", "cat", "substr", "map"} <= BANNED_OPS
    assert {"var", "==", "in", "some", "reduce", "+", "if", "!", "!!"} <= ALLOWED_OPS


def test_a_rust_panic_is_swallowed_but_other_base_exceptions_are_not(monkeypatch):
    import jsonlogic_rs

    class PanicException(BaseException):  # stands in for pyo3_runtime.PanicException
        pass

    def panic(*_):
        raise PanicException("boom")

    monkeypatch.setattr(jsonlogic_rs, "apply", panic)
    assert evaluate({"==": [1, 1]}, {}) is None

    def interrupt(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(jsonlogic_rs, "apply", interrupt)
    with pytest.raises(KeyboardInterrupt):
        evaluate({"==": [1, 1]}, {})
