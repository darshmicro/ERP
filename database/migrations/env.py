"""Alembic environment. Uses the migration account URL when provided (DDL rights), else the app URL."""
import os

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401
from app.core.db import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return (config.get_main_option("sqlalchemy.url") or os.environ.get("MERP_MIGRATION_DATABASE_URL")
            or os.environ.get("MERP_DATABASE_URL") or "sqlite:///./merp_dev.db")


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
