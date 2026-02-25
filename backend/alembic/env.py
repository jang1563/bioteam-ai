"""Alembic environment — auto-detect SQLModel table definitions.

Reads DATABASE_URL from app.config.settings (same as the app),
so migrations use the same DB that the server uses.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlmodel import SQLModel, create_engine

# Alembic Config object
config = context.config

# Set up Python logging from .ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Import all SQLModel table classes so metadata includes them ---
from app.models.cost import CostRecord  # noqa: F401, E402
from app.models.digest import DigestEntry, DigestReport, TopicProfile  # noqa: F401, E402
from app.models.evidence import ContradictionEntry, DataRegistry, Evidence  # noqa: F401, E402
from app.models.memory import EpisodicEvent  # noqa: F401, E402
from app.models.messages import AgentMessage, Conversation, ConversationTurn  # noqa: F401, E402
from app.models.negative_result import NegativeResult  # noqa: F401, E402
from app.models.task import Project, Task  # noqa: F401, E402
from app.models.workflow import StepCheckpoint, WorkflowInstance  # noqa: F401, E402

target_metadata = SQLModel.metadata

# --- Get DB URL from settings (same source of truth as the app) ---
from app.config import settings  # noqa: E402

DATABASE_URL = settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without DB connection)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (applies directly to DB)."""
    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Required for SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
