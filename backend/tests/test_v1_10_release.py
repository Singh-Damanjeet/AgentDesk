from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.main import app


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"


def load_launcher_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "agentdesk_launcher",
        ROOT_DIR / "run.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load run.py for release tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_corpus_has_25_documents_and_all_supported_formats() -> None:
    documents = list((ROOT_DIR / "samples" / "demo-company").iterdir())
    suffixes = {path.suffix.lower() for path in documents if path.is_file()}

    assert len([path for path in documents if path.is_file()]) == 25
    assert {".pdf", ".docx", ".txt", ".md"}.issubset(suffixes)
    assert not any(
        path.name == "prompt-injection.md"
        for path in documents
        if path.is_file()
    )


def test_security_fixtures_are_separate_from_demo_corpus() -> None:
    fixtures = ROOT_DIR / "samples" / "test-fixtures"

    assert (fixtures / "prompt-injection.md").is_file()
    assert (fixtures / "corrupt.pdf").is_file()
    assert (fixtures / "empty.txt").is_file()
    assert not (ROOT_DIR / "samples" / "demo-company" / "empty.txt").exists()


def test_launcher_reports_occupied_backend_port(monkeypatch) -> None:
    launcher = load_launcher_module()
    monkeypatch.setattr(launcher, "is_port_available", lambda host, port: False)

    try:
        launcher.ensure_ports_available()
    except launcher.StartupError as exc:
        message = str(exc)
    else:
        raise AssertionError("Occupied port should stop launcher startup")

    assert "Port 8000 is already in use" in message
    assert "does not silently switch" in message


def test_launcher_reports_occupied_frontend_port(monkeypatch) -> None:
    launcher = load_launcher_module()
    monkeypatch.setattr(
        launcher,
        "is_port_available",
        lambda host, port: port != launcher.FRONTEND_PORT,
    )

    try:
        launcher.ensure_ports_available()
    except launcher.StartupError as exc:
        message = str(exc)
    else:
        raise AssertionError("Occupied port should stop launcher startup")

    assert "Port 3000 is already in use" in message
    assert "does not silently switch" in message


def test_launcher_frontend_command_keeps_port_3000(monkeypatch) -> None:
    launcher = load_launcher_module()
    calls: list[list[str]] = []

    class FakeProcess:
        def __init__(self):
            self.pid = 1

    def fake_popen(command, **kwargs):
        del kwargs
        calls.append(command)
        return FakeProcess()

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    launcher.start_frontend("npm")

    assert calls == [
        [
            "npm",
            "run",
            "dev",
            "--",
            "--hostname",
            "127.0.0.1",
            "--port",
            "3000",
        ]
    ]


def test_admin_cors_is_explicit_and_rejects_unlisted_methods() -> None:
    with TestClient(app) as client:
        allowed = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        denied = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "PATCH",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == (
        "http://localhost:3000"
    )
    assert allowed.headers["access-control-allow-methods"] == (
        "GET, POST, PUT, DELETE, OPTIONS"
    )
    assert "*" not in allowed.headers["access-control-allow-headers"]
    assert denied.status_code == 400


def test_empty_database_migrates_to_one_release_head(tmp_path) -> None:
    data_dir = tmp_path / "data"
    environment = os.environ.copy()
    environment["AGENTDESK_DATA_DIR"] = str(data_dir)
    environment["PYTHONPATH"] = str(BACKEND_DIR)

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    database_path = data_dir / "agentdesk.db"
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        table_names = set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            versions = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars().all()
    finally:
        engine.dispose()

    assert "alembic_version" in table_names
    assert {"company", "ai_provider", "knowledge_document"}.issubset(
        table_names
    )
    assert versions == ["b1c2d3e4f5a6"]
