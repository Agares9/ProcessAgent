"""FastAPI 仅保留健康检查；业务请求统一走 aiohttp Web + CLI 场景入口。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health

# 健康检查不挂 v1 前缀
root_router = APIRouter()
root_router.include_router(health.router)
