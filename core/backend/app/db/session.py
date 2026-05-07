# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

_engine = None


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite kullanılıyorsa DB dosyasının dizinini oluştur."""
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path_str = url[len(prefix):]
        # sqlite:////abs/path → path starts with /
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)


def get_engine():
    """Lazy singleton SQLModel engine."""
    global _engine
    if _engine is None:
        _ensure_sqlite_dir(settings.database_url)
        connect_args: dict = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            settings.database_url,
            echo=False,
            connect_args=connect_args,
        )
    return _engine


def init_db() -> None:
    """Startup hook — tabloları oluştur."""
    # models'ı import etmek gerekiyor ki SQLModel metadata'sına kaydolsun
    from app.db import models  # noqa: F401
    from app.db import tenant_models  # noqa: F401  # T-009
    from app.auth.oauth import models as _oauth_models  # noqa: F401  # T-003

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency — request scope'lu session."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def get_session_sync() -> Iterator[Session]:
    """017 — MCP tool / non-FastAPI sync context manager.

    MCP tool'lari async ama DB query'leri sync (SQLModel + sqlite3 driver).
    `with get_session_sync() as db: ...` pattern ile session lifecycle yonet.
    """
    with Session(get_engine()) as session:
        yield session
