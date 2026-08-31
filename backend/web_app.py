"""ProcessAgent 单容器 Web 入口。

aiohttp 同时托管 React 构建产物和轻量任务轮询 API；任务复用 CLI 的企业场景
编排流程，容器仅负责认证、会话和运行时初始化。
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web

from app.llm.errors import StructuredOutputError
from app.main import app as fastapi_app
from app.main import lifespan as backend_lifespan
from scripts.run_manufacturing_agents import run as run_cli_workflow

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_user_id(request: web.Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        user_id = request.app["container"].auth.verify_token(authorization[7:].strip())
        if user_id:
            return user_id
    return "anonymous"


async def json_body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise web.HTTPBadRequest(text="invalid_json") from exc
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="body_must_be_object")
    return body


async def chat_start(request: web.Request) -> web.Response:
    body = await json_body(request)
    query = str(body.get("question") or body.get("query") or "").strip()
    if not query:
        raise web.HTTPBadRequest(text="question_required")
    session_id = str(body.get("session_id") or f"web-{uuid.uuid4().hex[:12]}")
    task_id = uuid.uuid4().hex
    request.app["tasks"][task_id] = {
        "task_id": task_id, "session_id": session_id, "status": "running", "question": query,
        "user_id": token_user_id(request),
        "created_at": now_iso(), "updated_at": now_iso(),
        "progress": {"stage": "dispatch", "label": "正在理解业务问题", "percent": 15, "mode": "协作"},
        "result": None, "error": None,
    }
    task = asyncio.create_task(run_chat_task(request.app, task_id, query, session_id, token_user_id(request)))
    request.app["task_handles"].add(task)
    task.add_done_callback(request.app["task_handles"].discard)
    return web.json_response({"task_id": task_id, "session_id": session_id, "status": "running"})


async def run_chat_task(app: web.Application, task_id: str, query: str, session_id: str, user_id: str) -> None:
    task = app["tasks"].get(task_id)
    if not task:
        return
    try:
        answer_task = asyncio.create_task(
            # Web 与 CLI 共用同一个企业场景入口；不再调用旧制度咨询 Orchestrator。
            run_cli_workflow(
                query,
                top_k=app["container"].settings.hybrid_topk,
                use_llm=True,
                session_id=session_id,
                user_id=user_id,
                runtime=app["container"],
            )
        )
        stages = [
            (2, "retrieval", "正在检索行业资料", 35),
            (7, "analysis", "正在分析数据和约束", 60),
            (15, "analysis", "多个分析任务正在协同处理，复杂问题需要一些时间", 60),
        ]
        started = asyncio.get_running_loop().time()
        while not answer_task.done():
            await asyncio.wait({answer_task}, timeout=1)
            elapsed = asyncio.get_running_loop().time() - started
            if elapsed >= 180:
                answer_task.cancel()
                await asyncio.gather(answer_task, return_exceptions=True)
                raise asyncio.TimeoutError
            for after, stage, label, percent in stages:
                if elapsed >= after:
                    task["progress"] = {"stage": stage, "label": label, "percent": percent, "mode": "协作"}
                    task["updated_at"] = now_iso()
        result = await answer_task
        solution = result.get("solution") or {}
        # CLI 的企业答案位于 solution.executive_summary，Web 保持既有扁平响应契约。
        result["answer"] = result.get("answer") or solution.get("executive_summary", "")
        result["citations"] = result.get("citations") or solution.get("citations", [])
        result["session_id"] = session_id
        task.update({
            "status": "completed", "result": result, "updated_at": now_iso(),
            "progress": {"stage": "reply", "label": "回答已生成", "percent": 100, "mode": "协作"},
        })
    except asyncio.CancelledError:
        task.update({"status": "cancelled", "updated_at": now_iso(), "error": "cancelled"})
        raise
    except asyncio.TimeoutError:
        task.update({
            "status": "failed", "error": "timeout", "updated_at": now_iso(),
            "progress": {"stage": "reply", "label": "系统处理超时", "percent": 100, "mode": "协作"},
            "result": {"answer": "系统处理超时，请简化问题后重试。", "error": "timeout", "session_id": session_id},
        })
    except StructuredOutputError as exc:
        messages = {
            "scenario_intent": "意图识别模型返回格式不符合要求，请重试。",
            "lead_plan": "任务规划模型返回格式不符合要求，请重试。",
        }
        answer = (
            "模型调用失败，请稍后重试。"
            if exc.stage == "transport"
            else messages.get(exc.agent, "模型返回格式不符合要求，请重试。")
        )
        task.update({
            "status": "failed", "error": "structured_output_invalid", "error_code": "structured_output_invalid",
            "agent": exc.agent, "updated_at": now_iso(),
            "progress": {"stage": "reply", "label": "模型结构化输出失败", "percent": 100, "mode": "协作"},
            "result": {
                "answer": answer, "error": "structured_output_invalid", "session_id": session_id,
            },
        })
    except Exception as exc:  # noqa: BLE001
        task.update({
            "status": "failed", "error": str(exc), "updated_at": now_iso(),
            "progress": {"stage": "reply", "label": "后端处理失败", "percent": 100, "mode": "协作"},
            "result": {"answer": "抱歉，处理您的问题时出现错误。", "error": str(exc), "session_id": session_id},
        })


async def chat_status(request: web.Request) -> web.Response:
    task = request.app["tasks"].get(request.match_info["task_id"])
    if not task:
        raise web.HTTPNotFound(text="task_not_found")
    if task.get("user_id") != token_user_id(request):
        raise web.HTTPForbidden(text="task_forbidden")
    return web.json_response(task)


async def recent_conversations(request: web.Request) -> web.Response:
    traces = await request.app["container"].store.find("traces", {"user_id": token_user_id(request)})
    groups: dict[str, dict[str, Any]] = {}
    for trace in sorted(traces, key=lambda item: str(item.get("created_at", ""))):
        sid = str(trace.get("session_id") or "")
        if not sid:
            continue
        group = groups.setdefault(sid, {"session_id": sid, "title": "", "message_count": 0, "updated_at": ""})
        group["title"] = group["title"] or str(trace.get("query") or "新对话")[:50]
        group["message_count"] += 2
        group["updated_at"] = max(group["updated_at"], str(trace.get("created_at") or ""))
    return web.json_response({"items": sorted(groups.values(), key=lambda item: item["updated_at"], reverse=True)})


async def history(request: web.Request) -> web.Response:
    traces = await request.app["container"].store.find(
        "traces", {"session_id": request.match_info["session_id"], "user_id": token_user_id(request)}
    )
    messages: list[dict[str, Any]] = []
    for trace in sorted(traces, key=lambda item: str(item.get("created_at", ""))):
        messages.extend([
            {"role": "user", "content": trace.get("query", "")},
            {"role": "assistant", "content": trace.get("answer", ""), "citations": trace.get("citations") or []},
        ])
    return web.json_response({"items": messages})


async def login(request: web.Request) -> web.Response:
    body = await json_body(request)
    auth = request.app["container"].auth
    user = await auth.authenticate(str(body.get("username") or ""), str(body.get("password") or ""))
    if user is None:
        raise web.HTTPUnauthorized(text="用户名或密码错误")
    return web.json_response({"token": auth.issue_token(user["id"]), "user": user})


async def delete_session(request: web.Request) -> web.Response:
    sid = request.match_info["session_id"]
    container = request.app["container"]
    await container.working_memory.clear(sid)
    await container.episodic_memory.delete_session(sid, token_user_id(request))
    for trace in await container.store.find("traces", {"session_id": sid, "user_id": token_user_id(request)}):
        await container.store.delete("traces", trace["_id"])
    return web.json_response({"cleared": sid})


async def index(_: web.Request) -> web.StreamResponse:
    return web.FileResponse(FRONTEND_DIST / "index.html")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "processagent-web"})


async def readiness(request: web.Request) -> web.Response:
    state = getattr(fastapi_app.state, "readiness", {"status": "not_ready", "error": "runtime_not_initialized"})
    status = 200 if state.get("status") == "ready" else 503
    return web.json_response(state, status=status)


async def static_or_index(request: web.Request) -> web.StreamResponse:
    candidate = (FRONTEND_DIST / request.match_info.get("path", "")).resolve()
    if candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
        return web.FileResponse(candidate)
    return await index(request)


@asynccontextmanager
async def backend_context(app: web.Application):
    async with backend_lifespan(fastapi_app):
        app["container"] = fastapi_app.state.container
        yield
        for handle in list(app["task_handles"]):
            handle.cancel()
        if app["task_handles"]:
            await asyncio.gather(*app["task_handles"], return_exceptions=True)


def create_app() -> web.Application:
    app = web.Application(client_max_size=20 * 1024 * 1024)
    app["tasks"] = {}
    app["task_handles"] = set()
    app.cleanup_ctx.append(backend_context)
    app.router.add_get("/", index)
    app.router.add_get("/healthz", health)
    app.router.add_get("/readyz", readiness)
    app.router.add_get("/api/health", readiness)
    app.router.add_post("/api/auth/login", login)
    app.router.add_post("/api/chat/start", chat_start)
    app.router.add_get("/api/chat/status/{task_id}", chat_status)
    app.router.add_get("/api/conversations/recent", recent_conversations)
    app.router.add_get("/api/chat/history/{session_id}", history)
    app.router.add_delete("/api/chat/session/{session_id}", delete_session)
    app.router.add_get("/{path:.*}", static_or_index)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ProcessAgent single-container web server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8088, type=int)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port 必须在 0 到 65535 之间，例如 8088")
    web.run_app(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
