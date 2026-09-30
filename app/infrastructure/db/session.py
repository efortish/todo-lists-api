"""Engine and session factory creation."""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def build_engine(database_url: str) -> Engine:
    """Create an engine, adapting SQLite so it behaves like the production database."""
    if not database_url.startswith("sqlite"):
        return create_engine(database_url, pool_pre_ping=True)

    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if database_url in ("sqlite://", "sqlite:///:memory:"):
        # One shared connection, otherwise every session would see a new empty database.
        kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        # SQLite ignores ON DELETE CASCADE / SET NULL unless this is on.
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory. Objects stay usable after commit (no expire)."""
    return sessionmaker(bind=engine, expire_on_commit=False)
