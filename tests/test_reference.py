from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from conftest import TEST_JWT_SECRET, TEST_PASSWORD
from govflow.domain import TRANSITIONS, DomainError, local_process, transition
from govflow.models import (
    Application,
    Attachment,
    AuditEvent,
    ExternalCheck,
    Notification,
    OutboxEvent,
    Revision,
    Signature,
    Tenant,
    User,
)
from govflow.security import issue_token
from govflow.seed import seeded_id
from sqlalchemy import func, select


def test_complete_flow_two_distinct_signatures_and_contiguous_audit(flow, client, auth, app):
    a = flow.approved()
    completed = flow.command(a, "sign-decision", "officer.a", document_hash=a["decision_hash"])
    assert completed.status_code == 200
    a = completed.json()
    assert a["business_status"] == "COMPLETED"
    assert a["applicant_signed"] and a["officer_signed"]
    events = client.get(f"/api/v1/applications/{a['id']}/audit", headers=auth("reviewer.a")).json()
    assert [e["version"] for e in events] == list(range(1, a["version"] + 1))
    assert [e["after"] for e in events if e["action"] == e["after"]] == [
        "AWAITING_APPLICANT_SIGNATURE",
        "SUBMITTED",
        "VALIDATING",
        "UNDER_REVIEW",
        "APPROVED",
        "AWAITING_OFFICER_SIGNATURE",
        "COMPLETED",
    ]
    with app.state.factory() as db:
        signatures = db.scalars(select(Signature)).all()
        assert len({s.signer_id for s in signatures}) == 2
        assert db.scalar(select(func.count()).select_from(Notification)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == a["version"]


@pytest.mark.parametrize(
    "other", ["applicant.b", "reviewer.b", "officer.b", "tenant_admin.b", "applicant2.a"]
)
def test_object_isolation_every_read_surface(flow, client, auth, other):
    a = flow.attach(flow.create())
    base = f"/api/v1/applications/{a['id']}"
    for path in [
        base,
        base + "/audit",
        base + "/integrations",
        base + "/attachments/" + a["attachments"][0]["id"],
    ]:
        result = client.get(path, headers=auth(other))
        assert result.status_code == 404
        assert a["title"] not in result.text
    assert client.get("/api/v1/applications", headers=auth(other)).json()["total"] == 0


def test_cross_tenant_commands_do_not_mutate(flow, client, auth, app):
    a = flow.submitted()
    r = flow.command(a, "review", "reviewer.b", decision="APPROVED", reason="Неверный tenant")
    assert r.status_code == 404
    with app.state.factory() as db:
        assert db.get(Application, a["id"]).version == a["version"]


def test_unknown_uuid_is_404(client, auth):
    r = client.get("/api/v1/applications/00000000-0000-0000-0000-000000000001", headers=auth())
    assert r.status_code == 404


def test_login_real_password_hash_and_no_secret_reflection(client):
    bad = client.post("/api/v1/auth/login", json={"username": "applicant.a", "password": "wrong-secret"})
    assert bad.status_code == 401 and "wrong-secret" not in bad.text
    good = client.post("/api/v1/auth/login", json={"username": "applicant.a", "password": TEST_PASSWORD})
    assert good.status_code == 200
    claims = jwt.decode(good.json()["access_token"], TEST_JWT_SECRET, algorithms=["HS256"])
    assert {"sub", "tenant_id", "role", "exp", "jti"}.issubset(claims)
    assert claims["role"] == "applicant"


@pytest.mark.parametrize("mode", ["missing", "invalid", "expired", "algorithm", "missing-jti", "role"])
def test_auth_rejects_invalid_claims(client, app, mode):
    with app.state.factory() as db:
        user = db.scalar(select(User).where(User.username == "applicant.a"))
        token = issue_token(user, TEST_JWT_SECRET)
    claims = jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])
    if mode == "expired":
        claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    if mode == "missing-jti":
        del claims["jti"]
    if mode == "role":
        claims["role"] = "officer"
    token = jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS384" if mode == "algorithm" else "HS256")
    headers = (
        {} if mode == "missing" else {"Authorization": "Bearer " + ("bad" if mode == "invalid" else token)}
    )
    assert client.get("/api/v1/applications", headers=headers).status_code == 401


