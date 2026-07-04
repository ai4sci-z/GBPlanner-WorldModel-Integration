from __future__ import annotations

import multiprocessing
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from navlab.common.logging import init_logger, logger


@dataclass(slots=True)
class ManagedProcess:
    name: str
    command: tuple[str, ...]
    process: subprocess.Popen[str] | multiprocessing.Process
    log_path: Path | None = None
    stdout: Any = None

    @property
    def pid(self) -> int:
        return int(self.process.pid or -1)

    def poll(self) -> int | None:
        if isinstance(self.process, subprocess.Popen):
            return self.process.poll()
        if self.process.is_alive():
            return None
        return self.process.exitcode

    def terminate(self) -> None:
        if self.poll() is None:
            logger.info("Terminating {} pid={}", self.name, self.pid)
            self.process.terminate()

    def wait_or_kill(self, *, timeout_sec: float) -> None:
        try:
            if self.poll() is not None:
                logger.info("{} exited rc={}", self.name, self.poll())
                return
            if isinstance(self.process, subprocess.Popen):
                try:
                    self.process.wait(timeout=timeout_sec)
                except subprocess.TimeoutExpired:
                    logger.warning("{} did not stop in {}s; killing pid={}", self.name, timeout_sec, self.pid)
                    self.process.kill()
                    self.process.wait(timeout=5)
            else:
                self.process.join(timeout=timeout_sec)
                if self.process.is_alive():
                    logger.warning("{} did not stop in {}s; killing pid={}", self.name, timeout_sec, self.pid)
                    self.process.kill()
                    self.process.join(timeout=5)
            logger.info("{} stopped rc={}", self.name, self.poll())
        finally:
            if self.stdout is not None:
                self.stdout.close()

    def wait(self, *, timeout_sec: float | None = None) -> int | None:
        try:
            if isinstance(self.process, subprocess.Popen):
                self.process.wait(timeout=timeout_sec)
            else:
                self.process.join(timeout=timeout_sec)
            return self.poll()
        finally:
            if self.stdout is not None:
                self.stdout.close()


def _run_function_entrypoint(
    target: Callable[..., int | None],
    args: tuple[Any, ...],
    log_path: Path | None,
) -> None:
    init_logger(log_path)
    logger.info("Function process entrypoint target={}.{}", target.__module__, target.__name__)
    rc = target(*args)
    raise SystemExit(0 if rc is None else int(rc))


class ProcessManager:
    def __init__(self) -> None:
        self._processes: list[ManagedProcess] = []

    @property
    def processes(self) -> tuple[ManagedProcess, ...]:
        return tuple(self._processes)

    def start_subprocess(
        self,
        name: str,
        command: list[str],
        *,
        log_path: Path | None = None,
    ) -> ManagedProcess:
        stdout = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            stdout = log_path.open("a", encoding="utf-8")
        logger.info("Starting {}: {}", name, " ".join(command))
        process = subprocess.Popen(
            command,
            stdout=stdout or None,
            stderr=subprocess.STDOUT if stdout is not None else None,
            text=True,
        )
        managed = ManagedProcess(name=name, command=tuple(command), process=process, log_path=log_path, stdout=stdout)
        self._processes.append(managed)
        logger.info("Started {} pid={}", name, managed.pid)
        return managed

    def start_function(
        self,
        name: str,
        target: Callable[..., int | None],
        *args: Any,
        log_path: Path | None = None,
    ) -> ManagedProcess:
        command = (f"{target.__module__}.{target.__name__}", *[str(arg) for arg in args])
        logger.info("Starting {} function: {}", name, " ".join(command))
        process = multiprocessing.get_context("spawn").Process(
            name=name,
            target=_run_function_entrypoint,
            args=(target, args, log_path),
        )
        process.start()
        managed = ManagedProcess(name=name, command=command, process=process, log_path=log_path)
        self._processes.append(managed)
        logger.info("Started {} pid={}", name, managed.pid)
        return managed

    def stop_all(self, *, timeout_sec: float = 5.0) -> None:
        for managed in reversed(self._processes):
            managed.terminate()
        for managed in reversed(self._processes):
            managed.wait_or_kill(timeout_sec=timeout_sec)
