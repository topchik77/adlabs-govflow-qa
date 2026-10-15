from alembic import context
from govflow.config import database_url
from govflow.models import Base
from sqlalchemy import create_engine, pool

target_metadata = Base.metadata


def run_migrations():
    if context.is_offline_mode():
        context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(database_url(), poolclass=pool.NullPool)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()


run_migrations()
