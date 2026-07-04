from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from navlab.common.slam.backends import SlamBackendRegistry
from navlab.common.slam.config import RuntimeConfig


def build_command(*, config_path: str | Path | None = None, backend: str | None = None) -> list[str]:
    config = RuntimeConfig.load(config_path, backend=backend)
    return SlamBackendRegistry.create(config.backend).command(config)


def exec_backend(*, config_path: str | Path | None = None, backend: str | None = None) -> None:
    command = build_command(config_path=config_path, backend=backend)
    print(f"Starting NavLab SLAM backend: {' '.join(shlex.quote(item) for item in command)}", flush=True)
    os.execvp(command[0], command)


def run_backend(*, config_path: str | Path | None = None, backend: str | None = None) -> int:
    command = build_command(config_path=config_path, backend=backend)
    print(f"Running NavLab SLAM backend: {' '.join(shlex.quote(item) for item in command)}", flush=True)
    return subprocess.run(command, check=False).returncode
