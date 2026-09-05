import subprocess
import sys
import time
import webbrowser
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"


def start_backend():
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
        ],
        cwd=BACKEND_DIR,
    )


def start_frontend():
    return subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=FRONTEND_DIR,
    )


def stop_process(process):
    if process.poll() is None:
        process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def main():
    backend = None
    frontend = None

    try:
        print("Starting AgentDesk backend...")
        backend = start_backend()

        print("Starting AgentDesk frontend...")
        frontend = start_frontend()

        time.sleep(3)

        print("Opening AgentDesk...")
        webbrowser.open("http://localhost:3000")

        print("\nAgentDesk is running.")
        print("Frontend: http://localhost:3000")
        print("Backend:  http://127.0.0.1:8000")
        print("\nPress Ctrl+C to stop AgentDesk.\n")

        while True:
            if backend.poll() is not None:
                raise RuntimeError("Backend process stopped unexpectedly.")

            if frontend.poll() is not None:
                raise RuntimeError("Frontend process stopped unexpectedly.")

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping AgentDesk...")

    finally:
        if frontend:
            stop_process(frontend)

        if backend:
            stop_process(backend)

        print("AgentDesk stopped.")


if __name__ == "__main__":
    main()