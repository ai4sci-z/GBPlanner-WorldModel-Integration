from __future__ import annotations

import argparse
from pathlib import Path

from navlab.common.slam.backends import SlamBackendRegistry
from navlab.common.slam.runtime import build_command, exec_backend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NavLab SLAM runtime wrapper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch_parser = subparsers.add_parser("launch", help="Exec the selected SLAM backend.")
    launch_parser.add_argument("--config", type=Path, default=None)
    launch_parser.add_argument("--backend", choices=SlamBackendRegistry.names(), default=None)

    print_parser = subparsers.add_parser("print-command", help="Print the backend launch command.")
    print_parser.add_argument("--config", type=Path, default=None)
    print_parser.add_argument("--backend", choices=SlamBackendRegistry.names(), default=None)

    args = parser.parse_args(argv)
    if args.command == "print-command":
        print(" ".join(build_command(config_path=args.config, backend=args.backend)))
        return 0
    if args.command == "launch":
        exec_backend(config_path=args.config, backend=args.backend)
        return 0
    raise RuntimeError(f"unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
