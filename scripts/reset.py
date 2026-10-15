"""Explicit reset restricted to the dedicated local GovFlow database."""

import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "services/core-api"))
from govflow.config import database_url  # noqa: E402
from govflow.models import Base  # noqa: E402
from govflow.seed import seed_data  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--confirm-local-reset", action="store_true", required=True)
parser.parse_args()
url = make_url(database_url())
if url.database != "govflow" or url.host not in {"127.0.0.1", "localhost", "db"}:
    raise SystemExit("Reset is restricted to local database 'govflow'.")
engine = create_engine(url)
Base.metadata.drop_all(engine)
# Keep Alembic revision after replacing the schema with the same migrated version.
with engine.begin() as conn:
    conn.exec_driver_sql("DELETE FROM alembic_version")
command.upgrade(Config(str(root / "services/core-api/alembic.ini")), "head")
from sqlalchemy.orm import Session  # noqa: E402

with Session(engine) as session:
    seed_data(session, os.environ["DEMO_PASSWORD"], int(os.getenv("SEED", "42")))
    session.commit()
print("Local GovFlow database reset and seeded. Existing tokens must be discarded.")
