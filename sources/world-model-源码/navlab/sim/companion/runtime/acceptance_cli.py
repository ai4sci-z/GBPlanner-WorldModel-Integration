from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from navlab.common.logging import init_logger, logger
from navlab.sim.companion.runtime.acceptance import execute_companion_gazebo_acceptance
from navlab.sim.companion.runtime.config import RuntimeConfig
from navlab.sim.companion.runtime.hover_acceptance import (
    execute_hover_acceptance,
    execute_hover_diagnostic_acceptance,
    execute_hover_slam_diagnostic_acceptance,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _default_config_path() -> Path:
    return Path(os.environ.get("NAVLAB_RUNTIME_CONFIG", "/workspace/navlab/config.toml"))


def _env_log_path(default: Path | None = None) -> Path | None:
    raw = os.environ.get("NAVLAB_RUNTIME_LOG")
    if raw:
        return Path(raw)
    return default


@app.command("execute-acceptance")
def execute_acceptance_command(
    artifact_dir: Annotated[
        Path,
        typer.Option("--artifact-dir", help="Artifact directory shared with the host"),
    ],
    duration_sec: Annotated[
        float,
        typer.Option("--duration-sec", help="Mission duration in seconds"),
    ],
    rosbag_profile: Annotated[
        Path,
        typer.Option("--rosbag-profile", help="Rosbag topic profile path"),
    ],
    companion_image: Annotated[
        str,
        typer.Option("--companion-image", help="Companion image label recorded in summaries"),
    ],
    scan_source: Annotated[
        str,
        typer.Option("--scan-source", help="Accepted scan source label recorded in summaries"),
    ] = "x2_virtual_serial_vendor_driver",
    config: Annotated[
        Path,
        typer.Option("--config", help="NavLab runtime TOML config path"),
    ] = _default_config_path(),
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", help="Runtime log file path"),
    ] = None,
) -> None:
    runtime_log = log_file or _env_log_path(artifact_dir / "runtime.log")
    init_logger(runtime_log)
    logger.info("Runtime log file: {}", runtime_log)
    raise typer.Exit(
        execute_companion_gazebo_acceptance(
            artifact_dir=artifact_dir,
            duration_sec=duration_sec,
            rosbag_profile_path=rosbag_profile,
            companion_image=companion_image,
            scan_source=scan_source,
            config=RuntimeConfig.load(config),
        )
    )


@app.command("execute-hover-acceptance")
def execute_hover_acceptance_command(
    artifact_dir: Annotated[
        Path,
        typer.Option("--artifact-dir", help="Artifact directory shared with the host"),
    ],
    duration_sec: Annotated[
        float,
        typer.Option("--duration-sec", help="Mission duration in seconds"),
    ],
    rosbag_profile: Annotated[
        Path,
        typer.Option("--rosbag-profile", help="Rosbag topic profile path"),
    ],
    companion_image: Annotated[
        str,
        typer.Option("--companion-image", help="Companion image label recorded in summaries"),
    ],
    scan_source: Annotated[
        str,
        typer.Option("--scan-source", help="Accepted scan source label recorded in summaries"),
    ] = "x2_virtual_serial_vendor_driver",
    config: Annotated[
        Path,
        typer.Option("--config", help="NavLab runtime TOML config path"),
    ] = _default_config_path(),
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", help="Runtime log file path"),
    ] = None,
) -> None:
    runtime_log = log_file or _env_log_path(artifact_dir / "runtime.log")
    init_logger(runtime_log)
    logger.info("Runtime log file: {}", runtime_log)
    raise typer.Exit(
        execute_hover_acceptance(
            artifact_dir=artifact_dir,
            duration_sec=duration_sec,
            rosbag_profile_path=rosbag_profile,
            companion_image=companion_image,
            scan_source=scan_source,
            config=RuntimeConfig.load(config),
        )
    )


@app.command("execute-hover-diagnostic-acceptance")
def execute_hover_diagnostic_acceptance_command(
    artifact_dir: Annotated[
        Path,
        typer.Option("--artifact-dir", help="Artifact directory shared with the host"),
    ],
    duration_sec: Annotated[
        float,
        typer.Option("--duration-sec", help="Mission duration in seconds"),
    ],
    rosbag_profile: Annotated[
        Path,
        typer.Option("--rosbag-profile", help="Rosbag topic profile path"),
    ],
    companion_image: Annotated[
        str,
        typer.Option("--companion-image", help="Companion image label recorded in summaries"),
    ],
    scan_source: Annotated[
        str,
        typer.Option("--scan-source", help="Accepted scan source label recorded in summaries"),
    ] = "x2_virtual_serial_vendor_driver",
    config: Annotated[
        Path,
        typer.Option("--config", help="NavLab runtime TOML config path"),
    ] = _default_config_path(),
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", help="Runtime log file path"),
    ] = None,
) -> None:
    runtime_log = log_file or _env_log_path(artifact_dir / "runtime.log")
    init_logger(runtime_log)
    logger.info("Runtime log file: {}", runtime_log)
    raise typer.Exit(
        execute_hover_diagnostic_acceptance(
            artifact_dir=artifact_dir,
            duration_sec=duration_sec,
            rosbag_profile_path=rosbag_profile,
            companion_image=companion_image,
            scan_source=scan_source,
            config=RuntimeConfig.load(config),
        )
    )


@app.command("execute-hover-slam-diagnostic-acceptance")
def execute_hover_slam_diagnostic_acceptance_command(
    artifact_dir: Annotated[
        Path,
        typer.Option("--artifact-dir", help="Artifact directory shared with the host"),
    ],
    duration_sec: Annotated[
        float,
        typer.Option("--duration-sec", help="Mission duration in seconds"),
    ],
    rosbag_profile: Annotated[
        Path,
        typer.Option("--rosbag-profile", help="Rosbag topic profile path"),
    ],
    companion_image: Annotated[
        str,
        typer.Option("--companion-image", help="Companion image label recorded in summaries"),
    ],
    scan_source: Annotated[
        str,
        typer.Option("--scan-source", help="Accepted scan source label recorded in summaries"),
    ] = "x2_virtual_serial_vendor_driver",
    config: Annotated[
        Path,
        typer.Option("--config", help="NavLab runtime TOML config path"),
    ] = _default_config_path(),
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", help="Runtime log file path"),
    ] = None,
) -> None:
    runtime_log = log_file or _env_log_path(artifact_dir / "runtime.log")
    init_logger(runtime_log)
    logger.info("Runtime log file: {}", runtime_log)
    raise typer.Exit(
        execute_hover_slam_diagnostic_acceptance(
            artifact_dir=artifact_dir,
            duration_sec=duration_sec,
            rosbag_profile_path=rosbag_profile,
            companion_image=companion_image,
            scan_source=scan_source,
            config=RuntimeConfig.load(config),
        )
    )


if __name__ == "__main__":
    app()
