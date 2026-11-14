"""Fail-fast local quality gates; run inside the pinned Linux test environment."""

import subprocess
import sys

for command in (
    ["ruff", "check", "."],
    ["ruff", "format", "--check", "."],
    ["mypy"],
    [sys.executable, "-m", "pytest", *sys.argv[1:]],
):
    subprocess.run(command, check=True)
