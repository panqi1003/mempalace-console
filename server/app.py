"""FastAPI 只读端点。错误语义：400 白名单 / 502 工具错 / 503 全不可达。"""

from __future__ import annotations

import os

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .reader import ReaderToolError, ReaderUnavailable, ReadOnlyReader

WEB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web"
)


def _lang(request) -> str:
    """按 Accept-Language 选择用户可见文案语言：缺省 zh（兼容旧测试/中文默认），含 zh 则中文，否则英文。"""
    header = (request.headers.get("accept-language") or "").strip().lower()
    if not header:
        return "zh"
    return "zh" if "zh" in header else "en"


def create_app(reader: ReadOnlyReader | None = None) -> FastAPI:
    app = FastAPI(title="MemPalace 可视化管理台", docs_url=None, redoc_url=None)
    r = reader or ReadOnlyReader()

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(config.ReadOnlyViolation)
    async def _violation(_request, exc: config.ReadOnlyViolation):
        return JSONResponse({"error": {"message": str(exc)}}, status_code=400)

    @app.exception_handler(ReaderToolError)
    async def _tool_error(_request, exc: ReaderToolError):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=502
        )

    @app.exception_handler(ReaderUnavailable)
    async def _unavailable(_request, exc: ReaderUnavailable):
        return JSONResponse(
            {
                "error": {"message": "palace unreachable", "detail": str(exc)},
                "tiers": r.tier_status(),
            },
            status_code=503,
        )

    def _ok(data, extra=None):
        body = {"data": data, "tiers": r.tier_status()}
        if extra:
            body.update(extra)
        return JSONResponse(body)

    @app.get("/api/overview")
    def overview():
        return _ok(r.overview())

    @app.get("/api/taxonomy")
    def taxonomy():
        return _ok(r.taxonomy())

    @app.get("/api/wings")
    def wings():
        return _ok(r.wings())

    @app.get("/api/rooms")
    def rooms(wing: str = Query(...)):
        return _ok(r.rooms(wing))

    @app.get("/api/drawers")
    def drawers(
        wing: str | None = None,
        room: str | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        return _ok(r.drawers(wing=wing, room=room, offset=offset, limit=limit))

    @app.get("/api/drawer/{drawer_id}")
    def drawer(drawer_id: str):
        return _ok(r.drawer(drawer_id))

    @app.get("/api/search")
    def search(
        q: str = Query(..., min_length=1),
        wing: str | None = None,
        room: str | None = None,
        limit: int = Query(10, ge=1, le=100),
    ):
        return _ok(r.search(q, wing=wing, room=room, limit=limit))

    @app.get("/api/kg/stats")
    def kg_stats():
        return _ok(r.kg_stats())

    @app.get("/api/kg/query")
    def kg_query(entity: str = Query(...)):
        return _ok(r.kg_query(entity))

    @app.get("/api/kg/timeline")
    def kg_timeline(entity: str | None = None):
        return _ok(r.kg_timeline(entity))

    @app.get("/api/graph/stats")
    def graph_stats():
        return _ok(r.graph_stats())

    @app.get("/api/graph/tunnels")
    def graph_tunnels():
        return _ok(r.tunnels())

    @app.get("/api/graph/traverse")
    def graph_traverse(room: str = Query(...), hops: int = Query(2, ge=1, le=5)):
        return _ok(r.traverse(room, max_hops=hops))

    @app.get("/api/graph/hallways")
    def graph_hallways(wing: str | None = None):
        return _ok(r.hallways(wing=wing))

    @app.get("/api/diary")
    def diary(agent: str = Query(...), last_n: int = Query(20, ge=1, le=100)):
        return _ok(r.diary(agent, last_n=last_n))

    @app.get("/api/diary/agents")
    def diary_agents():
        return _ok(r.diary_agents())

    @app.get("/api/events")
    def events(limit: int = Query(50, ge=1, le=200)):
        return _ok(r.events(limit=limit))

    @app.get("/api/artifact/{artifact_id}")
    def artifact(artifact_id: str):
        return _ok(r.artifact(artifact_id))

    @app.get("/api/health/summary")
    def health_summary(request: Request):
        lang = _lang(request)
        repair_status = ""
        try:
            repair_status = r.repair_status_text()
        except Exception as exc:  # CLI 不可用时降级为说明文本
            repair_status = (
                f"repair-status 不可用：{exc}"
                if lang != "en"
                else f"repair-status unavailable: {exc}"
            )
        return JSONResponse(
            {
                "repair_status": repair_status,
                "hub_log_configured": bool(config.HUB_LOG),
                "hub_log_tail": r.hub_log_tail(lang=lang),
                "backups": r.backups(),
                "palace": r.palace_size(lang=lang),
                "tiers": r.tier_status(),
            }
        )

    @app.get("/api/activity")
    def activity(days: int = Query(30, ge=7, le=90)):
        return _ok(r.activity(days=days))

    @app.get("/api/audit")
    def audit(samples: int = Query(5, ge=0, le=100)):
        return _ok(r.audit(sample_size=samples))

    @app.get("/api/wakeup")
    def wakeup(wing: str = Query(...)):
        return JSONResponse(
            {"data": {"text": r.wakeup(wing)}, "tiers": r.tier_status()}
        )

    if os.path.isdir(WEB_DIR):
        app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

        @app.get("/")
        def index():
            return FileResponse(os.path.join(WEB_DIR, "index.html"))

    return app
