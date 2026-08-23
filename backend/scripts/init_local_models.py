"""首次部署时下载并验证本地 Embedding 模型。"""
from __future__ import annotations

import argparse
import os
import time

from sentence_transformers import SentenceTransformer


def main() -> int:
    parser = argparse.ArgumentParser(description="下载并缓存本地 Embedding 模型")
    parser.add_argument("--model", default=os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"))
    args = parser.parse_args()
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    started = time.time()
    print(f"正在初始化模型: {args.model}")
    model = SentenceTransformer(args.model)
    vector = model.encode(["制造业模型初始化测试"], normalize_embeddings=True)
    print(f"初始化完成，维度={vector.shape[1]}，耗时={time.time() - started:.2f}s")
    print("后续可将 EMBEDDING_LOCAL_ONLY=true 切换为严格离线运行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
