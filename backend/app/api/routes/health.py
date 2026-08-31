"""健康检查 / 就绪探针。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request):
    readiness = getattr(request.app.state, "readiness", {"status": "not_ready", "error": "runtime_not_initialized"})
    if readiness.get("status") != "ready":
        return JSONResponse(status_code=503, content=readiness)
    return readiness
