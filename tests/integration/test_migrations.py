"""The Alembic migrations must build exactly the schema the ORM models describe."""

import pytest

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from app.infrastructure.db.models import Base
from app.infrastructure.db.session import build_engine

pytestmark = pytest.mark.integration


def test_migrations_match_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    config = Config("alembic.ini")
    config.attributes["database_url"] = url
    config.attributes["configure_logger"] = False

    command.upgrade(config, "head")

    engine = build_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()
    assert diff == []

    command.downgrade(config, "base")
