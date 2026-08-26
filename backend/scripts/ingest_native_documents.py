"""直接解析并入库原生 PDF/DOCX/Markdown/HTML/TXT 文档。

原始文件保持不变；脚本只读取文件，并在文档及 chunk 元数据中写入行业标签。
"""
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

SUFFIXES = {".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入原生金融/行业文档到本地 SQLite 与 Chroma")
    parser.add_argument("--source", required=True, help="原生文档目录或单个文件")
    parser.add_argument("--industry", required=True, help="行业标识，例如 finance")
    parser.add_argument("--business-domain", default="auto", help="细分领域；默认按文件名自动判断")
    parser.add_argument("--dept-id", default="dept_all")
    parser.add_argument("--sqlite-path", default="../local-data/processagent.db")
    parser.add_argument("--chroma-path", default="../local-data/chroma")
    parser.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--embedding-provider", choices=["local", "hash"], default="local")
    parser.add_argument("--embedding-dim", type=int, default=512)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> int:
    source = Path(args.source).resolve()
    files = [source] if source.is_file() else sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES)
    if args.limit > 0:
        files = files[: args.limit]
    print(f"发现 {len(files)} 个原生文档")
    if args.dry_run:
        for path in files:
            domain = infer_finance_domain(path) if args.industry == "finance" and args.business_domain == "auto" else args.business_domain
            print(f"{path} | domain={domain} | class={infer_document_class(path)}")
        return 0
    settings = Settings(storage_mode="sqlite", sqlite_path=args.sqlite_path, vector_backend="chroma", chroma_path=args.chroma_path,
                         embedding_provider=args.embedding_provider, embedding_model=args.embedding_model, embedding_dim=args.embedding_dim,
                         embedding_local_only=args.embedding_provider == "local",
                         reranker_enabled=False)
    store = SQLiteStore(settings.sqlite_path)
    vectors = ChromaVectorStore(path=settings.chroma_path)
    embeddings = EmbeddingClient(settings, relay=None)
    indexer = Indexer(store, vectors, embeddings, BM25Index())
    ok = failed = 0
    for path in files:
        try:
            business_domain = infer_finance_domain(path) if args.industry == "finance" and args.business_domain == "auto" else args.business_domain
            metadata = {"industry": args.industry, "business_domain": business_domain, "source_kind": "native_document", "document_class": infer_document_class(path)}
            doc = await indexer.ingest(path, dept_id=args.dept_id, uploaded_by="native-import", metadata=metadata)
            print(f"[ok] {path.name} -> {doc.get('_id')} ({doc.get('chunk_count', 0)} chunks)")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[fail] {path.name}: {exc}")
            failed += 1
    print(f"完成: 成功 {ok}，失败 {failed}")
    return 0 if failed == 0 else 1


def infer_finance_domain(path: Path) -> str:
    name = path.name.lower()
    risk_terms = ("风险", "监管", "合规", "尽职调查", "偿付能力", "资本管理", "流动性", "消费者权益", "适当性", "risk", "compliance", "due diligence", "capital", "liquidity", "operational")
    return "risk_compliance" if any(term in name for term in risk_terms) else "operations"


def infer_document_class(path: Path) -> str:
    name = path.name.lower()
    if any(term in name for term in ("办法", "规则", "管理", "监管", "framework", "standard", "guide")):
        return "regulation_or_standard"
    if any(term in name for term in ("规划", "概述", "投资", "产业")):
        return "industry_report"
    return "reference"


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
