from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.schemas.company import CompanyUpdate
from app.services.company_service import CompanyService
from app.services.config_service import ConfigService

import app.models  # noqa: F401


def create_test_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:"
    )

    Base.metadata.create_all(engine)

    return Session(engine)


def test_config_service_creates_single_config():
    with create_test_session() as db:
        first = ConfigService.get_status(db)
        second = ConfigService.get_status(db)

        assert first.id == second.id
        assert first.installation_id == second.installation_id
        assert first.configured is False


def test_company_service_creates_and_updates_company():
    with create_test_session() as db:
        created = CompanyService.update(
            db,
            CompanyUpdate(
                name="AgentDesk Demo",
                website="https://example.com",
                industry="Software",
                support_name="AgentDesk Support",
            ),
        )

        assert created.name == "AgentDesk Demo"

        updated = CompanyService.update(
            db,
            CompanyUpdate(
                name="AgentDesk Inc.",
                website="https://example.com",
                industry="Technology",
                support_name="Support Team",
            ),
        )

        assert updated.id == created.id
        assert updated.name == "AgentDesk Inc."