from __future__ import annotations

import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from src import mavlink_serial, maze, ros_setup
from src.command_logging import configure_command_logging

app = typer.Typer(add_completion=False, help="Unified command entrypoint for serial, maze, and ROS tools.")
serial_app = typer.Typer(add_completion=False, help="Serial bridge commands.")
maze_app = typer.Typer(add_completion=False, help="Official maze utility commands.")
ros_app = typer.Typer(add_completion=False, help="Real YDLidar ROS setup doctor and installer.")
console = Console()
error_console = Console(stderr=True)
REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "scripts/command"
DEFAULT_SERIAL_LOG_DIR = COMMAND_ROOT / "logs/serial"
SERIAL_TMUX_SESSION_NAME = "command-serial-bridge"


def _timestamped_log_path(log_file: Path | None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if log_file is None:
        DEFAULT_SERIAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
        return DEFAULT_SERIAL_LOG_DIR / f"{timestamp}.log"

    resolved = log_file.expanduser()
    if resolved.exists() and resolved.is_dir():
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved / f"{timestamp}.log"

    if resolved.suffix.lower() != ".log":
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved / f"{timestamp}.log"

    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _detach_serial_bridge(config: mavlink_serial.BridgeConfig) -> None:
    existing = subprocess.run(
        ["tmux", "has-session", "-t", SERIAL_TMUX_SESSION_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if existing.returncode == 0:
        raise RuntimeError(
            f"tmux session {SERIAL_TMUX_SESSION_NAME!r} already exists; attach with "
            f"`tmux attach -t {SERIAL_TMUX_SESSION_NAME}` or close it first"
        )

    command = [
        sys.executable,
        "scripts/command/main.py",
        "serial",
        "bridge",
        "--port-a",
        config.port_a,
        "--baud-a",
        str(config.baud_a),
        "--port-b",
        config.port_b,
        "--baud-b",
        str(config.baud_b),
        "--read-size",
        str(config.read_size),
        "--log-file",
        config.log_file,
        "--log-level",
        config.log_level,
        "--stats-interval",
        str(config.stats_interval),
        "--reconnect-delay",
        str(config.reconnect_delay),
    ]
    tmux_command = [
        "tmux",
        "new-session",
        "-d",
        "-s",
        SERIAL_TMUX_SESSION_NAME,
        f"cd {shlex.quote(str(REPO_ROOT))} && {shlex.join(command)}",
    ]
    subprocess.run(tmux_command, check=True)
    console.print(f"[green]started[/green] tmux session [bold]{SERIAL_TMUX_SESSION_NAME}[/bold]")
    console.print(f"log file: [cyan]{config.log_file}[/cyan]")
    console.print(f"attach: [bold]tmux attach -t {SERIAL_TMUX_SESSION_NAME}[/bold]")
    console.print(f"stop: [bold]tmux kill-session -t {SERIAL_TMUX_SESSION_NAME}[/bold]")


@serial_app.command("bridge")
def serial_bridge_command(
    port_a: Annotated[str, typer.Option("--port-a", help="First serial port")] = "/dev/ttyUSB1",
    baud_a: Annotated[int, typer.Option("--baud-a", help="Baud rate for port A")] = 115200,
    port_b: Annotated[str, typer.Option("--port-b", help="Second serial port")] = "/dev/ttyUSB0",
    baud_b: Annotated[int, typer.Option("--baud-b", help="Baud rate for port B")] = 115200,
    read_size: Annotated[int, typer.Option("--read-size", help="Bytes to read from the serial port at a time")] = 1024,
    log_file: Annotated[
        Path | None,
        typer.Option(
            "--log-file", help="Optional log file path; defaults to scripts/command/logs/serial/<timestamp>.log"
        ),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Logging verbosity", case_sensitive=False),
    ] = "INFO",
    stats_interval: Annotated[float, typer.Option("--stats-interval", help="Seconds between traffic stats logs")] = 5.0,
    reconnect_delay: Annotated[float, typer.Option("--reconnect-delay", help="Seconds to wait before reconnect")] = 2.0,
    detach: Annotated[
        bool, typer.Option("--detach", help="Run in a fixed tmux session named command-serial-bridge")
    ] = False,
) -> None:
    config = mavlink_serial.BridgeConfig(
        port_a=port_a,
        baud_a=baud_a,
        port_b=port_b,
        baud_b=baud_b,
        read_size=read_size,
        log_file=str(_timestamped_log_path(log_file)),
        log_level=log_level.upper(),
        stats_interval=stats_interval,
        reconnect_delay=reconnect_delay,
    )
    if detach:
        try:
            _detach_serial_bridge(config)
        except Exception as exc:  # noqa: BLE001 - CLI should emit concise blockers.
            error_console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(2) from exc
        return

    configure_command_logging(log_file=config.log_file or None, console_level=config.log_level)
    mavlink_serial.run_bridge(config)


@maze_app.command("plot-topdown")
def plot_topdown_command(
    maze_path: Annotated[
        Path, typer.Option("--maze", help="Path to ardupilot_gz_gazebo/worlds/maze.sdf")
    ] = maze.DEFAULT_MAZE,
    output: Annotated[Path, typer.Option("--output", help="Output SVG path")] = maze.DEFAULT_OUTPUT,
) -> None:
    try:
        output_file = maze.render_topdown_svg(maze_path, output)
    except Exception as exc:  # noqa: BLE001 - CLI should emit concise blockers.
        error_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print(str(output_file))


@ros_app.command("doctor")
def ros_doctor_command(
    distro: Annotated[
        str | None,
        typer.Option("--distro", help="ROS distro to check; defaults to ROS_DISTRO, installed /opt/ros, or jazzy."),
    ] = None,
) -> None:
    resolved_distro = ros_setup.resolve_ros_distro(distro)
    checks = ros_setup.run_checks(resolved_distro)
    ros_setup.render_checks(console, resolved_distro, checks)
    if ros_setup.missing_packages(checks):
        raise typer.Exit(1)


@ros_app.command("install")
def ros_install_command(
    distro: Annotated[
        str | None,
        typer.Option("--distro", help="ROS distro to install; defaults to ROS_DISTRO, installed /opt/ros, or jazzy."),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Install without prompting for confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print apt commands without installing.")] = False,
) -> None:
    resolved_distro = ros_setup.resolve_ros_distro(distro)
    checks = ros_setup.run_checks(resolved_distro)
    ros_setup.render_checks(console, resolved_distro, checks)

    missing = ros_setup.missing_packages(checks)
    sdk_missing = ros_setup.sdk_missing(checks)
    if not missing and not sdk_missing:
        console.print("[green]all real YDLidar ROS requirements are installed[/green]")
        return

    if missing:
        console.print(f"[yellow]will install {len(missing)} missing apt packages[/yellow]")
    if sdk_missing:
        console.print("[yellow]will build and install YDLidar-SDK from third_party/YDLidar-SDK[/yellow]")
    if not yes and not dry_run:
        typer.confirm("Continue with install?", abort=True)

    try:
        if missing:
            ros_setup.install_packages(missing, dry_run=dry_run)
        if sdk_missing:
            ros_setup.install_ydlidar_sdk(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 - CLI should emit concise blockers.
        error_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(2) from exc

    if not dry_run:
        followup_checks = ros_setup.run_checks(resolved_distro)
        ros_setup.render_checks(console, resolved_distro, followup_checks)
        if ros_setup.missing_packages(followup_checks):
            raise typer.Exit(1)


app.add_typer(serial_app, name="serial")
app.add_typer(maze_app, name="maze")
app.add_typer(ros_app, name="ros")
