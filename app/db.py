from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings

_kw: dict = {}
if settings.database_url.startswith("sqlite"):
    _kw["connect_args"] = {"check_same_thread": False}
    if settings.database_url in ("sqlite://", "sqlite:///:memory:"):
        _kw["poolclass"] = StaticPool  # одна in-memory БД на все потоки (тесты)

engine = create_engine(settings.database_url, **_kw)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as db:
        yield db
