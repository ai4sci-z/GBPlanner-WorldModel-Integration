from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

DEFAULT_ROS_DISTRO = "jazzy"
REPO_ROOT = Path(__file__).resolve().parents[3]
YDLIDAR_SDK_SOURCE = REPO_ROOT / "third_party/YDLidar-SDK"
YDLIDAR_SDK_BUILD = Path("/tmp/navlab_ydlidar_sdk-build")

SYSTEM_PACKAGES: tuple[tuple[str, str], ...] = (
    ("build-essential", "build YDLidar-SDK and ydlidar_ros2_driver"),
    ("cmake", "configure and install YDLidar-SDK"),
    ("pkg-config", "native build discovery for SDK dependencies"),
    ("python3-colcon-common-extensions", "build the ydlidar ROS 2 workspace"),
)

ROS_PACKAGE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("ros-{distro}-ros-base", "minimal ROS 2 runtime for real lidar driver"),
    ("ros-{distro}-ament-cmake", "ydlidar_ros2_driver buildtool_depend"),
    ("ros-{distro}-rclcpp", "ydlidar_ros2_driver build/exec_depend"),
    ("ros-{distro}-rmw", "ydlidar_ros2_driver CMake find_package"),
    ("ros-{distro}-sensor-msgs", "ydlidar_ros2_driver LaserScan output"),
    ("ros-{distro}-visualization-msgs", "ydlidar_ros2_driver package.xml"),
    ("ros-{distro}-geometry-msgs", "ydlidar_ros2_driver package.xml"),
    ("ros-{distro}-std-srvs", "third_party/ydlidar_ros2_driver package.xml"),
    ("ros-{distro}-rosbag2-storage-mcap", "record real lidar experiment bags as MCAP"),
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    group: str
    name: str
    installed: bool
    detail: str


def resolve_ros_distro(distro: str | None = None) -> str:
    if distro:
        return distro

    env_distro = os.environ.get("ROS_DISTRO")
    if env_distro:
        return env_distro

    if Path(f"/opt/ros/{DEFAULT_ROS_DISTRO}").exists():
        return DEFAULT_ROS_DISTRO

    opt_ros = Path("/opt/ros")
    if opt_ros.exists():
        distros = sorted(path.name for path in opt_ros.iterdir() if path.is_dir())
        if distros:
            return distros[-1]

    return DEFAULT_ROS_DISTRO


def ros_packages(distro: str) -> tuple[str, ...]:
    return tuple(template.format(distro=distro) for template, _detail in ROS_PACKAGE_TEMPLATES)


def target_packages(distro: str) -> tuple[str, ...]:
    return (*(package for package, _detail in SYSTEM_PACKAGES), *ros_packages(distro))


def package_installed(package: str) -> bool:
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${Status}", package],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "install ok installed"


def check_packages(distro: str) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for package, detail in SYSTEM_PACKAGES:
        checks.append(
            CheckResult(
                group="system",
                name=package,
                installed=package_installed(package),
                detail=detail,
            )
        )

    for template, detail in ROS_PACKAGE_TEMPLATES:
        package = template.format(distro=distro)
        checks.append(
            CheckResult(
                group="ros",
                name=package,
                installed=package_installed(package),
                detail=detail,
            )
        )

    return checks


def check_environment(distro: str) -> list[CheckResult]:
    setup_file = Path(f"/opt/ros/{distro}/setup.bash")
    return [
        CheckResult(
            group="env",
            name=str(setup_file),
            installed=setup_file.exists(),
            detail="source this before running ROS commands",
        ),
        CheckResult(
            group="env",
            name="ros2",
            installed=shutil.which("ros2") is not None,
            detail="available in PATH after sourcing setup.bash",
        ),
        CheckResult(
            group="env",
            name="colcon",
            installed=shutil.which("colcon") is not None,
            detail="workspace build command",
        ),
    ]


def check_ydlidar_sdk() -> list[CheckResult]:
    source_ready = (YDLIDAR_SDK_SOURCE / "CMakeLists.txt").exists()
    cmake_ready = (
        Path("/usr/local/lib/cmake/ydlidar_sdk/ydlidar_sdkConfig.cmake").exists()
        and Path("/usr/local/lib/libydlidar_sdk.a").exists()
    )
    return [
        CheckResult(
            group="sdk",
            name="third_party/YDLidar-SDK",
            installed=source_ready,
            detail="local SDK source used by installer",
        ),
        CheckResult(
            group="sdk",
            name="ydlidar_sdk",
            installed=cmake_ready,
            detail="CMake package required by ydlidar_ros2_driver",
        ),
    ]


