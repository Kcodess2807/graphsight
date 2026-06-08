"""Headless ingest entry point.

    python -m scripts.ingest --datasets datasets --db memory.lbug
    python scripts/ingest.py --reset
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracerag import config                       # noqa: E402
from tracerag.db import TraceDB                    # noqa: E402
from tracerag.extract import EntityExtractor       # noqa: E402
from tracerag.curation import CurationEngine, IngestStats  # noqa: E402

logger = logging.getLogger("tracerag.ingest")


@dataclass(frozen=True)
class Document:
    doc_id: str
    text: str
    meta: dict


def load_documents(datasets_dir: Path) -> Iterator[Document]:
    if not datasets_dir.exists():
        logger.warning("Datasets dir does not exist: %s", datasets_dir)
        return

    for path in sorted(datasets_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        rel = path.relative_to(datasets_dir).as_posix()
        try:
            if suffix in (".md", ".markdown"):
                yield _load_markdown(path, rel)
            elif suffix == ".json":
                yield from _load_json(path, rel)
            elif suffix == ".pdf":
                yield _load_pdf(path, rel)
            else:
                logger.debug("Skipping unsupported file: %s", rel)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load %s: %s", rel, exc)


def _load_markdown(path: Path, rel: str) -> Document:
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta, body = {}, raw
    try:
        import frontmatter

        post = frontmatter.loads(raw)
        meta, body = dict(post.metadata), post.content
    except Exception:  # noqa: BLE001
        pass
    return Document(doc_id=rel, text=body, meta=meta)


def _load_json(path: Path, rel: str) -> Iterator[Document]:
    # arrays -> one Document per record
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    records = data if isinstance(data, list) else [data]
    for i, rec in enumerate(records):
        if isinstance(rec, dict):
            text = "\n".join(f"{k}: {v}" for k, v in _flatten(rec).items())
            doc_id = f"{rel}#{rec.get('key', rec.get('id', i))}"
        else:
            text, doc_id = str(rec), f"{rel}#{i}"
        yield Document(doc_id=doc_id, text=text, meta={"source_file": rel})


def _load_pdf(path: Path, rel: str) -> Document:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return Document(doc_id=rel, text=text, meta={"pages": len(reader.pages)})


def _flatten(obj: dict, prefix: str = "") -> dict:
    out: dict = {}
    for k, v in obj.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, f"{key}."))
        elif isinstance(v, list):
            out[key] = ", ".join(str(x) for x in v)
        else:
            out[key] = v
    return out


def ingest_text(
    engine: CurationEngine,
    extractor: EntityExtractor,
    doc_id: str,
    text: str,
    source: str | None = None,
) -> IngestStats:
    """Run one text blob through extraction -> curation -> graph write.

    Callers must invoke ``db.build_vector_index()`` once after the final document.
    """
    entities = extractor.extract(text)
    return engine.ingest(doc_id, text, entities, source=source)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TraceRAG headless ingest.")
    p.add_argument("--datasets", type=Path, default=config.DATASETS_DIR)
    p.add_argument("--db", type=Path, default=config.DB_PATH)
    p.add_argument("--reset", action="store_true",
                   help="Delete the existing .lbug file before ingesting.")
    p.add_argument("--dry-run", action="store_true",
                   help="Extract and report entities without writing.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )
    for noisy in ("httpx", "httpcore", "openai", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.reset:
        # remove the .lbug file plus its .wal/.lock/.tmp sidecars
        for p in sorted(args.db.parent.glob(args.db.name + "*")):
            logger.info("Reset: removing %s", p)
            p.unlink()

    extractor = EntityExtractor()
    db = TraceDB(args.db)
    db.init_schema()
    engine = None if args.dry_run else CurationEngine(db)

    totals = IngestStats()
    try:
        for doc in load_documents(args.datasets):
            entities = extractor.extract(doc.text)
            logger.info("%-40s  %3d entities", doc.doc_id, len(entities))

            if args.dry_run:
                totals.docs += 1
                totals.entities += len(entities)
                continue

            stats = engine.ingest(doc.doc_id, doc.text, entities)
            totals.merge(stats)
            logger.debug("  %s", stats)

        if not args.dry_run:
            db.build_vector_index()

        logger.info(
            "Done. %d docs, %d entities | created=%d fast=%d deep_yes=%d "
            "deep_no=%d ollama=%d | rel=%d mentions=%d | nodes_in_db=%d",
            totals.docs, totals.entities, totals.created, totals.fast_merged,
            totals.deep_merged_yes, totals.deep_merged_no, totals.ollama_calls,
            totals.relates_edges, totals.mentions_edges, db.count_nodes(),
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
