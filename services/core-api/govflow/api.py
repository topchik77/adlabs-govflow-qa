import hashlib
import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from threading import Lock
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException

from govflow import config
from govflow.domain import (
    DomainError,
    accessible,
    add_signature,
    check_version,
    digest,
    document_snapshot,
    local_process,
    notify,
    record,
    require_editable,
    require_role,
    transition,
    verify_applicant_signature,
)
from govflow.models import (
    Application,
    Attachment,
    AuditEvent,
    ExternalCheck,
    IdempotencyRecord,
    ReviewDecision,
    Signature,
    Tenant,
    User,
)
from govflow.schemas import (
    ApplicationView,
    Edit,
    ErrorView,
    Login,
    PageView,
    ReviewCommand,
    SignCommand,
    Status,
    SubmitView,
    TokenView,
    UserView,
    VersionCommand,
)
from govflow.schemas import Form as ApplicationForm
from govflow.security import DUMMY_HASH, issue_token, passwords, read_token

log = logging.getLogger("govflow")
bearer = HTTPBearer(auto_error=False)
MAX_ATTACHMENT = 5 * 1024 * 1024


def create_app(database_url=None, jwt_secret=None, signature_secret=None):
    api = FastAPI(
        title="ADLabs GovFlow QA Simulator",
        version="0.1.0",
        description="Stage 1 reference. Synthetic data; HMAC educational signatures only.",
        responses={s: {"model": ErrorView} for s in [401, 403, 404, 409, 413, 415, 422, 429, 503]},
    )
    engine = create_engine(database_url or config.database_url(), pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    token_secret = jwt_secret or config.secret("JWT_SECRET")
    signing_secret = signature_secret or config.secret("SIGNATURE_SECRET")
    api.state.engine, api.state.factory = engine, factory
    api.state.jwt_secret = token_secret
    login_attempts = defaultdict(deque)
    login_lock = Lock()

    @api.middleware("http")
    async def correlation(request, call_next):
        started = time.monotonic()
        request.state.request_id = str(uuid.uuid4())
        supplied = request.headers.get("X-Correlation-ID", "")
        request.state.correlation_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", supplied) else str(uuid.uuid4())
        )
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        # No tokens, body, path parameters or query strings in logs.
        log.info(
            json.dumps(
                {
                    "correlation_id": request.state.correlation_id,
                    "method": request.method,
                    "status": response.status_code,
                    "request_id": request.state.request_id,
                    "actor": getattr(request.state, "actor_id", "anonymous"),
                    "tenant": getattr(request.state, "tenant_id", None),
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                }
            )
        )
        return response

    def error_response(request, status, code, message, details=None):
        return JSONResponse(
            status_code=status,
            content={
                "code": code,
                "message": message,
                "correlation_id": getattr(request.state, "correlation_id", "unknown"),
                "details": details or {},
            },
        )

    @api.exception_handler(DomainError)
    async def domain_error(request, exc):
        return error_response(request, exc.status, exc.code, exc.message, exc.details)

    @api.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        issues = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        return error_response(request, 422, "VALIDATION_ERROR", "Проверьте поля запроса", {"issues": issues})

    @api.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, exc.status_code, "HTTP_ERROR", "Запрос недоступен")

    @api.exception_handler(Exception)
    async def unexpected_error(request, exc):
        response = error_response(request, 500, "INTERNAL_ERROR", "Внутренняя ошибка сервера")
        response.headers["X-Correlation-ID"] = getattr(request.state, "correlation_id", "unknown")
        return response

    def db():
        with factory() as session:
            try:
                yield session
            finally:
                session.rollback()

    DB = Annotated[Session, Depends(db)]

    def current_user(
        request: Request,
        session: DB,
        auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        try:
            if auth is None:
                raise ValueError()
            claims = read_token(auth.credentials, token_secret)
            user = session.get(User, claims["sub"])
            if (
                not user
                or not user.active
                or user.tenant_id != claims["tenant_id"]
                or user.role != claims["role"]
            ):
                raise ValueError()
            tenant = session.get(Tenant, user.tenant_id)
            if not tenant or not tenant.active:
                raise ValueError()
            request.state.actor_id = user.id
            request.state.tenant_id = user.tenant_id
            return user
        except (jwt.InvalidTokenError, ValueError, KeyError):
            raise DomainError(401, "UNAUTHORIZED", "Войдите заново: сессия отсутствует или истекла") from None

    Actor = Annotated[User, Depends(current_user)]

    def user_view(user, session):
        return {
            "id": user.id,
            "username": user.username,
            "tenant_id": user.tenant_id,
            "tenant_name": session.get(Tenant, user.tenant_id).name,
            "role": user.role,
        }

    def view(app, session):
        attachments = session.scalars(
            select(Attachment).where(Attachment.application_id == app.id).order_by(Attachment.id)
        ).all()
        sigs = session.scalars(
            select(Signature).where(
                Signature.application_id == app.id, Signature.document_version == app.document_version
            )
        ).all()
        reviews = session.scalars(
            select(ReviewDecision)
            .where(ReviewDecision.application_id == app.id)
            .order_by(ReviewDecision.created_at)
        ).all()
        return {
            "id": app.id,
            "tenant_id": app.tenant_id,
            "applicant_id": app.applicant_id,
            "type": app.type,
            "title": app.title,
            "description": app.description,
            "business_status": app.business_status,
            "processing_status": app.processing_status,
            "version": app.version,
            "document_version": app.document_version,
            "document_hash": app.document_hash,
            "decision_document": app.decision_document,
            "decision_hash": app.decision_hash,
            "created_at": app.created_at.isoformat(),
            "updated_at": app.updated_at.isoformat(),
            "attachments": [
                {"id": f.id, "filename": f.filename, "mime": f.mime, "size": f.size, "sha256": f.sha256}
                for f in attachments
            ],
            "applicant_signed": any(s.kind == "APPLICANT" for s in sigs),
            "officer_signed": any(s.kind == "OFFICER" for s in sigs),
            "reviews": [
                {"decision": r.decision, "reason": r.reason, "created_at": r.created_at.isoformat()}
                for r in reviews
            ],
        }

    prefix = "/api/v1"

    @api.post(prefix + "/auth/login", response_model=TokenView)
    def login(payload: Login, request: Request, session: DB):
        bucket = request.client.host if request.client else "unknown"
        with login_lock:
            recent = login_attempts[bucket]
            clock = time.monotonic()
            while recent and recent[0] < clock - 60:
                recent.popleft()
            if len(recent) >= 30:
                raise DomainError(429, "RATE_LIMITED", "Слишком много попыток входа, подождите минуту")
            recent.append(clock)
        user = session.scalar(select(User).where(User.username == payload.username))
        valid = passwords.verify(payload.password, user.password_hash if user else DUMMY_HASH)
        if not user or not valid or not user.active or not session.get(Tenant, user.tenant_id).active:
            raise DomainError(401, "UNAUTHORIZED", "Неверные учётные данные")
        return {"access_token": issue_token(user, token_secret), "user": user_view(user, session)}

    @api.get(prefix + "/auth/me", response_model=UserView)
    def me(user: Actor, session: DB):
        return user_view(user, session)

    @api.get(prefix + "/health")
    def health():
        return {"status": "ok", "build": "0.1.0", "stage": "1-reference"}

    @api.get(prefix + "/ready")
    def ready(request: Request):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM alembic_version"))
            return {"status": "ready", "database": "postgresql", "broker": "not-in-stage-1"}
        except Exception:
            return error_response(request, 503, "NOT_READY", "База данных недоступна или не мигрирована")

    @api.post(prefix + "/applications", status_code=201, response_model=ApplicationView)
    def create(payload: ApplicationForm, request: Request, session: DB, user: Actor):
        require_role(user, "applicant")
        app = Application(**payload.model_dump(), tenant_id=user.tenant_id, applicant_id=user.id)
        session.add(app)
        session.flush()
        document_snapshot(session, app, increment=False)
        record(session, app, user.id, "CREATED", request.state.correlation_id, initial=True)
        session.commit()
        return view(app, session)

    @api.get(prefix + "/applications", response_model=PageView)
    def listing(
        session: DB,
        user: Actor,
        status: Status | None = None,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        sort: str = Query("newest", pattern="^(newest|oldest)$"),
    ):
        if user.role == "qa_observer":
            raise DomainError(403, "ROLE_FORBIDDEN", "Откройте обезличенный монитор")
        query = select(Application).where(Application.tenant_id == user.tenant_id)
        if user.role == "applicant":
            query = query.where(Application.applicant_id == user.id)
        if status:
            query = query.where(Application.business_status == status.value)
        count = session.scalar(select(func.count()).select_from(query.subquery()))
        order = Application.created_at.desc() if sort == "newest" else Application.created_at.asc()
        items = session.scalars(query.order_by(order, Application.id).limit(limit).offset(offset)).all()
        return {"items": [view(a, session) for a in items], "total": count, "limit": limit, "offset": offset}

    @api.get(prefix + "/applications/{application_id}", response_model=ApplicationView)
    def get(application_id: UUID, session: DB, user: Actor):
        return view(accessible(session, application_id, user), session)

    @api.patch(prefix + "/applications/{application_id}", response_model=ApplicationView)
    def edit(application_id: UUID, payload: Edit, request: Request, session: DB, user: Actor):
        app = accessible(session, application_id, user, lock=True)
        require_role(user, "applicant")
        check_version(app, payload.expected_version)
        require_editable(app)
        fields = payload.model_dump(exclude={"expected_version"})
        if any(getattr(app, k) != v for k, v in fields.items()):
            for k, v in fields.items():
                setattr(app, k, v)
            document_snapshot(session, app)
            record(
                session, app, user.id, "DOCUMENT_UPDATED", request.state.correlation_id, app.business_status
            )
        session.commit()
        return view(app, session)

    @api.post(
        prefix + "/applications/{application_id}/attachments", status_code=201, response_model=ApplicationView
    )
    async def attach(
        application_id: UUID,
        request: Request,
        session: DB,
        user: Actor,
        expected_version: Annotated[int, Form(ge=1)],
        file: Annotated[UploadFile, File()],
    ):
        app = accessible(session, application_id, user, lock=True)
        require_role(user, "applicant")
        check_version(app, expected_version)
        require_editable(app)
        name = file.filename or ""
        if not re.fullmatch(r"[\w .()-]{1,180}", name) or ".." in name or name.startswith("."):
            raise DomainError(422, "UNSAFE_FILENAME", "Недопустимое имя файла")
        if file.content_type not in {"application/pdf", "image/png"}:
            raise DomainError(415, "UNSUPPORTED_MEDIA_TYPE", "Разрешены только PDF и PNG")
        content = await file.read(MAX_ATTACHMENT + 1)
        if len(content) > MAX_ATTACHMENT:
            raise DomainError(413, "ATTACHMENT_TOO_LARGE", "Максимальный размер — 5 MiB")
        magic = b"%PDF-" if file.content_type == "application/pdf" else b"\x89PNG\r\n\x1a\n"
        if not content.startswith(magic):
            raise DomainError(415, "CONTENT_TYPE_MISMATCH", "Содержимое не соответствует формату")
        session.add(
            Attachment(
                application_id=app.id,
                filename=name,
                mime=file.content_type,
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                content=content,
            )
        )
        document_snapshot(session, app)
        record(session, app, user.id, "ATTACHMENT_ADDED", request.state.correlation_id, app.business_status)
        session.commit()
        return view(app, session)

    @api.get(prefix + "/applications/{application_id}/attachments/{attachment_id}")
    def download(application_id: UUID, attachment_id: UUID, session: DB, user: Actor):
        accessible(session, application_id, user)
        file = session.scalar(
            select(Attachment).where(
                Attachment.id == str(attachment_id), Attachment.application_id == str(application_id)
            )
        )
        if not file:
            raise DomainError(404, "NOT_FOUND", "Вложение не найдено")
        return Response(
            file.content,
            media_type=file.mime,
            headers={"Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff"},
        )

    @api.post(prefix + "/applications/{application_id}/prepare-signature", response_model=ApplicationView)
    def prepare(application_id: UUID, payload: VersionCommand, request: Request, session: DB, user: Actor):
        app = accessible(session, application_id, user, lock=True)
        require_role(user, "applicant")
        check_version(app, payload.expected_version)
        if not session.scalar(select(Attachment.id).where(Attachment.application_id == app.id)):
            raise DomainError(422, "ATTACHMENT_REQUIRED", "Добавьте синтетический PDF или PNG")
        if app.business_status == "NEEDS_CORRECTION":
            # A correction cycle always gets a fresh document revision.
            document_snapshot(session, app)
        transition(session, app, "AWAITING_APPLICANT_SIGNATURE", user.id, request.state.correlation_id)
        session.commit()
        return view(app, session)

    @api.post(prefix + "/applications/{application_id}/sign", response_model=ApplicationView)
    def sign(application_id: UUID, payload: SignCommand, request: Request, session: DB, user: Actor):
        app = accessible(session, application_id, user, lock=True)
        require_role(user, "applicant")
        check_version(app, payload.expected_version)
        if app.business_status != "AWAITING_APPLICANT_SIGNATURE":
            raise DomainError(409, "INVALID_TRANSITION", "Сначала подготовьте документ к подписанию")
        add_signature(session, app, user, "APPLICANT", payload.document_hash, signing_secret)
        record(session, app, user.id, "APPLICANT_SIGNED", request.state.correlation_id, app.business_status)
        session.commit()
        return view(app, session)

    @api.post(prefix + "/applications/{application_id}/submit", status_code=202, response_model=SubmitView)
    def submit(
        application_id: UUID,
        payload: VersionCommand,
        request: Request,
        background: BackgroundTasks,
        session: DB,
        user: Actor,
        idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
    ):
        app = accessible(session, application_id, user, lock=True)
        require_role(user, "applicant")
        scope = f"submit:{app.id}"
        previous = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.actor_id == user.id,
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.key == idempotency_key,
            )
        )
        payload_hash = digest(payload.model_dump())
        if previous:
            if previous.payload_hash != payload_hash:
                raise DomainError(409, "IDEMPOTENCY_CONFLICT", "Этот ключ уже использован с другим запросом")
            return previous.response
        check_version(app, payload.expected_version)
        verify_applicant_signature(session, app, signing_secret)
        app.processing_status = "PENDING"
        transition(session, app, "SUBMITTED", user.id, request.state.correlation_id)
        result = {
            "application_id": app.id,
            "business_status": "SUBMITTED",
            "processing_status": "PENDING",
            "version": app.version,
            "correlation_id": request.state.correlation_id,
        }
        session.add(
            IdempotencyRecord(
                actor_id=user.id, scope=scope, key=idempotency_key, payload_hash=payload_hash, response=result
            )
        )
        session.commit()
        background.add_task(local_process, factory, app.id, request.state.correlation_id)
        return result

    @api.post(prefix + "/applications/{application_id}/review", response_model=ApplicationView)
    def review(application_id: UUID, payload: ReviewCommand, request: Request, session: DB, user: Actor):
        app = accessible(session, application_id, user, lock=True)
        require_role(user, "reviewer")
        check_version(app, payload.expected_version)
        if app.business_status != "UNDER_REVIEW" or app.processing_status != "SUCCEEDED":
            raise DomainError(409, "INVALID_TRANSITION", "Дождитесь успешной проверки")
        decision = ReviewDecision(
            application_id=app.id, reviewer_id=user.id, decision=payload.decision, reason=payload.reason
        )
        session.add(decision)
        transition(session, app, payload.decision, user.id, request.state.correlation_id)
        if payload.decision == "APPROVED":
            app.decision_document = {
                "application_id": app.id,
                "document_hash": app.document_hash,
                "reviewer_id": user.id,
                "reason": payload.reason,
                "result": "APPROVED",
                "approved_version": app.version,
            }
            app.decision_hash = digest(app.decision_document)
            transition(
                session, app, "AWAITING_OFFICER_SIGNATURE", "system:decision", request.state.correlation_id
            )
        elif payload.decision == "REJECTED":
            notify(session, app)
        session.commit()
        return view(app, session)

    @api.post(prefix + "/applications/{application_id}/sign-decision", response_model=ApplicationView)
    def sign_decision(application_id: UUID, payload: SignCommand, request: Request, session: DB, user: Actor):
        app = accessible(session, application_id, user, lock=True)
        require_role(user, "officer")
        check_version(app, payload.expected_version)
        if app.business_status != "AWAITING_OFFICER_SIGNATURE":
            raise DomainError(409, "INVALID_TRANSITION", "Нет решения для подписания")
        if app.applicant_id == user.id:
            raise DomainError(403, "SIGNER_ROLE_FORBIDDEN", "Подписанты должны быть разными")
        verify_applicant_signature(session, app, signing_secret)
        add_signature(session, app, user, "OFFICER", payload.document_hash, signing_secret)
        transition(session, app, "COMPLETED", user.id, request.state.correlation_id)
        notify(session, app)
        session.commit()
        return view(app, session)

    @api.post(prefix + "/applications/{application_id}/cancel", response_model=ApplicationView)
    def cancel(application_id: UUID, payload: VersionCommand, request: Request, session: DB, user: Actor):
        app = accessible(session, application_id, user, lock=True)
        require_role(user, "applicant")
        check_version(app, payload.expected_version)
        transition(session, app, "CANCELLED", user.id, request.state.correlation_id)
        session.commit()
        return view(app, session)

    @api.get(prefix + "/applications/{application_id}/audit")
    def audit(application_id: UUID, session: DB, user: Actor):
        app = accessible(session, application_id, user)
        rows = session.scalars(
            select(AuditEvent).where(AuditEvent.application_id == app.id).order_by(AuditEvent.version)
        ).all()
        return [
            {
                "id": r.id,
                "version": r.version,
                "actor": r.actor if user.role != "applicant" else "redacted",
                "action": r.action,
                "before": r.before,
                "after": r.after,
                "correlation_id": r.correlation_id,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in rows
        ]

    @api.get(prefix + "/applications/{application_id}/integrations")
    def integrations(application_id: UUID, session: DB, user: Actor):
        app = accessible(session, application_id, user)
        rows = session.scalars(
            select(ExternalCheck)
            .where(ExternalCheck.application_id == app.id)
            .order_by(ExternalCheck.created_at)
        ).all()
        return [
            {
                "id": r.id,
                "provider": r.provider,
                "attempt": r.attempt,
                "outcome": r.outcome,
                "correlation_id": r.correlation_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    @api.get(prefix + "/monitor")
    def monitor(session: DB, user: Actor):
        if user.role == "applicant":
            raise DomainError(403, "ROLE_FORBIDDEN", "Монитор доступен служебным ролям")
        rows = session.execute(
            select(Application.business_status, func.count())
            .where(Application.tenant_id == user.tenant_id)
            .group_by(Application.business_status)
        ).all()
        checks = session.execute(
            select(ExternalCheck.outcome, func.count())
            .join(Application, Application.id == ExternalCheck.application_id)
            .where(Application.tenant_id == user.tenant_id)
            .group_by(ExternalCheck.outcome)
        ).all()
        return {
            "build": "0.1.0",
            "stage": "1-reference",
            "profile": "baseline",
            "scenario": "reference-flow",
            "seed": int(__import__("os").getenv("SEED", "42")),
            "tenant": session.get(Tenant, user.tenant_id).name,
            "statuses": dict(rows),
            "checks": dict(checks),
            "registry": "local-reference",
            "queue": "BackgroundTasks (non-durable)",
            "dlq": "not-in-stage-1",
            "signature": "HMAC educational simulation",
        }

    dist = config.ROOT / "frontend/demo-portal/dist"
    if dist.exists():
        api.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @api.get("/", include_in_schema=False)
        def portal():
            return FileResponse(dist / "index.html")

    return api
