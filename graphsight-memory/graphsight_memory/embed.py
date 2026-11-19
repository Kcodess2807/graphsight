"""One embedder for every write and every query, so they share one vector space.

fastembed runs MiniLM on ONNX in about 190 MB with no torch. Its vectors match
sentence-transformers' to five decimals, so graphs built either way still work.
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Callable

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def _normalize(vec) -> list[float]:
    norm = sum(float(x) * float(x) for x in vec) ** 0.5 or 1.0
    return [float(x) / norm for x in vec]


@lru_cache(maxsize=4)
def embedder(model: str) -> Callable[[str], list[float]]:
    """text -> unit vector. fastembed when installed, else sentence-transformers."""
    name = model if "/" in model else f"sentence-transformers/{model}"
    try:
        from fastembed import TextEmbedding
    except ImportError:
        TextEmbedding = None
    if TextEmbedding is not None:
        logger.info("Loading embedder %s (onnx)", name)
        onnx = TextEmbedding(name)

        def encode(text: str) -> list[float]:
            # ponytail: one lock around ONNX; a session per thread if embeds ever queue
            with _lock:
                return _normalize(next(iter(onnx.embed([text]))))
        return encode
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "No embedder installed. pip install graphsight-memory (fastembed) "
            "or sentence-transformers.") from None
    logger.info("Loading embedder %s (torch)", name)
    torch_model = SentenceTransformer(name)
    return lambda text: [float(x) for x in torch_model.encode(text, normalize_embeddings=True)]
