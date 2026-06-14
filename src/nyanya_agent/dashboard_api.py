#!/usr/bin/env python3
"""FastAPI dashboard for NyaNya Agent operations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nyanya_agent import dashboard_store as store


STATIC_DIR = Path(__file__).resolve().parent / "dashboard_static"


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = Field(default="", max_length=2000)
    owner: str = Field(default="operator", max_length=80)


class PhaseUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    summary: str | None = Field(default=None, max_length=2000)
    next_action: str | None = Field(default=None, max_length=2000)
    requires_confirmation: bool | None = None


def create_app(db_path: str | Path | None = None) -> FastAPI:
    store.init_db(db_path)
    app = FastAPI(title="NyaNya Agent Dashboard", version="0.1.0")
    app.state.db_path = db_path

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("NYANYA_DASHBOARD_CORS_ORIGINS", "http://127.0.0.1,http://localhost").split(","),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Dashboard static files are not installed")
        return FileResponse(index_path)

    @app.get("/health")
    def health() -> dict[str, str]:
        store.init_db(app.state.db_path)
        return {"status": "ok", "service": "nyanya-dashboard"}

    @app.get("/v1/summary")
    def summary() -> dict[str, Any]:
        return store.dashboard_summary(db_path=app.state.db_path)

    @app.get("/v1/requests")
    def list_requests(
        status: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        return store.list_requests(status=status, limit=limit, db_path=app.state.db_path)

    @app.get("/v1/requests/{request_id}")
    def get_request(request_id: str) -> dict[str, Any]:
        request = store.get_request(request_id, db_path=app.state.db_path)
        if request is None:
            raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")
        return request

    @app.get("/v1/usage")
    def usage(
        period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
        limit: int = Query(default=30, ge=1, le=120),
    ) -> list[dict[str, Any]]:
        return store.usage_series(period=period, limit=limit, db_path=app.state.db_path)

    @app.post("/v1/projects", status_code=201)
    def create_project(payload: ProjectCreate) -> dict[str, Any]:
        return store.create_project(
            name=payload.name,
            goal=payload.goal,
            owner=payload.owner,
            db_path=app.state.db_path,
        )

    @app.get("/v1/projects")
    def list_projects() -> list[dict[str, Any]]:
        return store.list_projects(db_path=app.state.db_path)

    @app.get("/v1/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        project = store.get_project(project_id, db_path=app.state.db_path)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
        return project

    @app.patch("/v1/projects/{project_id}/phases/{phase_key}")
    def update_phase(project_id: str, phase_key: str, payload: PhaseUpdate) -> dict[str, Any]:
        phase = store.update_phase(
            project_id,
            phase_key,
            status=payload.status,
            summary=payload.summary,
            next_action=payload.next_action,
            requires_confirmation=payload.requires_confirmation,
            db_path=app.state.db_path,
        )
        if phase is None:
            raise HTTPException(status_code=404, detail=f"Phase not found: {project_id}:{phase_key}")
        return phase

    @app.post("/v1/projects/{project_id}/phases/{phase_key}/check")
    def check_phase(project_id: str, phase_key: str) -> dict[str, Any]:
        try:
            return store.check_project_phase(project_id, phase_key=phase_key, db_path=app.state.db_path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Phase not found: {exc}") from exc

    @app.get("/v1/audit-log")
    def audit_log(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
        return store.audit_log(limit=limit, db_path=app.state.db_path)

    return app


app = create_app()


def main() -> int:
    import uvicorn

    host = os.getenv("NYANYA_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("NYANYA_DASHBOARD_PORT", "8765"))
    uvicorn.run("nyanya_agent.dashboard_api:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
