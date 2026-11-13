"""The grader decides every eval number, so its edge cases are pinned here."""
import pytest

from eval.grade import grade, normalize, parse_answer


@pytest.mark.parametrize("raw,want", [
    ("PR #3858", "3858"),
    ("Issue #3822", "3822"),
    ("`src/click/types.py`", "types.py"),
    ("@Rowlando13", "rowlando13"),
    ("**kdeldycke**", "kdeldycke"),
    ("the completion team", "completion team"),
])
def test_normalize(raw, want):
    assert normalize(raw) == want


def test_uses_the_last_answer_line():
    text = "ANSWER: 1\nActually, on reflection.\nANSWER: PR #2, PR #3"
    assert parse_answer(text) == {"2", "3"}


def test_no_answer_line_is_wrong_not_a_crash():
    assert grade("I think it was PR #1", ["PR #1"]) == {"correct": False, "f1": 0.0, "got": None}


def test_listing_extra_items_fails_exact_match():
    """The vague-answer loophole: naming every PR must not pass."""
    result = grade("ANSWER: PR #1, PR #2", ["PR #1"])
    assert not result["correct"]
    assert result["f1"] == pytest.approx(0.667, abs=0.001)


def test_order_and_format_do_not_matter():
    assert grade("ANSWER: `b.py`, a.py", ["src/a.py", "src/b.py"])["correct"]


def test_unknown_must_be_said_on_unanswerable_tasks():
    assert grade("ANSWER: unknown", ["unknown"])["correct"]
    assert not grade("ANSWER: kdeldycke", ["unknown"])["correct"]
