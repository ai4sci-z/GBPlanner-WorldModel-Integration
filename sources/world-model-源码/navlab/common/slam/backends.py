from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from navlab.common.slam.config import RuntimeConfig, launch_value


class SlamBackend(ABC):
    BACKEND_NAME: ClassVar[str] = ""

    @abstractmethod
    def command(self, config: RuntimeConfig) -> list[str]:
        raise NotImplementedError


BackendType = type[SlamBackend]


class SlamBackendRegistry:
    _backends: ClassVar[dict[str, BackendType]] = {}

    @classmethod
    def register(cls, backend_cls: BackendType) -> BackendType:
        if not issubclass(backend_cls, SlamBackend):
            raise TypeError(f"registered backend must inherit SlamBackend, got {backend_cls.__name__}")
        backend_name = backend_cls.BACKEND_NAME
        if not backend_name:
            raise ValueError(f"{backend_cls.__name__} must define BACKEND_NAME")
        normalized = cls._normalize_name(backend_name)
        if normalized in cls._backends:
            raise ValueError(f"SLAM backend '{backend_name}' is already registered")
        cls._backends[normalized] = backend_cls
        return backend_cls

    @classmethod
    def create(cls, name: str) -> SlamBackend:
        normalized = cls._normalize_name(name)
        try:
            backend_cls = cls._backends[normalized]
        except KeyError as exc:
            available = ", ".join(cls.names()) or "<none>"
            raise ValueError(f"Unknown SLAM backend '{name}'. Available backends: {available}") from exc
        return backend_cls()

    @classmethod
    def names(cls) -> tuple[str, ...]:
        return tuple(sorted(cls._backends))

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("backend name cannot be empty")
        return normalized


@SlamBackendRegistry.register
@dataclass(frozen=True, slots=True)
class CartographerBackend(SlamBackend):
    BACKEND_NAME: ClassVar[str] = "cartographer"

    def command(self, config: RuntimeConfig) -> list[str]:
        launch_args = [f"{key}:={launch_value(value)}" for key, value in config.launch_argument_map().items()]
        return [
            "ros2",
            "launch",
            config.launch_package,
            config.launch_file,
            *launch_args,
        ]
