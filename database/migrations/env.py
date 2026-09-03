"""
Alembic environment. Imports the backend's SQLModel metadata (all six core
tables) so `alembic revision --autogenerate` produces accurate diffs, and
pulls the live DATABASE_URL from the backend's Settings so a single source
of truth is used for both the app and migrations.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `backend/app` importable when running Alembic from database/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.config import settings  # noqa: E402
from app.models import *  # noqa: E402,F401,F403 — registers all tables on SQLModel.metadata
from sqlmodel import SQLModel  # noqa: E402

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=lambda obj, name, type_, reflected, compare_to: (
                # Skip PostGIS's internal spatial_ref_sys table in diffs.
                not (type_ == "table" and name == "spatial_ref_sys")
            ),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
