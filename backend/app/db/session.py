import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[2]


def _configured_data_dir() -> Path:
    configured_path = os.environ.get("AGENTDESK_DATA_DIR", "").strip()
    if not configured_path:
        return BACKEND_DIR / "data"

    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = BACKEND_DIR / path

    return path.resolve()


DATA_DIR = _configured_data_dir()
DATABASE_PATH = DATA_DIR / "agentdesk.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
