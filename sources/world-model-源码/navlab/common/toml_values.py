from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib


@dataclass(slots=True)
class ValueWithSource:
    value: str
    source: str


@dataclass(slots=True)
class FloatWithSource:
    value: float
    source: str


@dataclass(slots=True)
class BoolWithSource:
    value: bool
    source: str


NAVLAB_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = NAVLAB_PACKAGE_ROOT.parent
DEFAULT_NAVLAB_CONFIG_FILE = NAVLAB_PACKAGE_ROOT / "config.toml"


def repo_root() -> Path:
    return REPO_ROOT


def resolve_navlab_config_file(path: str | Path | None = None) -> Path:
    raw_path = path or os.environ.get("NAVLAB_CONFIG") or DEFAULT_NAVLAB_CONFIG_FILE
    config_file = Path(raw_path)
    if not config_file.is_absolute():
        config_file = repo_root() / config_file
    return config_file


def load_config_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config in {path}")
    return data


def load_navlab_config(path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    config_file = resolve_navlab_config_file(path)
    return config_file, load_config_file(config_file)


def section(data: dict[str, Any], key: str, *, path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    value = data.get(key, default or {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Invalid [{key}] section in {path}")
    return value


def resolve_str_value(section_data: dict[str, Any], key: str, default: str) -> ValueWithSource:
    value = section_data.get(key)
    if value not in (None, ""):
        return ValueWithSource(str(value), "config.toml")
    return ValueWithSource(default, "default")


def resolve_float_value(section_data: dict[str, Any], key: str, default: float) -> FloatWithSource:
    value = section_data.get(key)
    if value not in (None, ""):
        try:
            return FloatWithSource(float(value), "config.toml")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid value for '{key}': expected a number") from exc
    return FloatWithSource(default, "default")


def resolve_bool_value(section_data: dict[str, Any], key: str, default: bool) -> BoolWithSource:
    value = section_data.get(key)
    if value in (None, ""):
        return BoolWithSource(default, "default")
    if isinstance(value, bool):
        return BoolWithSource(value, "config.toml")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return BoolWithSource(True, "config.toml")
        if normalized in ("0", "false", "no", "off"):
            return BoolWithSource(False, "config.toml")
    raise ValueError(f"Invalid value for '{key}': expected a boolean")


def as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def as_args(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(shlex.split(value))
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    raise TypeError(f"expected args list or string, got {type(value).__name__}")


def nested_section(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    value: Any = data
    for key in keys:
        value = value.get(key, {}) if isinstance(value, dict) else {}
    if not isinstance(value, dict):
        return {}
    return value