@pytest.mark.parametrize("kind", ["user", "tenant"])
def test_disabled_identity_rejects_previously_issued_token(client, auth, app, kind):
    headers = auth()
    with app.state.factory.begin() as db:
        user = db.scalar(select(User).where(User.username == "applicant.a"))
        (user if kind == "user" else db.get(Tenant, user.tenant_id)).active = False
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_mass_assignment_forbidden(flow, client, auth):
    r = client.post(
        "/api/v1/applications",
        headers=auth(),
        json={
            "title": "Test form",
            "description": "Synthetic data",
            "tenant_id": "other",
            "business_status": "COMPLETED",
        },
    )
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    assert client.get("/api/v1/applications", headers=auth()).json()["total"] == 0


@pytest.mark.parametrize("role", ["reviewer.a", "officer.a", "tenant_admin.a", "qa_observer.a"])
def test_non_applicant_cannot_create(client, auth, role):
    r = client.post(
        "/api/v1/applications",
        headers=auth(role),
        json={"title": "Synthetic", "description": "Synthetic information"},
    )
    assert r.status_code == 403


def test_stale_edit_rolls_back(flow, client, auth, app):
    a = flow.create()
    payload = {
        "title": "Updated synthetic title",
        "description": a["description"],
        "type": a["type"],
        "expected_version": a["version"],
    }
    path = f"/api/v1/applications/{a['id']}"
    assert client.patch(path, headers=auth(), json=payload).status_code == 200
    r = client.patch(path, headers=auth(), json={**payload, "title": "Stale synthetic title"})
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    with app.state.factory() as db:
        assert db.get(Application, a["id"]).title == payload["title"]
        assert db.scalar(select(func.count()).select_from(Revision)) == 2


def test_concurrent_edits_one_winner(flow, client, auth):
    a = flow.create()
    headers = auth()

    def edit(index):
        return client.patch(
            f"/api/v1/applications/{a['id']}",
            headers=headers,
            json={
                "title": f"Concurrent title {index}",
                "description": a["description"],
                "type": a["type"],
                "expected_version": a["version"],
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(edit, range(5)))
    assert results.count(200) == 1 and results.count(409) == 4


def test_prepare_requires_attachment(flow):
    r = flow.command(flow.create(), "prepare-signature")
    assert r.status_code == 422 and r.json()["code"] == "ATTACHMENT_REQUIRED"


def test_unsigned_submission_rejected_without_event(flow, app):
    a = flow.attach(flow.create())
    a = flow.command(a, "prepare-signature").json()
    r = flow.command(a, "submit")
    assert r.status_code == 422 and r.json()["code"] == "SIGNATURE_INVALID"
    with app.state.factory() as db:
        assert db.get(Application, a["id"]).version == a["version"]
        assert db.scalar(select(func.count()).select_from(ExternalCheck)) == 0


def test_wrong_hash_does_not_sign(flow, app):
    a = flow.attach(flow.create())
    a = flow.command(a, "prepare-signature").json()
    r = flow.command(a, "sign", document_hash="0" * 64)
    assert r.status_code == 422 and r.json()["code"] == "DOCUMENT_HASH_MISMATCH"
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(Signature)) == 0


def test_edit_invalidates_signed_revision(flow, client, auth):
    a = flow.signed()
    r = client.patch(
        f"/api/v1/applications/{a['id']}",
        headers=auth(),
        json={
            "title": "New signed document title",
            "description": a["description"],
            "type": a["type"],
            "expected_version": a["version"],
        },
    )
    b = r.json()
    assert b["document_version"] == a["document_version"] + 1
    assert b["document_hash"] != a["document_hash"] and not b["applicant_signed"]
    assert flow.command(b, "submit").json()["code"] == "SIGNATURE_INVALID"
    assert (
        flow.command(b, "sign", document_hash=a["document_hash"]).json()["code"] == "DOCUMENT_HASH_MISMATCH"
    )


def test_corrupt_stored_proof_detected(flow, app):
    a = flow.signed()
    with app.state.factory.begin() as db:
        db.scalar(select(Signature)).proof = "f" * 64
    r = flow.command(a, "submit")
    assert r.status_code == 422 and r.json()["code"] == "SIGNATURE_INVALID"


