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


# spaCy/EntityRuler label -> domain type (whitelisted labels only; see
# config.SPACY_ALLOWED_LABELS). Anything not here is dropped at the source.
_SPACY_LABEL_MAP = {
    # Statistical NER
    "PERSON": "Person",
    "ORG": "Service",
    "PRODUCT": "Tool",
    "GPE": "Location",
    # Deterministic EntityRuler
    "TICKET": "Ticket",
    "PULL_REQUEST": "PR",
    "SERVICE": "Service",
}

# Deterministic regex/token patterns for structured engineering entities,
# matched by an EntityRuler placed BEFORE the statistical `ner` (so the ruler
# wins). Inline (?i) flags sit at the start of each regex (Python 3.11+ rule).
_RULER_LABELS = frozenset({"TICKET", "PULL_REQUEST", "SERVICE"})
_ENTITY_RULER_PATTERNS = [
    # Any Jira project key: INC-123, OPS-456, SRCTREEWIN-14221, JRASERVER-9
    {"label": "TICKET",
     "pattern": [{"TEXT": {"REGEX": r"(?i)^[A-Z][A-Z0-9]+-\d+$"}}]},
    # PR #402, PR 402
    {"label": "PULL_REQUEST",
     "pattern": [{"LOWER": "pr"}, {"TEXT": "#", "OP": "?"}, {"IS_DIGIT": True}]},
    # payment-service (single token, if the tokenizer keeps it whole)
    {"label": "SERVICE",
     "pattern": [{"TEXT": {"REGEX": r"(?i)^[a-z0-9]+-service$"}}]},
    # payment-service split by spaCy into ["payment", "-", "service"]
    {"label": "SERVICE",
     "pattern": [{"TEXT": {"REGEX": r"(?i)^[a-z0-9]+$"}},
                 {"TEXT": "-"}, {"LOWER": "service"}]},
]

# Leading/trailing markdown & list punctuation to trim off noisy spaCy spans.
_EDGE_JUNK = " \t\r\n-*#•|>:.,;"


def clean_entity_text(raw: str) -> str | None:
    """Sanitize an extracted surface form; return cleaned text or None to drop.

    Drops spans that are empty, too short, purely numeric, or made only of
    special characters / leading punctuation — the markdown & number noise that
    turns the fallback graph into a hairball.
    """
    if not raw:
        return None
    # Collapse internal whitespace/newlines, then trim edge punctuation.
    text = re.sub(r"\s+", " ", raw).strip().strip(_EDGE_JUNK).strip()
    if len(text) < config.MIN_ENTITY_CHARS:
        return None
    if re.fullmatch(r"[\W_]+", text):          # only special chars
        return None
    if re.fullmatch(r"[\d.,%$]+", text):       # entirely numeric (2026, 1,000, 50%)
        return None
    if not text[0].isalnum():                  # starts with a special char (#, -, *)
        return None
    return text


class EntityExtractor:
    """Extracts domain entities. GLiNER first; degrades to spaCy if unavailable."""

    def __init__(
        self,
        labels: list[str] | None = None,
        threshold: float = config.GLINER_THRESHOLD,
        prefer_gliner: bool = True,
    ) -> None:
        self.labels = labels or config.ENTITY_LABELS
        self.threshold = threshold
        # Set False for query-time use (the router): query-side entity linking
        # only needs the deterministic spaCy EntityRuler to spot ticket/PR/
        # service mentions. Loading the ~750MB GLiNER transformer per request is
        # pure waste and, under concurrent requests, exhausts the Windows commit
        # limit (os error 1455). GLiNER belongs at ingest time, not query time.
        self._prefer_gliner = prefer_gliner
        self._gliner = None
        self._spacy = None
        self._gliner_failed = False

    # --- lazy model loaders -------------------------------------------- #
    def _get_gliner(self):
        if not self._prefer_gliner:
            return None
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
                nlp = spacy.load(config.SPACY_MODEL)
            except OSError as exc:
                raise RuntimeError(
                    f"spaCy model '{config.SPACY_MODEL}' not found. "
                    f"Run: python -m spacy download {config.SPACY_MODEL}"
                ) from exc
            # Deterministic engineering entities take priority: the ruler runs
            # BEFORE `ner`, so the statistical model respects its spans.
            if "entity_ruler" not in nlp.pipe_names:
                ruler = nlp.add_pipe("entity_ruler", before="ner")
                ruler.add_patterns(_ENTITY_RULER_PATTERNS)
            self._spacy = nlp
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
                clean = clean_entity_text(p["text"])
                if clean is None:
                    continue
                found.append(ExtractedEntity(
                    text=clean,
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
                # Ontology enforcement: whitelist high-signal labels, drop the
                # date/number/quantity noise.
                if ent.label_ not in config.SPACY_ALLOWED_LABELS:
                    continue
                if ent.label_ in config.SPACY_BLOCKED_LABELS:
                    continue
                if ent.label_ in _RULER_LABELS:
                    # Deterministic match — trust it, just trim whitespace.
                    clean = ent.text.strip()
                    if not clean:
                        continue
                    # Canonicalize ticket keys so 'srctreewin-14221' and
                    # 'SRCTREEWIN-14221' resolve to the exact same node.
                    if ent.label_ == "TICKET":
                        clean = clean.upper()
                else:
                    # Statistical NER — sanitize (drop numerics, <3 chars, junk).
                    clean = clean_entity_text(ent.text)
                    if clean is None:
                        continue
                found.append(ExtractedEntity(
                    text=clean,
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
