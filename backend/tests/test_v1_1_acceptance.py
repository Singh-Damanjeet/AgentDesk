from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401

from app.core.secrets import decrypt_secret, encrypt_secret
from app.db.base import Base
from app.schemas.company import CompanyUpdate
from app.services.company_service import CompanyService
from app.services.config_service import ConfigService


def test_company_persists_between_sessions(tmp_path):
    database_path = tmp_path / "test_agentdesk.db"

    engine = create_engine(
        f"sqlite:///{database_path}"
    )

    Base.metadata.create_all(engine)

    with Session(engine) as first_session:
        company = CompanyService.update(
            first_session,
            CompanyUpdate(
                name="Persistent Company",
                website="https://example.com",
                industry="Technology",
                support_name="Support",
            ),
        )

        company_id = company.id

    with Session(engine) as second_session:
        company = CompanyService.get(second_session)

        assert company is not None
        assert company.id == company_id
        assert company.name == "Persistent Company"


def test_system_config_persists_between_sessions(tmp_path):
    database_path = tmp_path / "config_test.db"

    engine = create_engine(
        f"sqlite:///{database_path}"
    )

    Base.metadata.create_all(engine)

    with Session(engine) as first_session:
        config = ConfigService.get_status(first_session)

        installation_id = config.installation_id

    with Session(engine) as second_session:
        config = ConfigService.get_status(second_session)

        assert config.installation_id == installation_id


def test_secret_encryption_round_trip():
    secret = "agentdesk-test-secret"

    encrypted = encrypt_secret(secret)

    assert encrypted != secret
    assert secret not in encrypted

    decrypted = decrypt_secret(encrypted)

    assert decrypted == secret