"""Entity extraction: GLiNER (zero-shot, primary) with spaCy fallback.

GLiNER has a strict context window, so all text runs through a word-based
sliding window; spans re-project to absolute char offsets and de-dupe.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterator

from . import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractedEntity:
    text: str          # surface form
    type: str          # config.ENTITY_LABELS (or spaCy label in fallback)
    score: float       # confidence in [0, 1]
    start: int         # absolute char offset
    end: int           # absolute char offset (exclusive)
    source: str        # "gliner" | "spacy"


@dataclass(frozen=True)
class _WordWindow:
    text: str
    offset: int  # absolute char offset where this window begins


def sliding_window_words(
    text: str,
    window: int = config.GLINER_WINDOW_WORDS,
    overlap: int = config.GLINER_WINDOW_OVERLAP,
) -> Iterator[_WordWindow]:
    """Yield overlapping word windows tagged with their char offset."""
    if overlap >= window:
        raise ValueError("overlap must be smaller than window")

    tokens = [(m.group(0), m.start()) for m in re.finditer(r"\S+", text)]
    if not tokens:
        return

    step = window - overlap
    for i in range(0, len(tokens), step):
        chunk = tokens[i : i + window]
        if not chunk:
            break
        start_char = chunk[0][1]
        last_word, last_start = chunk[-1]
        end_char = last_start + len(last_word)
        yield _WordWindow(text=text[start_char:end_char], offset=start_char)
        if i + window >= len(tokens):
            break


# Best-effort spaCy label -> domain type (fallback only).
_SPACY_LABEL_MAP = {
    "PERSON": "Person",
    "ORG": "Team",
    "PRODUCT": "Tool",
    "WORK_OF_ART": "Tool",
    "FAC": "Service",
}


class EntityExtractor:
    """Extracts domain entities. GLiNER first; degrades to spaCy if unavailable."""

    def __init__(
        self,
        labels: list[str] | None = None,
        threshold: float = config.GLINER_THRESHOLD,
    ) -> None:
        self.labels = labels or config.ENTITY_LABELS
        self.threshold = threshold
        self._gliner = None
        self._spacy = None
        self._gliner_failed = False

    # --- lazy model loaders -------------------------------------------- #
    def _get_gliner(self):
        if self._gliner is None and not self._gliner_failed:
            try:
                from gliner import GLiNER

                logger.info("Loading GLiNER model: %s", config.GLINER_MODEL)
                self._gliner = GLiNER.from_pretrained(config.GLINER_MODEL)
            except Exception as exc:  # noqa: BLE001
                logger.warning("GLiNER unavailable (%s); using spaCy.", exc)
                self._gliner_failed = True
        return self._gliner

    def _get_spacy(self):
        if self._spacy is None:
            import spacy

            try:
                logger.info("Loading spaCy model: %s", config.SPACY_MODEL)
                self._spacy = spacy.load(config.SPACY_MODEL)
            except OSError as exc:
                raise RuntimeError(
                    f"spaCy model '{config.SPACY_MODEL}' not found. "
                    f"Run: python -m spacy download {config.SPACY_MODEL}"
                ) from exc
        return self._spacy

    # --- public API ---------------------------------------------------- #
    def extract(self, text: str) -> list[ExtractedEntity]:
        if not text or not text.strip():
            return []
        model = self._get_gliner()
        if model is not None:
            return self._extract_gliner(text, model)
        return self._extract_spacy(text)

    # --- GLiNER -------------------------------------------------------- #
    def _extract_gliner(self, text: str, model) -> list[ExtractedEntity]:
        found: list[ExtractedEntity] = []
        for win in sliding_window_words(text):
            try:
                preds = model.predict_entities(
                    win.text, self.labels, threshold=self.threshold
                )
            except Exception as exc:  # noqa: BLE001 — skip bad window, keep doc
                logger.warning("GLiNER failed on a window (%s); skipping.", exc)
                continue
            for p in preds:
                found.append(ExtractedEntity(
                    text=p["text"].strip(),
                    type=p["label"],
                    score=float(p.get("score", 1.0)),
                    start=win.offset + p["start"],
                    end=win.offset + p["end"],
                    source="gliner",
                ))
        return self._dedupe(found)

    # --- spaCy fallback ------------------------------------------------ #
    def _extract_spacy(self, text: str) -> list[ExtractedEntity]:
        nlp = self._get_spacy()
        found: list[ExtractedEntity] = []
        for win in sliding_window_words(text):
            for ent in nlp(win.text).ents:
                found.append(ExtractedEntity(
                    text=ent.text.strip(),
                    type=_SPACY_LABEL_MAP.get(ent.label_, ent.label_),
                    score=1.0,
                    start=win.offset + ent.start_char,
                    end=win.offset + ent.end_char,
                    source="spacy",
                ))
        return self._dedupe(found)

    # --- dedup --------------------------------------------------------- #
    @staticmethod
    def _dedupe(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        # Surface-level only (highest score per text+type); semantic
        # canonicalisation is curation.py's job.
        best: dict[tuple[str, str], ExtractedEntity] = {}
        for e in entities:
            if not e.text:
                continue
            key = (e.text.lower(), e.type)
            cur = best.get(key)
            if cur is None or e.score > cur.score:
                best[key] = e
        return sorted(best.values(), key=lambda e: (e.start, e.text))