def run_checks(distro: str) -> list[CheckResult]:
    return [*check_packages(distro), *check_ydlidar_sdk(), *check_environment(distro)]


def missing_packages(checks: list[CheckResult]) -> list[str]:
    return [check.name for check in checks if check.group in {"system", "ros"} and not check.installed]


def sdk_missing(checks: list[CheckResult]) -> bool:
    return any(check.group == "sdk" and check.name == "ydlidar_sdk" and not check.installed for check in checks)


def render_checks(console: Console, distro: str, checks: list[CheckResult]) -> None:
    packages = [check for check in checks if check.group in {"system", "ros"}]
    installed_count = sum(1 for check in packages if check.installed)
    missing_count = len(packages) - installed_count

    status = "[green]ready[/green]" if missing_count == 0 else f"[yellow]{missing_count} missing[/yellow]"
    console.print(
        Panel(
            f"ROS distro: [bold]{distro}[/bold]\n"
            f"Real YDLidar packages: [bold]{installed_count}/{len(packages)}[/bold] installed\n"
            f"Status: {status}",
            title="YDLidar ROS Doctor",
            border_style="cyan",
        )
    )

    table = Table(show_lines=False)
    table.add_column("Group", style="cyan", no_wrap=True)
    table.add_column("Requirement", overflow="fold")
    table.add_column("Status", no_wrap=True)
    table.add_column("Detail", overflow="fold")

    for check in checks:
        mark = "[green]installed[/green]" if check.installed else "[red]missing[/red]"
        table.add_row(check.group, check.name, mark, check.detail)

    console.print(table)
    if any(check.group == "env" and check.name == "ros2" and not check.installed for check in checks):
        console.print(f"[dim]hint:[/dim] source /opt/ros/{distro}/setup.bash")


def apt_command() -> list[str]:
    if os.geteuid() == 0:
        return ["apt-get"]

    sudo = shutil.which("sudo")
    if sudo:
        return [sudo, "apt-get"]

    raise RuntimeError("apt install needs root privileges or sudo")


def elevated_command(command: str) -> list[str]:
    if os.geteuid() == 0:
        return [command]

    sudo = shutil.which("sudo")
    if sudo:
        return [sudo, command]

    raise RuntimeError(f"{command} needs root privileges or sudo")


def install_packages(packages: list[str], *, dry_run: bool = False) -> None:
    base = apt_command()
    update_cmd = [*base, "-o", "Acquire::Retries=2", "update"]
    install_cmd = [
        *base,
        "-o",
        "Acquire::Retries=2",
        "install",
        "-y",
        "--no-install-recommends",
        *packages,
    ]

    if dry_run:
        typer.echo(" ".join(update_cmd))
        typer.echo(" ".join(install_cmd))
        return

    subprocess.run(update_cmd, check=True)
    subprocess.run(install_cmd, check=True)


def install_ydlidar_sdk(*, dry_run: bool = False) -> None:
    if not (YDLIDAR_SDK_SOURCE / "CMakeLists.txt").exists():
        raise RuntimeError(f"missing YDLidar-SDK source at {YDLIDAR_SDK_SOURCE}")

    configure_cmd = [
        "cmake",
        "-S",
        str(YDLIDAR_SDK_SOURCE),
        "-B",
        str(YDLIDAR_SDK_BUILD),
        "-DCMAKE_INSTALL_PREFIX=/usr/local",
    ]
    build_cmd = ["cmake", "--build", str(YDLIDAR_SDK_BUILD), "-j", str(os.cpu_count() or 1)]
    install_cmd = [*elevated_command("cmake"), "--install", str(YDLIDAR_SDK_BUILD)]
    ldconfig_cmd = elevated_command("ldconfig")

    if dry_run:
        typer.echo(" ".join(configure_cmd))
        typer.echo(" ".join(build_cmd))
        typer.echo(" ".join(install_cmd))
        typer.echo(" ".join(ldconfig_cmd))
        return

    subprocess.run(configure_cmd, check=True)
    subprocess.run(build_cmd, check=True)
    subprocess.run(install_cmd, check=True)
    subprocess.run(ldconfig_cmd, check=True)
