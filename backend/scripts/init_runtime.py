"""启动 ProcessAgent 前的最小运行时自检。

用法：
    python -m scripts.init_runtime

检查会复用生产 FastAPI lifespan，因此不会复制容器初始化逻辑。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


def mask(value: str) -> str:
    return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "已配置"


async def check() -> int:
    from app.config import get_settings
    from app.main import app, lifespan

    settings = get_settings()
    print(f"[init] storage={settings.storage_mode}, vector={settings.vector_backend}, embedding={settings.embedding_provider}")
    if not settings.deepseek_api_key:
        print("[init] ERROR: DEEPSEEK_API_KEY 未配置", file=sys.stderr)
        return 1
    print(f"[init] DeepSeek key: {mask(settings.deepseek_api_key)}")

    try:
        async with lifespan(app):
            container = app.state.container
            await container.embeddings.embed(["ProcessAgent 初始化检查"])
            print("[init] SQLite/Chroma/Embedding 检查通过")
    except Exception as exc:  # noqa: BLE001
        print(f"[init] ERROR: {exc}", file=sys.stderr)
        if settings.embedding_provider == "local" and not settings.embedding_local_only:
            print("[init] 提示: 本地模型可用时请设置 EMBEDDING_LOCAL_ONLY=true", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ProcessAgent runtime before starting web_app")
    parser.add_argument("--offline", action="store_true", help="强制本地模型离线加载")
    args = parser.parse_args()
    if args.offline:
        os.environ["EMBEDDING_LOCAL_ONLY"] = "true"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return asyncio.run(check())


if __name__ == "__main__":
    raise SystemExit(main())
