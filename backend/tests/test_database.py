from sqlalchemy import text

from app.db.session import SessionLocal


def test_database_connection():
    with SessionLocal() as session:
        result = session.execute(
            text("SELECT 1")
        )

        assert result.scalar() == 1