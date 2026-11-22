"""Rating maths (pure functions). Numbers from REQUIREMENTS §5.4."""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.scoring.engine import (
    DEFAULT_CONFIG,
    category_value,
    overall_result,
    round_half_up,
    validate_config,
    word_for,
)

D = DEFAULT_CONFIG["deductions"]


def test_default_numbers_are_the_agreed_ones():
    assert D == {"minor": 0.25, "major": 1, "critical": 3}
    assert DEFAULT_CONFIG["thresholds"] == {"excellent": 4.5, "good": 3.5, "average": 2.5}


@pytest.mark.parametrize("x,expected", [(3.5, 4), (3.25, 3), (3.75, 4), (1.0, 1), (4.5, 5),
                                        (4.49, 4), (2.5, 3), (5.0, 5)])
def test_round_half_up(x, expected):
    assert round_half_up(x) == expected


@pytest.mark.parametrize("severities,expected", [
    ([], 5), (["minor"], 5), (["minor"] * 2, 5), (["minor"] * 3, 4), (["major"], 4),
    (["major", "minor"], 4), (["major"] * 2, 3), (["minor"] * 6, 4), (["critical"], 2),
    (["critical", "major"], 1), (["critical"] * 2, 1), (["major"] * 4, 1), (["major"] * 5, 1),
    (["minor"] * 14, 2), (["minor"] * 15, 1), (["major", "major", "minor", "minor"], 3),
    (["critical", "minor"], 2), (["major", "minor", "minor", "minor"], 3),
    (["minor"] * 4, 4), (["major", "critical"], 1),
])
def test_category_value(severities, expected):
    assert category_value(severities, D) == expected


def test_a_critical_cap_only_lowers_and_only_for_critical_defects():
    assert category_value(["critical"], D, cap=1) == 1
    assert category_value(["critical"], D, cap=4) == 2     # already lower than the cap
    assert category_value(["major"], D, cap=1) == 4        # no critical: cap not applied
    assert category_value([], D, cap=1) == 5


def test_custom_deductions_are_honoured():
    assert category_value(["minor"] * 2, {"minor": 1, "major": 2, "critical": 4}) == 3


@pytest.mark.parametrize("avg,word", [(5, "excellent"), (4.5, "excellent"), (4.49, "good"),
                                      (3.5, "good"), (3.49, "average"), (2.5, "average"),
                                      (2.49, "bad"), (1, "bad")])
def test_word_for(avg, word):
    assert word_for(avg, DEFAULT_CONFIG["thresholds"]) == word


def test_overall_is_the_average_of_the_category_values():
    r = overall_result([5, 4, 5, 4], DEFAULT_CONFIG["thresholds"], any_critical=False)
    assert r == {"average": 4.5, "word": "excellent"}
    assert overall_result([3, 4], DEFAULT_CONFIG["thresholds"], False)["word"] == "good"


def test_any_critical_defect_caps_the_overall_at_average_but_never_raises_it():
    t = DEFAULT_CONFIG["thresholds"]
    assert overall_result([5, 5, 5], t, any_critical=True)["word"] == "average"
    assert overall_result([2, 2, 2], t, any_critical=True)["word"] == "bad"
    assert overall_result([3, 3], t, any_critical=True)["word"] == "average"


def test_overall_of_nothing_is_none():
    assert overall_result([], DEFAULT_CONFIG["thresholds"], False) == {"average": None, "word": None}


@given(st.lists(st.sampled_from(["minor", "major", "critical"]), max_size=30))
def test_values_stay_in_1_to_5_and_more_defects_never_raise_a_rating(severities):
    v = category_value(severities, D)
    assert 1 <= v <= 5
    assert category_value(severities + ["minor"], D) <= v


GOOD_CFG = {"categories": [{"key": "engine", "label": "Engine", "sections": ["Engine"]},
                           {"key": "ac", "label": "A.C.", "sections": ["Air Conditioning"],
                            "cap": 2}],
            "deductions": {"minor": 0.25, "major": 1, "critical": 3},
            "thresholds": {"excellent": 4.5, "good": 3.5, "average": 2.5}}


def test_a_good_config_validates_and_defaults_fill_in():
    validate_config(GOOD_CFG)
    validate_config({})  # nothing configured is allowed: no ratings
    validate_config({"categories": GOOD_CFG["categories"]})


@pytest.mark.parametrize("cfg", [
    [], {"categories": "x"}, {"categories": [{"key": "Bad Key", "label": "x", "sections": ["S"]}]},
    {"categories": [{"key": "a_b", "label": "", "sections": ["S"]}]},
    {"categories": [{"key": "a_b", "label": "x", "sections": []}]},
    {"categories": [{"key": "a_b", "label": "x", "sections": [""]}]},
    {"categories": [{"key": "a_b", "label": "x", "sections": ["S"], "cap": 9}]},
    {"categories": [{"key": "a_b", "label": "x", "sections": ["S"], "extra": 1}]},
    {"categories": [{"key": "a_b", "label": "x", "sections": ["S"]},
                    {"key": "a_b", "label": "y", "sections": ["T"]}]},
    {"categories": [{"key": "a_b", "label": "x", "sections": ["S"]},
                    {"key": "c_d", "label": "y", "sections": ["S"]}]},   # section in two categories
    {"deductions": {"minor": 1, "major": 0.5, "critical": 3}},            # not increasing
    {"deductions": {"minor": -1, "major": 1, "critical": 3}},
    {"deductions": {"minor": 0.25, "major": 1}},
    {"thresholds": {"excellent": 3, "good": 3.5, "average": 2.5}},          # not descending
    {"thresholds": {"excellent": 6, "good": 3.5, "average": 2.5}},
    {"surprise": 1},
])
def test_bad_configs_are_rejected(cfg):
    with pytest.raises(ValueError):
        validate_config(cfg)
