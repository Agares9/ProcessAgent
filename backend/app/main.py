"""文枢后端入口（FastAPI）。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest
from starlette.responses import Response

from app.api.router import root_router
from app.config import get_settings
from app.deps import build_container
from app.utils.logging import get_logger, setup_logging
from app.loop.default_skills import seed_default_skills

logger = get_logger(__name__)


def _is_placeholder_key(value: str) -> bool:
    value = value.strip().lower()
    return not value or value in {"changeme", "change-me"} or (value.startswith("sk-") and set(value[3:]) <= {"x"})


async def validate_llm_runtime(container) -> None:
    """Fail startup unless the configured LLM can answer a minimal request."""
    settings = container.settings
    if _is_placeholder_key(settings.deepseek_api_key):
        raise RuntimeError("DEEPSEEK_API_KEY 未配置或仍为样例值")
    if not settings.deepseek_base_url.strip() or not settings.deepseek_model.strip():
        raise RuntimeError("DeepSeek base URL 或模型名称未配置")
    try:
        reply = await asyncio.wait_for(
            container.llm.complete(
                [{"role": "user", "content": "只回复 OK"}], temperature=0, max_tokens=4
            ),
            timeout=settings.startup_llm_timeout,
        )
    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"LLM 启动检查超时（{settings.startup_llm_timeout:g}s）") from exc
    if not reply.strip():
        raise RuntimeError("LLM 启动检查返回空响应")


async def validate_knowledge_runtime(container) -> dict[str, int]:
    """Verify embedding, knowledge documents and vector index are usable."""
    provider = str(getattr(container.settings, "embedding_provider", "")).lower()
    if provider == "hash":
        raise RuntimeError("生产运行不能使用 hash Embedding")
    if provider == "relay" and not getattr(container.settings, "relay_api_key", ""):
        raise RuntimeError("Embedding provider=relay 但 RELAY_API_KEY 未配置")
    vector = await container.embeddings.embed_query("ProcessAgent 启动检查")
    if not vector:
        raise RuntimeError("Embedding 启动检查返回空向量")
    chunks = await container.store.list_active_chunks()
    vector_count = await container.vector_store.count()
    if container.settings.require_knowledge_base and not chunks:
        raise RuntimeError("知识库为空：未找到 active chunks")
    if chunks and vector_count < len(chunks):
        raise RuntimeError(f"向量索引不完整：vectors={vector_count}, active_chunks={len(chunks)}")
    if vector_count:
        try:
            await container.vector_store.search(vector, top_k=1)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Embedding 与向量索引不兼容: {exc}") from exc
    return {"active_chunks": len(chunks), "vectors": vector_count, "embedding_dim": len(vector)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    container = build_container(settings)
    app.state.container = container
    app.state.readiness = {"status": "starting", "components": {}}

    logger.info(
        "运行路径: sqlite=%s, chroma=%s, uploads=%s",
        settings.sqlite_path, settings.chroma_path, settings.upload_storage_dir,
    )

    # 连接外部依赖（memory 模式跳过）
    if container.mongo is not None:
        try:
            await container.mongo.connect()
        except Exception as exc:  # noqa: BLE001
            logger.error("MongoDB 连接失败: %s", exc)
    if hasattr(container.session_store, "connect"):
        try:
            await container.session_store.connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 连接失败(%s)，会话回退内存", exc)

    try:
        await validate_llm_runtime(container)
        app.state.readiness["components"]["llm"] = "ready"
    except Exception as exc:
        app.state.readiness = {"status": "not_ready", "components": {"llm": "failed"}, "error": str(exc)}
        logger.error("LLM 启动检查失败: %s", exc)
        raise

    # 种子默认 Rules / Hooks
    await container.rule_engine.seed_defaults()
    await container.hook_engine.seed_defaults()
    seeded_skills = await seed_default_skills(container.store)
    if seeded_skills:
        logger.info("已创建 %d 个可执行基线 Skills", seeded_skills)

    # 种子账号（学生/管理员）
    await container.auth.seed_users()

    # 回填部门 Loop 阶段与审核统计字段（兼容旧数据）
    await _backfill_departments(container)

    # 重建内存检索索引（BM25 + 向量）：MongoDB 中已入库的文档可跨进程/重启被检索
    try:
        chunks = await container.store.list_active_chunks()
        if chunks:
            for c in chunks:
                container.bm25.add(c)
            # 持久向量库已有完整索引时只重建 BM25，避免启动时重复计算全量 embedding。
            persistent_vectors_ready = settings.vector_backend in {"mongo", "chroma"} and (
                await container.vector_store.count()
            ) >= len(chunks)
            if not persistent_vectors_ready:
                texts = [c["content"] for c in chunks]
                vectors = await container.embeddings.embed(texts)
                for c, v in zip(chunks, vectors):
                    await container.vector_store.add(
                        c["embedding_id"],
                        v,
                        {"doc_id": c["doc_id"], "dept_id": c["dept_id"], "chunk_index": c["chunk_index"]},
                    )
            logger.info(
                "重建检索索引完成: %d chunks (BM25%s)",
                len(chunks), "，复用持久向量" if persistent_vectors_ready else " + 向量",
            )
        else:
            logger.info("无已入库文档，跳过检索索引重建")
    except Exception as exc:  # noqa: BLE001
        logger.warning("重建检索索引失败(%s)，检索可能不完整", exc)

    try:
        knowledge = await validate_knowledge_runtime(container)
        app.state.readiness["components"].update({
            "embedding": "ready", "storage": "ready", "vector_store": "ready", "knowledge_base": "ready"
        })
        app.state.readiness["details"] = knowledge
    except Exception as exc:
        app.state.readiness = {
            "status": "not_ready", "components": {**app.state.readiness.get("components", {}), "knowledge_base": "failed"},
            "error": str(exc),
        }
        logger.error("知识运行时启动检查失败: %s", exc)
        raise

    app.state.readiness["status"] = "ready"
    logger.info("%s 启动完成 (storage=%s)", settings.app_name, settings.storage_mode)
    yield

    # 关闭
    if container.mongo is not None:
        await container.mongo.close()
    if hasattr(container.session_store, "close"):
        await container.session_store.close()
    await container.pi_runtime.close()
    logger.info("应用已关闭")


async def _backfill_departments(container) -> None:
    """为已存在的部门补充 loop_phase / review_stats / fade_out 字段（幂等）。"""
    from datetime import datetime, timezone

    try:
        for dept in await container.store.list_departments():
            changed = False
            if "loop_phase" not in dept:
                dept["loop_phase"] = "human_in_loop"
                changed = True
            if "review_stats" not in dept:
                dept["review_stats"] = {"total": 0, "correct": 0, "accuracy": 0.0}
                changed = True
            if "admin_users" not in dept:
                dept["admin_users"] = []
                changed = True
            if changed:
                dept["updated_at"] = datetime.now(timezone.utc).isoformat()
                await container.store.upsert_department(dept)
        logger.info("部门 Loop 阶段字段回填完成")
    except Exception as exc:  # noqa: BLE001
        logger.warning("部门字段回填失败: %s", exc)


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

# CORS：显式来源列表；通配符来源不允许携带凭据（浏览器规范）
_cors_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials="*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(root_router)


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4")


@app.get("/")
async def index():
    return {"app": settings.app_name, "docs": "/docs", "health": "/healthz"}
