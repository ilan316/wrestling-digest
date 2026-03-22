"""
Register (or update) a Windows Task Scheduler job that runs main.py daily.

Usage:
    python setup_scheduler.py              # registers at 07:00 AM
    python setup_scheduler.py 08:30        # registers at 08:30 AM
    python setup_scheduler.py --remove     # removes the task
"""
from __future__ import annotations

import os
import subprocess
import sys

TASK_NAME = "FeedlyDailyDigest"


def _python_exe() -> str:
    # Prefer the Python installation that has the project's dependencies
    candidate = r"C:\Users\ilan\AppData\Local\Programs\Python\Python314\python.exe"
    if os.path.exists(candidate):
        return candidate
    return sys.executable


def _script_path() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))


def _project_dir() -> str:
    return os.path.dirname(_script_path())


def register(run_time: str = "07:00") -> None:
    python = _python_exe()
    script = _script_path()
    working_dir = _project_dir()

    # Build the action command: python main.py
    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", f'"{python}" -X utf8 "{script}"',
        "/sc", "DAILY",
        "/st", run_time,
        "/sd", "01/01/2025",
        "/f",  # overwrite if exists
    ]

    print(f"[scheduler] Registering task '{TASK_NAME}' to run daily at {run_time}")
    print(f"[scheduler] Command: {python} {script}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[scheduler] Success! Task '{TASK_NAME}' created.")
        print(f"[scheduler] Working directory note: Task Scheduler will run from system32.")
        print(f"[scheduler] The .env file must be in: {working_dir}")
    else:
        print(f"[scheduler] Error: {result.stderr.strip() or result.stdout.strip()}")
        sys.exit(1)


def remove() -> None:
    cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
    print(f"[scheduler] Removing task '{TASK_NAME}'...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[scheduler] Task '{TASK_NAME}' removed.")
    else:
        print(f"[scheduler] Error: {result.stderr.strip() or result.stdout.strip()}")


def status() -> None:
    cmd = ["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"Task '{TASK_NAME}' not found.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--remove" in args:
        remove()
    elif "--status" in args:
        status()
    else:
        time_arg = args[0] if args else "07:00"
        register(time_arg)
