"""Start the local AgentDesk development runtime.

The launcher intentionally owns only the local development processes. Production
deployments should run the backend and frontend with their normal process
manager. Keeping the checks here explicit makes a clean checkout fail with a
useful message instead of a secondary child-process error.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 3000
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"
STARTUP_TIMEOUT_SECONDS = 30.0


class StartupError(RuntimeError):
    """Raised when the local runtime cannot be started safely."""


def _npm_executable() -> str | None:
    return shutil.which("npm.cmd" if os.name == "nt" else "npm")


def ensure_prerequisites() -> str:
    """Validate tools and installed dependencies before starting children."""
    if sys.version_info < (3, 11):
        version = ".".join(str(value) for value in sys.version_info[:3])
        raise StartupError(
            "Python 3.11 or newer is required. "
            f"The active interpreter is Python {version}."
        )

    if not BACKEND_DIR.is_dir() or not (BACKEND_DIR / "app").is_dir():
        raise StartupError(
            f"Backend source was not found at {BACKEND_DIR}. "
            "Run this command from the AgentDesk repository."
        )

    if not FRONTEND_DIR.is_dir() or not (FRONTEND_DIR / "package.json").is_file():
        raise StartupError(
            f"Frontend source was not found at {FRONTEND_DIR}. "
            "Run this command from the AgentDesk repository."
        )

    if shutil.which(sys.executable) is None and not Path(sys.executable).is_file():
        raise StartupError(
            f"The active Python interpreter could not be found: {sys.executable}"
        )

    if not _module_available("uvicorn"):
        raise StartupError(
            "The backend dependencies are not installed in the active Python "
            "environment. Install them with `python -m pip install -r "
            "backend/requirements.txt`."
        )

    npm = _npm_executable()
    if npm is None:
        raise StartupError(
            "Node.js and npm are required. Install a supported Node.js release "
            "and make sure `npm` is on PATH."
        )

    if not (FRONTEND_DIR / "node_modules").is_dir():
        raise StartupError(
            "Frontend dependencies are not installed. Run `npm install` in "
            "the frontend directory, then run `python run.py` again."
        )

    return npm


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
    except ImportError:
        return False
    return True


def is_port_available(host: str, port: int) -> bool:
    """Return whether the launcher can bind the requested local port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def ensure_ports_available() -> None:
    for label, host, port in (
        ("backend", BACKEND_HOST, BACKEND_PORT),
        ("frontend", FRONTEND_HOST, FRONTEND_PORT),
    ):
        if is_port_available(host, port):
            continue

        raise StartupError(
            f"Port {port} is already in use ({label}). AgentDesk may already "
            "be running. Stop the existing process and try again; the launcher "
            "does not silently switch to another port."
        )


def run_migrations() -> None:
    """Bring a new or existing local database to the checked-in schema head."""
    print("Applying database migrations...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        check=False,
    )
    if result.returncode != 0:
        raise StartupError(
            "Database migration failed. Resolve the migration error above "
            "before starting AgentDesk."
        )


def _process_group_options() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def start_backend() -> subprocess.Popen[Any]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=BACKEND_DIR,
        **_process_group_options(),
    )


def start_frontend(npm: str) -> subprocess.Popen[Any]:
    return subprocess.Popen(
        [
            npm,
            "run",
            "dev",
            "--",
            "--hostname",
            FRONTEND_HOST,
            "--port",
            str(FRONTEND_PORT),
        ],
        cwd=FRONTEND_DIR,
        **_process_group_options(),
    )


def stop_process(process: subprocess.Popen[Any] | None) -> None:
    """Stop a child and its reload/dev-server descendants cleanly."""
    if process is None or process.poll() is not None:
        return

    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait(timeout=5)


def wait_for_http(
    process: subprocess.Popen[Any],
    *,
    url: str,
    label: str,
    timeout_seconds: float = STARTUP_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response yet"

    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise StartupError(
                f"The {label} process exited during startup with code "
                f"{exit_code}. Check the process output above for the cause."
            )

        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if 200 <= response.status < 500:
                    return
                last_error = f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)

        time.sleep(0.25)

    raise StartupError(
        f"The {label} did not become ready at {url} within "
        f"{timeout_seconds:.0f} seconds ({last_error})."
    )


def _report_process_failure(label: str, process: subprocess.Popen[Any]) -> None:
    exit_code = process.poll()
    if exit_code is not None:
        raise StartupError(
            f"The {label} process stopped with exit code {exit_code}. "
            "Review the process output above for the actionable error."
        )


def main() -> int:
    backend: subprocess.Popen[Any] | None = None
    frontend: subprocess.Popen[Any] | None = None

    try:
        npm = ensure_prerequisites()
        ensure_ports_available()
        run_migrations()

        print("Starting AgentDesk backend...")
        backend = start_backend()
        wait_for_http(
            backend,
            url=f"{BACKEND_URL}/api/health",
            label="backend",
        )

        print("Starting AgentDesk frontend...")
        frontend = start_frontend(npm)
        wait_for_http(
            frontend,
            url=FRONTEND_URL,
            label="frontend",
        )

        print("Opening AgentDesk...")
        webbrowser.open(FRONTEND_URL)

        print("\nAgentDesk is running.")
        print(f"Frontend: {FRONTEND_URL}")
        print(f"Backend:  {BACKEND_URL}")
        print("\nPress Ctrl+C to stop AgentDesk.\n")

        while True:
            _report_process_failure("backend", backend)
            _report_process_failure("frontend", frontend)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping AgentDesk...")
        return 0
    except StartupError as exc:
        print(f"\nAgentDesk could not start: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_process(frontend)
        stop_process(backend)
        print("AgentDesk stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
