import os
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from govflow.config import database_url
from govflow.models import Tenant, User
from govflow.security import passwords

ROLES = ["applicant", "reviewer", "officer", "tenant_admin", "qa_observer"]


def seeded_id(seed, label):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"govflow-lab:{seed}:{label}"))


def seed_data(session, password, seed=42):
    for tenant_code, name in [("a", "Север · CivicTech"), ("b", "Юг · CivicTech")]:
        tenant_id = seeded_id(seed, f"tenant-{tenant_code}")
        if not session.get(Tenant, tenant_id):
            session.add(Tenant(id=tenant_id, name=name))
            session.flush()
        for role in ROLES + ["applicant2"]:
            username = f"{role}.{tenant_code}"
            if not session.scalar(select(User).where(User.username == username)):
                session.add(
                    User(
                        id=seeded_id(seed, username),
                        tenant_id=tenant_id,
                        username=username,
                        password_hash=passwords.hash(password),
                        role="applicant" if role == "applicant2" else role,
                    )
                )
        session.flush()


def main():
    password = os.environ.get("DEMO_PASSWORD", "")
    if len(password) < 12:
        raise RuntimeError("Generate local credentials using python scripts/configure.py")
    with Session(create_engine(database_url())) as session:
        seed_data(session, password, int(os.getenv("SEED", "42")))
        session.commit()
    print("Seed ready: tenants a/b; applicant, applicant2, reviewer, officer, tenant_admin, qa_observer.")
    print("Local password is in .env (DEMO_PASSWORD). No credentials are logged.")


if __name__ == "__main__":
    main()
