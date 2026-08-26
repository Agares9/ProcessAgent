"""使用本地 Embedding 模型重建已入库文档的向量，不重新解析原文。"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.config import Settings
from app.llm.embeddings import EmbeddingClient
from app.pipeline.indexer import Indexer
from app.retrieval.bm25 import BM25Index
from app.retrieval.vector_store import ChromaVectorStore
from app.storage.store import SQLiteStore


async def run(args: argparse.Namespace) -> int:
    settings = Settings(storage_mode="sqlite", sqlite_path=args.sqlite_path, vector_backend="chroma", chroma_path=args.chroma_path,
                        embedding_provider="local", embedding_model=args.model, embedding_dim=512, embedding_local_only=True,
                        reranker_enabled=False)
    store = SQLiteStore(settings.sqlite_path)
    indexer = Indexer(store, ChromaVectorStore(path=settings.chroma_path), EmbeddingClient(settings), BM25Index())
    names = {p.name for p in Path(args.source).glob("*.pdf")} if args.source else set()
    docs = await store.list_documents(status="active")
    selected = [d for d in docs if not names or (d.get("source") or {}).get("file_name") in names]
    if args.limit > 0:
        selected = selected[:args.limit]
    print(f"待重建文档: {len(selected)}")
    ok = failed = 0
    for doc in selected:
        try:
            await indexer.reindex(doc["_id"])
            ok += 1
            print(f"[ok] {doc.get('title', doc['_id'])}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[fail] {doc.get('title', doc['_id'])}: {exc}")
    print(f"完成: 成功 {ok}，失败 {failed}")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="使用本地 BGE 模型重建向量")
    parser.add_argument("--source", default="../文档/金融", help="用于按文件名筛选已入库文档")
    parser.add_argument("--sqlite-path", default="../local-data/processagent.db")
    parser.add_argument("--chroma-path", default="../local-data/chroma")
    parser.add_argument("--model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--limit", type=int, default=0)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
