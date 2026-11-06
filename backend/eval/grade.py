"""Deterministic grading: the final ANSWER line against facts from the snapshot.

No LLM judge. Standard memory judges accept vague answers, and this one can't:
the answer has to be exactly the right set.
"""

from __future__ import annotations

import re

_ANSWER_LINE = re.compile(r"^\W*ANSWER\W*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)


def normalize(item: str) -> str:
    """'PR #3858' -> '3858', '`src/click/types.py`' -> 'types.py', '@Bob' -> 'bob'."""
    item = item.strip().strip("`*'\". ").lower()
    item = re.sub(r"^(pr|pull request|issue|commit)\s+", "", item).lstrip("#@")
    return item.rsplit("/", 1)[-1]


def parse_answer(text: str) -> set[str] | None:
    """Items on the last ANSWER line, or None if the model didn't give one."""
    lines = _ANSWER_LINE.findall(text or "")
    if not lines:
        return None
    return {normalize(i) for i in lines[-1].split(",") if normalize(i)}


def grade(text: str, gold: list[str]) -> dict:
    """correct = exact set match. f1 shows partial credit on list questions."""
    got = parse_answer(text)
    want = {normalize(g) for g in gold}
    if got is None:
        return {"correct": False, "f1": 0.0, "got": None}
    hits = len(got & want)
    f1 = 2 * hits / (len(got) + len(want)) if got or want else 1.0
    return {"correct": got == want, "f1": round(f1, 3), "got": sorted(got)}
