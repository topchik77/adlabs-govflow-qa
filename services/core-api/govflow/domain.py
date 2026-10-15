import hashlib
import hmac
import json

from sqlalchemy import select

from govflow.models import (
    Application,
    Attachment,
    AuditEvent,
    ExternalCheck,
    Notification,
    OutboxEvent,
    Revision,
    Signature,
    now,
)


class DomainError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}


TRANSITIONS = {
    "DRAFT": {"AWAITING_APPLICANT_SIGNATURE", "CANCELLED"},
    "AWAITING_APPLICANT_SIGNATURE": {"SUBMITTED"},
    "SUBMITTED": {"VALIDATING"},
    "VALIDATING": {"UNDER_REVIEW"},
    "UNDER_REVIEW": {"NEEDS_CORRECTION", "APPROVED", "REJECTED"},
    "NEEDS_CORRECTION": {"AWAITING_APPLICANT_SIGNATURE", "CANCELLED"},
    "APPROVED": {"AWAITING_OFFICER_SIGNATURE"},
    "AWAITING_OFFICER_SIGNATURE": {"COMPLETED"},
}
EDITABLE = {"DRAFT", "NEEDS_CORRECTION", "AWAITING_APPLICANT_SIGNATURE"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def require_role(user, role):
    if user.role != role:
        raise DomainError(
            403,
            "SIGNER_ROLE_FORBIDDEN" if role == "officer" else "ROLE_FORBIDDEN",
            "Недостаточно прав для этой операции",
        )


def check_version(app, expected):
    if app.version != expected:
        raise DomainError(
            409,
            "VERSION_CONFLICT",
            "Документ уже изменён. Обновите карточку.",
            {"current_version": app.version},
        )


def require_editable(app):
    if app.business_status not in EDITABLE:
        raise DomainError(409, "INVALID_TRANSITION", "Документ недоступен для редактирования")


def accessible(session, application_id, user, lock=False):
    query = select(Application).where(
        Application.id == str(application_id), Application.tenant_id == user.tenant_id
    )
    if user.role == "applicant":
        query = query.where(Application.applicant_id == user.id)
    if user.role == "qa_observer":
        raise DomainError(403, "ROLE_FORBIDDEN", "Наблюдателю доступен обезличенный монитор")
    if lock:
        query = query.with_for_update()
    app = session.scalar(query)
    if not app:
        raise DomainError(404, "NOT_FOUND", "Заявление не найдено")
    return app


def record(session, app, actor, action, correlation, before=None, initial=False):
    if not initial:
        app.version += 1
    app.updated_at = now()
    session.add(
        AuditEvent(
            application_id=app.id,
            version=app.version,
            actor=actor,
            action=action,
            before=before,
            after=app.business_status,
            correlation_id=correlation,
        )
    )
    session.add(
        OutboxEvent(
            aggregate_id=app.id,
            event_type=action,
            event_version=app.version,
            payload={
                "application_id": app.id,
                "status": app.business_status,
                "version": app.version,
                "correlation_id": correlation,
            },
        )
    )
    session.flush()


def transition(session, app, target, actor, correlation):
    before = app.business_status
    if target not in TRANSITIONS.get(before, set()):
        raise DomainError(409, "INVALID_TRANSITION", f"Недопустимый переход {before} → {target}")
    app.business_status = target
    record(session, app, actor, target, correlation, before)


def document_snapshot(session, app, increment=True):
    session.flush()
    if increment:
        app.document_version += 1
    files = session.scalars(
        select(Attachment).where(Attachment.application_id == app.id).order_by(Attachment.id)
    ).all()
    snapshot = {
        "application_id": app.id,
        "document_version": app.document_version,
        "type": app.type,
        "title": app.title,
        "description": app.description,
        "attachments": [{"id": f.id, "sha256": f.sha256, "mime": f.mime} for f in files],
    }
    app.document_hash = digest(snapshot)
    session.add(
        Revision(
            application_id=app.id,
            version=app.document_version,
            form_json=snapshot,
            document_hash=app.document_hash,
        )
    )
    # Historical signatures remain evidence for old bytes; only the current
    # document_version is eligible for authorization and submission.
    session.flush()


def signature_proof(app, signer_id, kind, doc_hash, secret):
    payload = f"{app.id}:{app.document_version}:{kind}:{signer_id}:{doc_hash}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def add_signature(session, app, user, kind, supplied_hash, secret):
    expected = app.document_hash if kind == "APPLICANT" else app.decision_hash
    if not expected or not hmac.compare_digest(expected, supplied_hash):
        raise DomainError(422, "DOCUMENT_HASH_MISMATCH", "Хеш не соответствует актуальному документу")
    existing = session.scalar(
        select(Signature).where(
            Signature.application_id == app.id,
            Signature.kind == kind,
            Signature.document_version == app.document_version,
        )
    )
    if existing:
        raise DomainError(409, "ALREADY_SIGNED", "Эта версия уже подписана")
    session.add(
        Signature(
            application_id=app.id,
            document_hash=expected,
            document_version=app.document_version,
            signer_id=user.id,
            signer_role=user.role,
            kind=kind,
            proof=signature_proof(app, user.id, kind, expected, secret),
        )
    )
    session.flush()


def verify_applicant_signature(session, app, secret):
    sig = session.scalar(
        select(Signature).where(
            Signature.application_id == app.id,
            Signature.kind == "APPLICANT",
            Signature.document_version == app.document_version,
        )
    )
    if not sig or sig.document_hash != app.document_hash or sig.signer_id != app.applicant_id:
        raise DomainError(422, "SIGNATURE_INVALID", "Нужна подпись заявителя на актуальной версии")
    expected = signature_proof(app, sig.signer_id, sig.kind, app.document_hash, secret)
    if sig.signer_role != "applicant" or not hmac.compare_digest(sig.proof, expected):
        raise DomainError(422, "SIGNATURE_INVALID", "Учебная подпись не прошла проверку")


def local_process(factory, application_id, correlation):
    """Stage 1 local reference, not a broker/worker or an external Registry."""
    with factory.begin() as session:
        app = session.scalar(select(Application).where(Application.id == application_id).with_for_update())
        if not app or app.business_status != "SUBMITTED":
            return
        transition(session, app, "VALIDATING", "system:local-reference", correlation)
        app.processing_status = "SUCCEEDED"
        session.add(ExternalCheck(application_id=app.id, outcome="VALID", correlation_id=correlation))
        transition(session, app, "UNDER_REVIEW", "system:local-reference", correlation)


def notify(session, app):
    session.add(Notification(application_id=app.id, recipient_id=app.applicant_id, kind="RESULT"))
