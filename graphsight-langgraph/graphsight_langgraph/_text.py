"""Shared lexical bits for overlap scoring and query matching."""
from __future__ import annotations

import re

# base stopwords shared by both matchers; callers extend as needed
STOP = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "was", "were", "are",
    "has", "have", "not", "but", "its", "also", "into", "over", "after",
})

# 3+ chars, must start alphanumeric — used for answer-overlap scoring
WORD_RE = re.compile(r"[a-z0-9][a-z0-9_#-]{2,}")


def tokens(text: str, stop: frozenset[str] = STOP, pattern: re.Pattern = WORD_RE) -> set[str]:
    return {w for w in pattern.findall(text.lower()) if w not in stop}
