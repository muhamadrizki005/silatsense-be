from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import QueuePool, NullPool
from app.core.config import settings


class Base(DeclarativeBase):
    pass


def engine_options(config):
    """Keep SQLite's dialect-specific pool; explicitly budget network engines."""
    url = make_url(config.database_url)
    options = {"pool_pre_ping": True, "hide_parameters": True}
    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
        return options
    if config.db_pool_mode == "null":
        # No idle retention; unlike QueuePool this does NOT cap concurrency.
        options["poolclass"] = NullPool
    else:
        options.update(
            poolclass=QueuePool,
            pool_size=config.db_pool_size,
            max_overflow=config.db_max_overflow,
            pool_timeout=config.db_pool_timeout_seconds,
            pool_recycle=config.db_pool_recycle_seconds,
            pool_use_lifo=True,
        )
    if url.drivername in {"mysql+pymysql", "mariadb+pymysql"}:
        options["connect_args"] = {
            "connect_timeout": config.db_connect_timeout_seconds,
            "read_timeout": config.db_read_timeout_seconds,
            "write_timeout": config.db_write_timeout_seconds,
        }
    return options


def create_database_engine(config=settings):
    return create_engine(config.database_url, **engine_options(config))


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