def test_concurrent_submit_deduplicates_and_replays_original_response(flow, client, auth, app):
    a = flow.signed()
    headers = {**auth(), "Idempotency-Key": "concurrent-10"}

    def submit(_):
        r = client.post(
            f"/api/v1/applications/{a['id']}/submit", headers=headers, json={"expected_version": a["version"]}
        )
        assert r.status_code == 202, r.text
        return r.json()

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(submit, range(10)))
    assert all(response == responses[0] for response in responses)
    with app.state.factory() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(OutboxEvent).where(OutboxEvent.event_type == "SUBMITTED")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(ExternalCheck)) == 1
        assert db.get(Application, a["id"]).business_status == "UNDER_REVIEW"
    conflict = client.post(
        f"/api/v1/applications/{a['id']}/submit", headers=headers, json={"expected_version": a["version"] + 1}
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_submit_requires_key(flow, client, auth):
    a = flow.signed()
    r = client.post(
        f"/api/v1/applications/{a['id']}/submit", headers=auth(), json={"expected_version": a["version"]}
    )
    assert r.status_code == 422


def test_review_requires_successful_check_and_reason(flow):
    a = flow.create()
    r = flow.command(a, "review", "reviewer.a", decision="APPROVED", reason="Test reason")
    assert r.status_code == 409
    a = flow.submitted()
    assert flow.command(a, "review", "reviewer.a", decision="APPROVED", reason=" ").status_code == 422
    assert (
        flow.command(a, "review", "officer.a", decision="APPROVED", reason="Valid reason").status_code == 403
    )


def test_officer_only_and_correct_decision_hash(flow):
    a = flow.approved()
    assert flow.command(a, "sign-decision", "reviewer.a", document_hash=a["decision_hash"]).status_code == 403
    assert (
        flow.command(a, "sign-decision", "applicant.a", document_hash=a["decision_hash"]).status_code == 403
    )
    assert flow.command(a, "sign-decision", "officer.a", document_hash=a["document_hash"]).status_code == 422


def test_correction_requires_new_signature_and_can_complete(flow, client, auth):
    a = flow.submitted()
    r = flow.command(
        a, "review", "reviewer.a", decision="NEEDS_CORRECTION", reason="Уточнить описание объекта"
    )
    a = r.json()
    old_revision = a["document_version"]
    a = client.patch(
        f"/api/v1/applications/{a['id']}",
        headers=auth(),
        json={
            "title": a["title"],
            "type": a["type"],
            "description": "Исправленные синтетические сведения",
            "expected_version": a["version"],
        },
    ).json()
    a = flow.command(a, "prepare-signature").json()
    assert a["document_version"] > old_revision
    assert not a["applicant_signed"]
    a = flow.command(a, "sign", document_hash=a["document_hash"]).json()
    assert flow.command(a, "submit", key="correction-new-command").status_code == 202
    a = client.get(f"/api/v1/applications/{a['id']}", headers=auth()).json()
    assert a["business_status"] == "UNDER_REVIEW" and len(a["reviews"]) == 1


@pytest.mark.parametrize("terminal", ["CANCELLED", "REJECTED", "COMPLETED"])
def test_terminal_states_immutable(flow, client, auth, terminal):
    if terminal == "CANCELLED":
        a = flow.command(flow.create(), "cancel").json()
    elif terminal == "REJECTED":
        a = flow.command(
            flow.submitted(),
            "review",
            "reviewer.a",
            decision="REJECTED",
            reason="Синтетические сведения не соответствуют требованиям",
        ).json()
    else:
        a = flow.approved()
        a = flow.command(a, "sign-decision", "officer.a", document_hash=a["decision_hash"]).json()
    assert a["business_status"] == terminal
    assert flow.command(a, "cancel").status_code == 409
    r = client.patch(
        f"/api/v1/applications/{a['id']}",
        headers=auth(),
        json={
            "expected_version": a["version"],
            "type": a["type"],
            "title": "Changed terminal",
            "description": a["description"],
        },
    )
    assert r.status_code == 409
    current = client.get(f"/api/v1/applications/{a['id']}", headers=auth()).json()
    assert current["version"] == a["version"]


@pytest.mark.parametrize(
    "filename,mime,content,status,code",
    [
        ("script.html", "text/html", b"<html>", 415, "UNSUPPORTED_MEDIA_TYPE"),
        ("fake.pdf", "application/pdf", b"not a PDF", 415, "CONTENT_TYPE_MISMATCH"),
        ("../escape.pdf", "application/pdf", b"%PDF-1.7", 422, "UNSAFE_FILENAME"),
        ("huge.pdf", "application/pdf", b"%PDF-" + b"x" * (5 * 1024 * 1024), 413, "ATTACHMENT_TOO_LARGE"),
    ],
    ids=["unsupported-mime", "spoofed-pdf", "unsafe-path", "over-5mib"],
)
def test_attachment_boundaries_are_atomic(flow, client, auth, app, filename, mime, content, status, code):
    a = flow.create()
    r = client.post(
        f"/api/v1/applications/{a['id']}/attachments",
        headers=auth(),
        data={"expected_version": a["version"]},
        files={"file": (filename, content, mime)},
    )
    assert r.status_code == status and r.json()["code"] == code
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(Attachment)) == 0
        assert db.get(Application, a["id"]).version == a["version"]


