from app.db.base import Base
import app.models  # noqa: F401


def test_expected_tables_registered():
    expected_tables = {
        "system_config",
        "company",
        "ai_provider",
        "customer",
        "ticket",
        "message",
        "agent_run",
        "agent_step",
    }

    assert expected_tables.issubset(
        set(Base.metadata.tables.keys())
    )