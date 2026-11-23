"""Identify the source revision used for a run."""

import subprocess
from pathlib import Path


def git_commit() -> str:
    """Return the revision and dirty status, or ``unknown`` outside a checkout."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()

    try:
        commit = git("rev-parse", "--short", "HEAD")
        dirty = git("status", "--porcelain")
    except OSError, subprocess.SubprocessError:
        return "unknown"
    return f"{commit} (with uncommitted changes)" if dirty else commit