def test_pagination_filters_tenant_before_limit(flow, client, auth):
    flow.create("applicant.b", title="Other tenant newest")
    for i in range(3):
        flow.create(title=f"Tenant A item {i}")
    result = client.get(
        "/api/v1/applications?limit=1&offset=1&sort=oldest&status=DRAFT", headers=auth()
    ).json()
    assert result["total"] == 3 and len(result["items"]) == 1
    assert result["items"][0]["title"] == "Tenant A item 1"


def test_observer_only_anonymized_aggregates(flow, client, auth):
    a = flow.submitted()
    headers = auth("qa_observer.a")
    assert client.get("/api/v1/applications", headers=headers).status_code == 403
    assert client.get(f"/api/v1/applications/{a['id']}", headers=headers).status_code == 403
    result = client.get("/api/v1/monitor", headers=headers)
    assert result.status_code == 200
    assert result.json()["statuses"]["UNDER_REVIEW"] == 1
    assert a["title"] not in result.text and a["id"] not in result.text


def test_local_process_redelivery_and_late_call_have_no_effect(flow, app):
    a = flow.approved()
    local_process(app.state.factory, a["id"], "duplicate-delivery")
    with app.state.factory() as db:
        current = db.get(Application, a["id"])
        assert current.business_status == "AWAITING_OFFICER_SIGNATURE" and current.version == a["version"]
        assert db.scalar(select(func.count()).select_from(ExternalCheck)) == 1


def test_transaction_rollback_removes_state_audit_and_outbox(flow, app):
    a = flow.create()
    with pytest.raises(RuntimeError):
        with app.state.factory.begin() as db:
            current = db.get(Application, a["id"])
            transition(db, current, "CANCELLED", "test", "rollback-check")
            raise RuntimeError("controlled failure before commit")
    with app.state.factory() as db:
        assert db.get(Application, a["id"]).business_status == "DRAFT"
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_all_unlisted_state_transitions_rejected(flow, app):
    a = flow.create()
    states = set(TRANSITIONS) | {"COMPLETED", "REJECTED", "CANCELLED"}
    with app.state.factory() as db:
        current = db.get(Application, a["id"])
        for source in states:
            for target in states - TRANSITIONS.get(source, set()):
                current.business_status = source
                with pytest.raises(DomainError) as exc:
                    transition(db, current, target, "test", "illegal-transition")
                assert exc.value.code == "INVALID_TRANSITION"


def test_openapi_typed_contract_and_correlation(client, auth):
    schema = client.get("/openapi.json").json()
    path = schema["paths"]["/api/v1/applications/{application_id}/submit"]["post"]
    assert "202" in path["responses"]
    assert any(p["name"] == "idempotency-key" and p["required"] for p in path["parameters"])
    assert "ApplicationView" in schema["components"]["schemas"]
    r = client.get("/api/v1/auth/me", headers={**auth(), "X-Correlation-ID": "contract-001"})
    assert r.headers["X-Correlation-ID"] == "contract-001"
    assert client.get("/api/v1/ready").json()["status"] == "ready"


def test_seed_stable_ids_and_no_credentials_in_monitor(client, auth):
    assert seeded_id(42, "tenant-a") == seeded_id(42, "tenant-a")
    assert seeded_id(42, "tenant-a") != seeded_id(43, "tenant-a")
    r = client.get("/api/v1/monitor", headers=auth("qa_observer.a"))
    assert TEST_PASSWORD not in r.text and TEST_JWT_SECRET not in r.text


def test_input_validation_no_sensitive_echo(client, auth):
    r = client.post(
        "/api/v1/auth/login", json={"username": "applicant.a", "password": "private-input", "extra": True}
    )
    assert r.status_code == 422 and "private-input" not in r.text
    r = client.post("/api/v1/applications", headers=auth(), json={"title": "ab", "description": "too short"})
    assert r.status_code == 422
