"""Import processed manufacturing JSON/JSONL into local SQLite and Chroma."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config import Settings
from app.llm.embeddings import EmbeddingClient
from app.pipeline.manufacturing_importer import import_prepared_documents, prepare_dataset
from app.retrieval.vector_store import ChromaVectorStore
from app.storage.store import SQLiteStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import preprocessed manufacturing data into local RAG stores")
    parser.add_argument("--source", default="../manufacturing-data")
    parser.add_argument("--sqlite-path", default="../local-data/processagent.db")
    parser.add_argument("--chroma-path", default="../local-data/chroma")
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--embedding-provider", choices=["local", "hash"], default="local")
    parser.add_argument("--embedding-dim", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--limit-documents", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default="../local-data/import-report.json")
    return parser


async def run(args: argparse.Namespace) -> int:
    prepared, report = prepare_dataset(Path(args.source), args.limit_documents)
    if not args.dry_run:
        settings = Settings(
            storage_mode="sqlite",
            sqlite_path=args.sqlite_path,
            vector_backend="chroma",
            chroma_path=args.chroma_path,
            embedding_provider=args.embedding_provider,
            embedding_model=args.embedding_model,
            embedding_dim=args.embedding_dim,
            reranker_enabled=False,
        )
        store = SQLiteStore(settings.sqlite_path)
        vector_store = ChromaVectorStore(path=settings.chroma_path)
        embeddings = EmbeddingClient(settings, relay=None)
        await import_prepared_documents(
            prepared, report, store, vector_store, embeddings, batch_size=args.batch_size
        )

    output = report.to_dict()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "issues"}, ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
