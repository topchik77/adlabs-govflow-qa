"""Populate real API examples and write sanitized HTTP + SQL evidence."""

import json
import os
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "services/core-api"))
from govflow.config import database_url  # noqa: E402
from govflow.models import AuditEvent, ExternalCheck, Notification, Signature  # noqa: E402

base = os.getenv("GOVFLOW_URL", "http://127.0.0.1:8014")
client = httpx.Client(base_url=base + "/api/v1", timeout=15)
tokens = {}
evidence = {
    "build": "0.1.0",
    "stage": "1-reference",
    "seed": int(os.getenv("SEED", "42")),
    "synthetic": True,
    "flows": [],
    "limitations": ["local-reference; no broker/HTTP Registry"],
}


def call(method, path, user="applicant.a", **kwargs):
    if user not in tokens:
        response = client.post(
            "/auth/login", json={"username": user, "password": os.environ["DEMO_PASSWORD"]}
        )
        response.raise_for_status()
        tokens[user] = response.json()["access_token"]
    headers = {"Authorization": "Bearer " + tokens[user], "X-Correlation-ID": "demo-reference-42"}
    headers.update(kwargs.pop("headers", {}))
    response = client.request(method, path, headers=headers, **kwargs)
    if response.is_error:
        raise RuntimeError(
            f"Demo failed: {method} {path} → {response.status_code} {response.json().get('code')}"
        )
    return response.json()


def command(app, action, user="applicant.a", **extra):
    headers = {"Idempotency-Key": f"demo-{app['id']}-{app['document_version']}"} if action == "submit" else {}
    result = call(
        "POST",
        f"/applications/{app['id']}/{action}",
        user,
        headers=headers,
        json={"expected_version": app["version"], **extra},
    )
    if action == "submit":
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = call("GET", f"/applications/{app['id']}")
            if result["business_status"] == "UNDER_REVIEW":
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("Local reference check did not complete within 10 seconds")
    return result


def sample_pdf():
    stream = b"BT /F1 16 Tf 50 750 Td (GOVFLOW - SYNTHETIC QA DOCUMENT) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    content = b"%PDF-1.4\n"
    positions = []
    for i, obj in enumerate(objects, 1):
        positions.append(len(content))
        content += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    offset = len(content)
    content += b"xref\n0 6\n0000000000 65535 f \n"
    content += b"".join(f"{position:010d} 00000 n \n".encode() for position in positions)
    return content + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF\n".encode()


existing = call("GET", "/applications?limit=100")["items"]
examples = [
    ("Демо · Разрешение на учебный павильон", "COMPLETED", "PERMIT"),
    ("Демо · Продление учебного разрешения", "UNDER_REVIEW", "RENEWAL"),
    ("Демо · Разрешение на учебную площадку", "NEEDS_CORRECTION", "PERMIT"),
    ("Демо · Новый синтетический объект", "DRAFT", "PERMIT"),
    ("Демо · Решение для подписи", "AWAITING_OFFICER_SIGNATURE", "PERMIT"),
]
for title, target, kind in examples:
    app = next((a for a in existing if a["title"] == title), None)
    if app is None:
        app = call(
            "POST",
            "/applications",
            json={
                "title": title,
                "type": kind,
                "description": "Синтетическое заявление CivicTech Solutions. "
                "Используется только в учебном QA-стенде.",
            },
        )
        if target != "DRAFT":
            app = call(
                "POST",
                f"/applications/{app['id']}/attachments",
                data={"expected_version": app["version"]},
                files={"file": ("synthetic-permit.pdf", sample_pdf(), "application/pdf")},
            )
            app = command(app, "prepare-signature")
            app = command(app, "sign", document_hash=app["document_hash"])
            app = command(app, "submit")
            if target == "NEEDS_CORRECTION":
                app = command(
                    app,
                    "review",
                    "reviewer.a",
                    decision="NEEDS_CORRECTION",
                    reason="Уточните синтетическое описание расположения учебного объекта.",
                )
            elif target in {"AWAITING_OFFICER_SIGNATURE", "COMPLETED"}:
                app = command(
                    app,
                    "review",
                    "reviewer.a",
                    decision="APPROVED",
                    reason="Синтетические сведения и вложение проверены; ограничений не выявлено.",
                )
                if target == "COMPLETED":
                    app = command(app, "sign-decision", "officer.a", document_hash=app["decision_hash"])
    events = call("GET", f"/applications/{app['id']}/audit", "reviewer.a")
    with Session(create_engine(database_url())) as db:
        counts = {
            model.__tablename__: db.scalar(
                select(func.count()).select_from(model).where(model.application_id == app["id"])
            )
            for model in [Signature, Notification, ExternalCheck, AuditEvent]
        }
    evidence["flows"].append(
        {
            "application_id": app["id"],
            "title": app["title"],
            "status": app["business_status"],
            "version": app["version"],
            "document_hash": app["document_hash"],
            "audit": events,
            "sql_counts": counts,
        }
    )

out = Path(
    os.getenv(
        "GOVFLOW_EVIDENCE",
        "/tmp/govflow-demo-evidence.json" if os.name != "nt" else str(root / "reports/demo-evidence.json"),
    )
)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
client.close()
print(f"Real API examples ready: {len(evidence['flows'])}; sanitized evidence: {out}")
