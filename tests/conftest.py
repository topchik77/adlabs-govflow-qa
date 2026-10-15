import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from govflow.api import create_app
from govflow.config import database_url
from govflow.models import Base, User
from govflow.security import issue_token
from govflow.seed import seed_data
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
TEST_PASSWORD = "synthetic-test-password-only"
TEST_JWT_SECRET = "isolated-test-jwt-secret-" * 3
TEST_SIGNATURE_SECRET = "isolated-test-signature-secret-" * 3


@pytest.fixture(scope="session")
def pg_url():
    source = make_url(os.getenv("TEST_DATABASE_URL", database_url()))
    name = "govflow_test_" + uuid.uuid4().hex
    admin = create_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    target = source.set(database=name).render_as_string(hide_password=False)
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = target
    try:
        command.upgrade(Config(str(ROOT / "services/core-api/alembic.ini")), "head")
        seed_engine = create_engine(target)
        with Session(seed_engine) as session:
            seed_data(session, TEST_PASSWORD)
            session.commit()
        seed_engine.dispose()
        yield target
    finally:
        if old is not None:
            os.environ["DATABASE_URL"] = old
        else:
            os.environ.pop("DATABASE_URL", None)
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def app(pg_url):
    app = create_app(pg_url, TEST_JWT_SECRET, TEST_SIGNATURE_SECRET)
    with app.state.engine.begin() as connection:
        tables = [t.name for t in Base.metadata.sorted_tables if t.name not in {"users", "tenants"}]
        connection.execute(text("TRUNCATE " + ", ".join(tables) + " CASCADE"))
        connection.execute(text("UPDATE users SET active = true"))
        connection.execute(text("UPDATE tenants SET active = true"))
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth(app):
    def headers(username="applicant.a"):
        with app.state.factory() as session:
            user = session.scalar(select(User).where(User.username == username))
            token = issue_token(user, TEST_JWT_SECRET)
        return {"Authorization": "Bearer " + token, "X-Correlation-ID": "pytest-reference"}

    return headers


@pytest.fixture
def flow(client, auth):
    class Flow:
        def create(self, user="applicant.a", **extra):
            result = client.post(
                "/api/v1/applications",
                headers=auth(user),
                json={
                    "type": "PERMIT",
                    "title": "Учебное разрешение",
                    "description": "Только синтетические данные для QA",
                    **extra,
                },
            )
            assert result.status_code == 201, result.text
            return result.json()

        def command(self, app, endpoint, user="applicant.a", **extra):
            headers = auth(user)
            if endpoint == "submit":
                headers["Idempotency-Key"] = extra.pop("key", "submit-" + str(app["document_version"]))
            return client.post(
                f"/api/v1/applications/{app['id']}/{endpoint}",
                headers=headers,
                json={"expected_version": app["version"], **extra},
            )

        def attach(self, app):
            result = client.post(
                f"/api/v1/applications/{app['id']}/attachments",
                headers=auth(),
                data={"expected_version": app["version"]},
                files={"file": ("synthetic.pdf", b"%PDF-1.7\nsynthetic fixture\n%%EOF", "application/pdf")},
            )
            assert result.status_code == 201, result.text
            return result.json()

        def signed(self):
            app = self.attach(self.create())
            prepared = self.command(app, "prepare-signature")
            assert prepared.status_code == 200, prepared.text
            app = prepared.json()
            signed = self.command(app, "sign", document_hash=app["document_hash"])
            assert signed.status_code == 200, signed.text
            return signed.json()

        def submitted(self):
            app = self.signed()
            result = self.command(app, "submit")
            assert result.status_code == 202, result.text
            current = client.get(f"/api/v1/applications/{app['id']}", headers=auth()).json()
            assert current["business_status"] == "UNDER_REVIEW"
            return current

        def approved(self):
            result = self.command(
                self.submitted(),
                "review",
                "reviewer.a",
                decision="APPROVED",
                reason="Сведения проверены в учебном реестре",
            )
            assert result.status_code == 200, result.text
            return result.json()

    return Flow()
