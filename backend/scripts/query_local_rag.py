"""Run a local semantic search against SQLite + Chroma manufacturing data."""
from __future__ import annotations

import argparse
import asyncio

from app.config import Settings
from app.llm.embeddings import EmbeddingClient
from app.retrieval.vector_store import ChromaVectorStore
from app.storage.store import SQLiteStore


async def run(args: argparse.Namespace) -> int:
    settings = Settings(
        embedding_provider="local",
        embedding_model=args.embedding_model,
        embedding_dim=512,
    )
    store = SQLiteStore(args.sqlite_path)
    vectors = ChromaVectorStore(path=args.chroma_path)
    embeddings = EmbeddingClient(settings, relay=None)

    query_vector = await embeddings.embed_query(args.query)
    hits = await vectors.search(query_vector, top_k=args.top_k)
    print(
        f"documents={await store.count('documents')} "
        f"chunks={await store.count('chunks')} vectors={await vectors.count()}"
    )
    for rank, hit in enumerate(hits, start=1):
        chunk = await store.get("chunks", hit["id"])
        document = await store.get_document(hit.get("doc_id", ""))
        if not chunk:
            continue
        metadata = chunk.get("metadata") or {}
        page_start = metadata.get("page_start")
        page_end = metadata.get("page_end")
        page = str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
        print(f"\n[{rank}] score={hit['score']:.4f} title={document.get('title', '') if document else ''}")
        print(f"    doc_id={hit.get('doc_id', '')} page={page} process={metadata.get('process', '')}")
        print(f"    {chunk['content'][:args.preview_chars].replace(chr(10), ' ')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Search the local ProcessAgent manufacturing RAG index")
    parser.add_argument("query")
    parser.add_argument("--sqlite-path", default="../local-data/processagent.db")
    parser.add_argument("--chroma-path", default="../local-data/chroma")
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--preview-chars", type=int, default=240)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
