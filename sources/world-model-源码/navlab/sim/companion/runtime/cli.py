from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from navlab.common.logging import init_logger, logger
from navlab.sim.companion.runtime.config import DEFAULT_NAVLAB_COMPANION_IMAGE
from navlab.sim.companion.runtime.doctor import write_doctor_summary
from navlab.sim.companion.runtime.launcher import launch_companion

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _default_config_path() -> Path:
    return Path(os.environ.get("NAVLAB_RUNTIME_CONFIG", "/workspace/navlab/config.toml"))


def _default_companion_image() -> str:
    return os.environ.get("NAVLAB_COMPANION_IMAGE", DEFAULT_NAVLAB_COMPANION_IMAGE)


def _env_log_path(default: Path | None = None) -> Path | None:
    raw = os.environ.get("NAVLAB_RUNTIME_LOG")
    if raw:
        return Path(raw)
    return default


@app.command("launch-companion")
def launch_companion_command(
    config: Annotated[
        Path,
        typer.Option("--config", help="NavLab runtime TOML config path"),
    ] = _default_config_path(),
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", help="Runtime log file path"),
    ] = None,
) -> None:
    runtime_log = log_file or _env_log_path(Path("/tmp/navlab_companion.log"))
    init_logger(runtime_log)
    logger.info("Runtime log file: {}", runtime_log)
    raise typer.Exit(launch_companion(config_path=config))


@app.command("doctor")
def doctor_command(
    summary_file: Annotated[
        Path,
        typer.Option("--summary-file", help="Where to write the doctor summary JSON"),
    ],
    image: Annotated[
        str,
        typer.Option("--image", help="Companion image label recorded in the summary"),
    ] = _default_companion_image(),
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", help="Runtime log file path"),
    ] = None,
) -> None:
    runtime_log = log_file or _env_log_path(summary_file.parent / "doctor.log")
    init_logger(runtime_log)
    logger.info("Runtime log file: {}", runtime_log)
    raise typer.Exit(write_doctor_summary(summary_file=summary_file, image=image))


if __name__ == "__main__":
    app()
