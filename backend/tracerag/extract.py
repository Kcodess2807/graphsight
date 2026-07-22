"""Entity extraction: GLiNER (zero-shot) with spaCy fallback, over sliding windows."""

from __future__ import annotations

import logging
import re
import threading
from collections import OrderedDict
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


# spaCy/EntityRuler label -> domain type; anything not here is dropped
_SPACY_LABEL_MAP = {
    "PERSON": "Person",
    "ORG": "Service",
    "PRODUCT": "Tool",
    "GPE": "Location",
    "TICKET": "Ticket",
    "PULL_REQUEST": "PR",
    "SERVICE": "Service",
}

# patterns for an EntityRuler placed before the statistical ner, so the ruler wins
_RULER_LABELS = frozenset({"TICKET", "PULL_REQUEST", "SERVICE"})
_ENTITY_RULER_PATTERNS = [
    # jira project key: INC-123, OPS-456, SRCTREEWIN-14221
    {"label": "TICKET",
     "pattern": [{"TEXT": {"REGEX": r"(?i)^[A-Z][A-Z0-9]+-\d+$"}}]},
    # PR #402, PR 402
    {"label": "PULL_REQUEST",
     "pattern": [{"LOWER": "pr"}, {"TEXT": "#", "OP": "?"}, {"IS_DIGIT": True}]},
    # payment-service as one token
    {"label": "SERVICE",
     "pattern": [{"TEXT": {"REGEX": r"(?i)^[a-z0-9]+-service$"}}]},
    # payment-service split into ["payment", "-", "service"]
    {"label": "SERVICE",
     "pattern": [{"TEXT": {"REGEX": r"(?i)^[a-z0-9]+$"}},
                 {"TEXT": "-"}, {"LOWER": "service"}]},
]

# leading/trailing markdown & list punctuation to trim off noisy spaCy spans
_EDGE_JUNK = " \t\r\n-*#•|>:.,;"


def clean_entity_text(raw: str) -> str | None:
    """Sanitize an extracted surface form; return cleaned text or None to drop."""
    if not raw:
        return None
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
        # False at query time: linking only needs the ruler, gliner is ingest-only
        self._prefer_gliner = prefer_gliner
        self._gliner = None
        self._spacy = None
        self._gliner_failed = False
        # Query-side extraction is a pure fn of the text and GIL-bound (spaCy),
        # so cache it: repeated queries skip the pass entirely. Disabled for the
        # ingest path (prefer_gliner=True), where every document text is unique.
        self._cache_cap = 0 if prefer_gliner else config.QUERY_EXTRACT_CACHE
        self._cache: "OrderedDict[str, list[ExtractedEntity]]" = OrderedDict()
        self._cache_lock = threading.Lock()

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
                # Entity linking needs only tok2vec + ruler + ner. Excluding the
                # tagger/parser/lemmatizer cuts per-call CPU (and GIL-hold), which
                # is what dominates query latency under concurrency.
                nlp = spacy.load(
                    config.SPACY_MODEL,
                    exclude=["tagger", "parser", "lemmatizer", "attribute_ruler"],
                )
            except OSError as exc:
                raise RuntimeError(
                    f"spaCy model '{config.SPACY_MODEL}' not found. "
                    f"Run: python -m spacy download {config.SPACY_MODEL}"
                ) from exc
            # ruler runs before ner so deterministic spans take priority
            if "entity_ruler" not in nlp.pipe_names:
                ruler = nlp.add_pipe("entity_ruler", before="ner")
                ruler.add_patterns(_ENTITY_RULER_PATTERNS)
            self._spacy = nlp
        return self._spacy

    def extract(self, text: str) -> list[ExtractedEntity]:
        if not text or not text.strip():
            return []
        if self._cache_cap:
            with self._cache_lock:
                cached = self._cache.get(text)
                if cached is not None:
                    self._cache.move_to_end(text)
                    return cached
        model = self._get_gliner()
        if model is not None:
            result = self._extract_gliner(text, model)
        else:
            result = self._extract_spacy(text)
        if self._cache_cap:
            with self._cache_lock:
                self._cache[text] = result
                self._cache.move_to_end(text)
                if len(self._cache) > self._cache_cap:
                    self._cache.popitem(last=False)
        return result

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
                # GLiNER's p["text"] corrupts multi-byte chars (José -> Jos�);
                # re-slice the span from the source using its (correct) offsets.
                raw = win.text[p["start"]:p["end"]] or p["text"]
                clean = clean_entity_text(raw)
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

    def _extract_spacy(self, text: str) -> list[ExtractedEntity]:
        nlp = self._get_spacy()
        found: list[ExtractedEntity] = []
        for win in sliding_window_words(text):
            for ent in nlp(win.text).ents:
                # whitelist high-signal labels, drop date/number/quantity noise
                if ent.label_ not in config.SPACY_ALLOWED_LABELS:
                    continue
                if ent.label_ in config.SPACY_BLOCKED_LABELS:
                    continue
                if ent.label_ in _RULER_LABELS:
                    clean = ent.text.strip()
                    if not clean:
                        continue
                    # canonicalize ticket keys so case variants resolve to one node
                    if ent.label_ == "TICKET":
                        clean = clean.upper()
                else:
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

    @staticmethod
    def _dedupe(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        # surface-level only (best score per text+type); semantic merge is curation's job
        best: dict[tuple[str, str], ExtractedEntity] = {}
        for e in entities:
            if not e.text:
                continue
            key = (e.text.lower(), e.type)
            cur = best.get(key)
            if cur is None or e.score > cur.score:
                best[key] = e
        return sorted(best.values(), key=lambda e: (e.start, e.text))
