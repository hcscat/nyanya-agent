#!/usr/bin/env python3
"""FastAPI dashboard for NyaNya Agent operations."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nyanya_agent import core
from nyanya_agent import dashboard_store as store
from nyanya_agent import execution_store as ledger
from nyanya_agent import database as db, operation_store
from nyanya_agent.execution_runtime import ExecutionCoordinator


core.load_env(core.DEFAULT_ENV)

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


class MemoryUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|approved|rejected|archived)$")
    importance: float | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(default="", max_length=20_000)
    priority: int = Field(default=100, ge=0, le=1000)
    requested_by: str = Field(default="operator", min_length=1, max_length=100)
    assigned_agent_id: str | None = Field(default=None, max_length=100)
    project_id: str | None = Field(default=None, max_length=100)
    codex_session_id: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    workspace: str = Field(min_length=1, max_length=1000)
    profile: str = Field(default='auto', pattern='^(auto|flash|luna|astra)$')


class OperationControl(BaseModel):
    command: str = Field(min_length=1, max_length=1000)


class ExecutionProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner: str = Field(default="operator", min_length=1, max_length=100)
    workspace_root: str = Field(default="", max_length=1000)
    status: str = Field(default="active", pattern="^(active|paused|archived)$")
    description: str = Field(default="", max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodexSessionCreate(BaseModel):
    session_key: str = Field(min_length=1, max_length=240)
    name: str = Field(default="Codex project session", min_length=1, max_length=160)
    external_session_id: str = Field(default="", max_length=240)
    status: str = Field(default="active", pattern="^(active|paused|closed)$")
    workspace_root: str = Field(default="", max_length=1000)
    model: str = Field(default="", max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlAction(BaseModel):
    actor: str = Field(default="operator", min_length=1, max_length=100)
    reason: str = Field(default="", max_length=2000)


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    decided_by: str = Field(default="operator", min_length=1, max_length=100)
    reason: str = Field(default="", max_length=2000)


def _control_token() -> str:
    configured = os.getenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "").strip()
    if configured:
        return configured
    token_file = Path(
        os.getenv(
            "NYANYA_DASHBOARD_CONTROL_TOKEN_FILE",
            str(core.STATE_ROOT / "data" / "dashboard_control.token"),
        )
    ).expanduser()
    if not token_file.is_absolute():
        token_file = core.STATE_ROOT / token_file
    try:
        if not token_file.is_file() or token_file.is_symlink():
            return ""
        if os.name != "nt" and token_file.stat().st_mode & 0o077:
            return ""
        return token_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def require_control_token(
    authorization: str | None = Header(default=None),
    x_nyanya_control_token: str | None = Header(default=None),
) -> str:
    expected = _control_token()
    if not expected:
        raise HTTPException(status_code=503, detail="Dashboard control token is not configured")
    supplied = x_nyanya_control_token or ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid dashboard control token")
    return "authenticated"


def heartbeat_local_host(db_path: str | Path | None = None) -> dict[str, Any]:
    macos_version = platform.mac_ver()[0]
    return ledger.register_host(
        name=os.getenv("NYANYA_HOST_NAME", "mac-a"),
        role=os.getenv("NYANYA_HOST_ROLE", "control-hub"),
        platform=f"macOS {macos_version}" if macos_version else platform.system(),
        architecture=platform.machine(),
        tailscale_name=os.getenv("NYANYA_TAILSCALE_HOSTNAME", ""),
        status="online",
        capabilities={
            "dashboard": True,
            "discord_bridge": True,
            "tmux": shutil.which("tmux") is not None,
            "codex": shutil.which("codex") is not None,
            "antigravity": shutil.which("agy") is not None,
            "tailscale": shutil.which("tailscale") is not None,
        },
        db_path=db_path,
    )


def create_app(db_path: str | Path | None = None) -> FastAPI:
    store.init_db(db_path)
    ledger.apply_migrations(db_path)
    ledger.reconcile_legacy_requests(db_path=db_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async def heartbeat_loop() -> None:
            while True:
                heartbeat_local_host(db_path)
                await asyncio.sleep(30)

        heartbeat_task = asyncio.create_task(heartbeat_loop())
        try:
            yield
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            _app.state.operations.close()

    app = FastAPI(title="NyaNya Agent Dashboard", version="0.3.0", lifespan=lifespan)
    from nyanya_agent.operation_service import OperationService
    app.state.operations = OperationService(db_path)
    app.state.db_path = db_path
    app.state.execution_coordinator = ExecutionCoordinator(db_path=db_path)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("NYANYA_DASHBOARD_CORS_ORIGINS", "http://127.0.0.1,http://localhost").split(","),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def authenticate_remote_reads(request: Request, call_next):
        # Do not trust forwarded headers as identity or assume a proxy makes reads local.
        remote = not request.client or request.client.host not in {"127.0.0.1", "::1"}
        forwarded = any(name in request.headers for name in ("forwarded", "x-forwarded-for", "x-real-ip"))
        if request.url.path.startswith("/v1/") and (remote or forwarded):
            try:
                require_control_token(request.headers.get("authorization"), request.headers.get("x-nyanya-control-token"))
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Dashboard static files are not installed")
        return FileResponse(index_path)

    @app.get("/health")
    def health() -> dict[str, Any]:
        store.init_db(app.state.db_path)
        schema = ledger.schema_state(app.state.db_path)
        return {
            "status": "ok",
            "service": "nyanya-dashboard",
            "schema_version": schema["version"],
            "control_auth_configured": bool(_control_token()),
        }

    @app.get("/v1/summary")
    def summary() -> dict[str, Any]:
        result = store.dashboard_summary(db_path=app.state.db_path)
        result["execution_ledger"] = ledger.ledger_summary(db_path=app.state.db_path)
        return result

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

    @app.post("/v1/projects", status_code=201, dependencies=[Depends(require_control_token)])
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

    @app.post("/v1/execution-projects", status_code=201, dependencies=[Depends(require_control_token)])
    def create_execution_project(payload: ExecutionProjectCreate) -> dict[str, Any]:
        try:
            return ledger.create_project(
                name=payload.name,
                owner=payload.owner,
                workspace_root=payload.workspace_root,
                status=payload.status,
                description=payload.description,
                metadata=payload.metadata,
                db_path=app.state.db_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                raise HTTPException(status_code=409, detail="An execution project already uses this workspace") from exc
            raise

    @app.get("/v1/execution-projects")
    def list_execution_projects(
        status: str | None = Query(default=None, pattern="^(active|paused|archived)$"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        return ledger.list_projects(status=status, limit=limit, db_path=app.state.db_path)

    @app.get("/v1/execution-projects/{project_id}")
    def get_execution_project(project_id: str) -> dict[str, Any]:
        project = ledger.get_project(project_id, db_path=app.state.db_path)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Execution project not found: {project_id}")
        return project

    @app.post(
        "/v1/execution-projects/{project_id}/codex-sessions",
        status_code=201,
        dependencies=[Depends(require_control_token)],
    )
    def create_codex_session(project_id: str, payload: CodexSessionCreate) -> dict[str, Any]:
        if ledger.get_project(project_id, db_path=app.state.db_path) is None:
            raise HTTPException(status_code=404, detail=f"Execution project not found: {project_id}")
        try:
            return ledger.create_codex_session(
                project_id=project_id,
                session_key=payload.session_key,
                name=payload.name,
                external_session_id=payload.external_session_id,
                status=payload.status,
                workspace_root=payload.workspace_root,
                model=payload.model,
                metadata=payload.metadata,
                db_path=app.state.db_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/execution-projects/{project_id}/codex-sessions")
    def list_codex_sessions(
        project_id: str,
        status: str | None = Query(default=None, pattern="^(active|paused|closed)$"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        if ledger.get_project(project_id, db_path=app.state.db_path) is None:
            raise HTTPException(status_code=404, detail=f"Execution project not found: {project_id}")
        return ledger.list_codex_sessions(
            project_id=project_id,
            status=status,
            limit=limit,
            db_path=app.state.db_path,
        )

    @app.get("/v1/codex-sessions/{session_id}")
    def get_codex_session(session_id: str) -> dict[str, Any]:
        session = ledger.get_codex_session(session_id, db_path=app.state.db_path)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Codex session not found: {session_id}")
        return session

    @app.patch(
        "/v1/projects/{project_id}/phases/{phase_key}",
        dependencies=[Depends(require_control_token)],
    )
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

    @app.post(
        "/v1/projects/{project_id}/phases/{phase_key}/check",
        dependencies=[Depends(require_control_token)],
    )
    def check_phase(project_id: str, phase_key: str) -> dict[str, Any]:
        try:
            return store.check_project_phase(project_id, phase_key=phase_key, db_path=app.state.db_path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Phase not found: {exc}") from exc

    @app.get("/v1/audit-log")
    def audit_log(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
        return store.audit_log(limit=limit, db_path=app.state.db_path)

    @app.get("/v1/schema")
    def execution_schema() -> dict[str, Any]:
        return ledger.schema_state(db_path=app.state.db_path)

    @app.get("/v1/hosts")
    def list_hosts(
        stale_after_seconds: int = Query(default=90, ge=10, le=3600),
        offline_after_seconds: int = Query(default=300, ge=30, le=86_400),
    ) -> list[dict[str, Any]]:
        return ledger.list_hosts(
            stale_after_seconds=stale_after_seconds,
            offline_after_seconds=offline_after_seconds,
            db_path=app.state.db_path,
        )

    @app.get("/v1/agents")
    def list_agents() -> list[dict[str, Any]]:
        return ledger.list_agent_profiles(db_path=app.state.db_path)

    @app.get("/v1/adapters")
    def adapter_inventory() -> list[dict[str, Any]]:
        return app.state.execution_coordinator.inventory()

    @app.post('/v1/operations', status_code=201, dependencies=[Depends(require_control_token)])
    def create_operation(payload: OperationCreate):
        try:
            return app.state.operations.submit(payload.prompt, payload.workspace, 'operator', profile=payload.profile)
        except (ValueError, PermissionError, OSError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=f'Operation prerequisite failed: {type(exc).__name__}') from exc

    @app.get('/v1/operations/incomplete', dependencies=[Depends(require_control_token)])
    def incomplete_operations():
        from nyanya_agent.operation_store import incomplete
        return incomplete(app.state.operations.path, 'operator')

    @app.post('/v1/operations/control', dependencies=[Depends(require_control_token)])
    def control_operation(payload: OperationControl):
        try:
            # An HTTP request acknowledges submission, not final delivery.
            response = app.state.operations.control(payload.command, 'operator', wait=False)
            if response is None:
                raise ValueError('Unsupported operation control')
            return {'message': response}
        except (ValueError, PermissionError, OSError) as exc:
            raise HTTPException(status_code=409, detail=f'Operation control rejected: {type(exc).__name__}') from exc

    @app.post("/v1/tasks", status_code=201, dependencies=[Depends(require_control_token)])
    def create_task(payload: TaskCreate) -> dict[str, Any]:
        try:
            return ledger.create_task(
                title=payload.title,
                prompt=payload.prompt,
                priority=payload.priority,
                requested_by=payload.requested_by,
                assigned_agent_id=payload.assigned_agent_id,
                project_id=payload.project_id,
                codex_session_id=payload.codex_session_id,
                metadata={**payload.metadata, "execution_mode": "draft", "execution_hint": "Submit /v1/operations to execute"},
                db_path=app.state.db_path,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Project or session not found: {exc}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/tasks")
    def list_tasks(
        status: str | None = None,
        project_id: str | None = None,
        codex_session_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        return ledger.list_tasks(
            status=status,
            project_id=project_id,
            codex_session_id=codex_session_id,
            limit=limit,
            db_path=app.state.db_path,
        )

    @app.get("/v1/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        task = ledger.get_task(task_id, db_path=app.state.db_path)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        return task

    def require_cancel_owner(task):
        # The control credential authenticates operator, never payload.actor.
        if (task.get("metadata", {}).get("owner_key") or task.get("requested_by") or "operator") != "operator":
            raise HTTPException(status_code=403, detail="Task owner mismatch")

    def cancel_operation_task(task, expected_execution_id=None):
        with db.connect(app.state.db_path) as conn:
            operation = conn.execute("SELECT 1 FROM task_operations WHERE task_id=?", (task["id"],)).fetchone()
        if not operation:
            return False
        try:
            operation_store.cancel(
                app.state.db_path, task["id"], "operator", expected_execution_id=expected_execution_id
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Task owner mismatch") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="Execution state changed; refresh before cancelling") from exc
        return True

    @app.post("/v1/tasks/{task_id}/cancel", dependencies=[Depends(require_control_token)])
    def cancel_task(task_id: str, payload: ControlAction) -> dict[str, Any]:
        task = ledger.get_task(task_id, db_path=app.state.db_path)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        require_cancel_owner(task)
        if cancel_operation_task(task):
            return ledger.get_task(task_id, db_path=app.state.db_path)
        if task["status"] in ledger.TASK_TERMINAL_STATUSES:
            return task
        execution_id = task.get("current_execution_id")
        if execution_id:
            execution = ledger.get_execution(execution_id, db_path=app.state.db_path)
            if execution and execution["status"] not in ledger.EXECUTION_TERMINAL_STATUSES:
                try:
                    ledger.transition_execution(
                        execution_id,
                        "cancelling",
                        actor="operator",
                        message=payload.reason or "Cancellation requested",
                        db_path=app.state.db_path,
                    )
                    return ledger.get_task(task_id, db_path=app.state.db_path)
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail="Execution state changed; refresh before cancelling") from exc
        return ledger.transition_task(
            task_id,
            "cancelled",
            actor="operator",
            message=payload.reason or "Task cancelled",
            db_path=app.state.db_path,
        )

    @app.post("/v1/tasks/{task_id}/retry", dependencies=[Depends(require_control_token)])
    def retry_task(task_id: str, payload: ControlAction) -> dict[str, Any]:
        task = ledger.get_task(task_id, db_path=app.state.db_path)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        raise HTTPException(status_code=409, detail="Retry requires operator reconciliation and a new request; stored work is not replayed")

    @app.get("/v1/executions")
    def list_executions(
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        return ledger.list_executions(status=status, limit=limit, db_path=app.state.db_path)

    @app.get("/v1/executions/{execution_id}")
    def get_execution(execution_id: str) -> dict[str, Any]:
        execution = ledger.get_execution(execution_id, db_path=app.state.db_path)
        if execution is None:
            raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")
        return execution

    @app.post("/v1/executions/{execution_id}/cancel", dependencies=[Depends(require_control_token)])
    def cancel_execution(execution_id: str, payload: ControlAction) -> dict[str, Any]:
        execution = ledger.get_execution(execution_id, db_path=app.state.db_path)
        if execution is None:
            raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")
        task = ledger.get_task(execution["task_id"], db_path=app.state.db_path)
        require_cancel_owner(task)
        if task.get("current_execution_id") != execution_id:
            if execution["status"] in ledger.EXECUTION_TERMINAL_STATUSES:
                return execution
            raise HTTPException(status_code=409, detail="Execution is no longer current")
        if cancel_operation_task(task, execution_id):
            return ledger.get_execution(execution_id, db_path=app.state.db_path)
        if execution and execution.get("metadata", {}).get("worker_id"):
            if execution["status"] in ledger.EXECUTION_TERMINAL_STATUSES:
                return execution
            return ledger.transition_execution(execution_id, "cancelling", force=True, db_path=app.state.db_path)
        try:
            return app.state.execution_coordinator.cancel(
                execution_id,
                actor="operator",
                reason=payload.reason,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/runtime-sessions")
    def runtime_sessions(
        stale_after_seconds: int = Query(default=90, ge=10, le=3600),
        offline_after_seconds: int = Query(default=300, ge=30, le=86_400),
    ) -> list[dict[str, Any]]:
        return ledger.list_runtime_sessions(
            stale_after_seconds=stale_after_seconds,
            offline_after_seconds=offline_after_seconds,
            db_path=app.state.db_path,
        )

    @app.post("/v1/recovery/reconcile", dependencies=[Depends(require_control_token)])
    def recover_active_executions() -> dict[str, Any]:
        recovered = app.state.execution_coordinator.recover_active()
        return {"count": len(recovered), "executions": recovered}

    @app.get("/v1/approvals")
    def list_approvals(
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        return ledger.list_approvals(status=status, limit=limit, db_path=app.state.db_path)

    @app.post("/v1/approvals/{approval_id}/decision", dependencies=[Depends(require_control_token)])
    def decide_approval(approval_id: str, payload: ApprovalDecision) -> dict[str, Any]:
        try:
            return ledger.decide_approval(
                approval_id,
                decision=payload.decision,
                decided_by="operator",
                reason=payload.reason,
                db_path=app.state.db_path,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Approval not found: {approval_id}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/events")
    def events(
        after_seq: int = Query(default=0, ge=0),
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        return ledger.list_events(after_seq=after_seq, limit=limit, db_path=app.state.db_path)

    @app.get("/v1/events/stream")
    async def event_stream(
        request: Request,
        cursor: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None),
    ) -> StreamingResponse:
        if last_event_id and last_event_id.isdigit():
            cursor = max(cursor, int(last_event_id))

        async def generate():
            nonlocal cursor
            idle_ticks = 0
            while not await request.is_disconnected():
                batch = ledger.list_events(after_seq=cursor, limit=200, db_path=app.state.db_path)
                if batch:
                    idle_ticks = 0
                    for event in batch:
                        cursor = int(event["seq"])
                        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                        yield f"id: {cursor}\nevent: ledger\ndata: {payload}\n\n"
                else:
                    idle_ticks += 1
                    if idle_ticks >= 15:
                        idle_ticks = 0
                        yield ": keepalive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/memories")
    def list_memories(
        status: str | None = Query(default=None, pattern="^(pending|approved|rejected|archived)$"),
        limit: int = Query(default=100, ge=1, le=300),
    ) -> list[dict[str, Any]]:
        return store.list_memories(status=status, limit=limit, db_path=app.state.db_path)

    @app.post("/v1/memories/extract", dependencies=[Depends(require_control_token)])
    def extract_memories(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        return store.extract_memory_candidates_from_requests(limit=limit, db_path=app.state.db_path)

    @app.patch("/v1/memories/{memory_id}", dependencies=[Depends(require_control_token)])
    def update_memory(memory_id: str, payload: MemoryUpdate) -> dict[str, Any]:
        memory = store.update_memory(
            memory_id,
            status=payload.status,
            importance=payload.importance,
            confidence=payload.confidence,
            db_path=app.state.db_path,
        )
        if memory is None:
            raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id}")
        return memory

    @app.get("/v1/memory-graph")
    def memory_graph(
        status: str | None = Query(default=None, pattern="^(pending|approved|rejected|archived)$"),
        limit: int = Query(default=80, ge=1, le=200),
    ) -> dict[str, Any]:
        return store.memory_graph(status=status, limit=limit, db_path=app.state.db_path)

    @app.get("/v1/tech-stack-graph")
    def tech_stack_graph(
        status: str | None = Query(default=None, pattern="^(pending|approved|rejected|archived)$"),
        limit: int = Query(default=120, ge=1, le=300),
    ) -> dict[str, Any]:
        return store.tech_stack_graph(status=status, limit=limit, db_path=app.state.db_path)

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
