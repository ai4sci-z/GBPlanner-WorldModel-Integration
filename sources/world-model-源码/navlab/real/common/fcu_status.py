from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FcuStatusField:
    name: str
    aliases: tuple[str, ...]
    mavlink_parameters: tuple[str, ...] = ()


FCU_STATUS_FIELDS: tuple[FcuStatusField, ...] = (
    FcuStatusField("active_source_set", ("active_source_set", "ekf_active_source_set", "source_set", "ekf_source_set")),
    FcuStatusField("configured_external_nav_source_set", ("configured_external_nav_source_set",)),
    FcuStatusField("observed_ekf_source_set", ("observed_ekf_source_set",)),
    FcuStatusField("observed_ekf_source_set_text", ("observed_ekf_source_set_text",)),
    FcuStatusField("gps_type", ("GPS_TYPE", "gps_type"), ("GPS_TYPE",)),
    FcuStatusField("gps1_type", ("GPS1_TYPE", "gps1_type"), ("GPS1_TYPE",)),
    FcuStatusField("viso_type", ("VISO_TYPE", "viso_type"), ("VISO_TYPE",)),
    FcuStatusField("ek3_src1_posxy", ("EK3_SRC1_POSXY",), ("EK3_SRC1_POSXY",)),
    FcuStatusField("ek3_src1_velxy", ("EK3_SRC1_VELXY",), ("EK3_SRC1_VELXY",)),
    FcuStatusField("ek3_src1_velz", ("EK3_SRC1_VELZ",), ("EK3_SRC1_VELZ",)),
    FcuStatusField("ek3_src1_yaw", ("EK3_SRC1_YAW",), ("EK3_SRC1_YAW",)),
    FcuStatusField("ek3_src1_posz", ("EK3_SRC1_POSZ",), ("EK3_SRC1_POSZ",)),
    FcuStatusField("ek3_src2_posxy", ("EK3_SRC2_POSXY",), ("EK3_SRC2_POSXY",)),
    FcuStatusField("ek3_src2_velxy", ("EK3_SRC2_VELXY",), ("EK3_SRC2_VELXY",)),
    FcuStatusField("ek3_src2_velz", ("EK3_SRC2_VELZ",), ("EK3_SRC2_VELZ",)),
    FcuStatusField("ek3_src2_yaw", ("EK3_SRC2_YAW",), ("EK3_SRC2_YAW",)),
    FcuStatusField("ek3_src2_posz", ("EK3_SRC2_POSZ",), ("EK3_SRC2_POSZ",)),
    FcuStatusField(
        "local_position_valid",
        ("local_position_valid", "local_position_ok", "position_valid", "local_position_ready"),
    ),
)

FCU_STATUS_PARAMETER_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys(param for field in FCU_STATUS_FIELDS for param in field.mavlink_parameters)
)

ARDUCOPTER_MODE_NAMES = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    9: "LAND",
    11: "DRIFT",
    13: "SPORT",
    14: "FLIP",
    15: "AUTOTUNE",
    16: "POSHOLD",
    17: "BRAKE",
    18: "THROW",
    19: "AVOID_ADSB",
    20: "GUIDED_NOGPS",
    21: "SMART_RTL",
    22: "FLOWHOLD",
    23: "FOLLOW",
    24: "ZIGZAG",
    25: "SYSTEMID",
    26: "AUTOROTATE",
    27: "AUTO_RTL",
}


def arducopter_mode_name(mode_number: int | None) -> str:
    if mode_number is None:
        return "unknown"
    return ARDUCOPTER_MODE_NAMES.get(mode_number, f"mode:{mode_number}")


def infer_external_nav_source_set(parameters: Mapping[str, Any]) -> str:
    if _source_set_uses_external_nav(parameters, prefix="EK3_SRC1"):
        return "SRC1"
    if _source_set_uses_external_nav(parameters, prefix="EK3_SRC2"):
        return "SRC2"
    return "unknown"


def source_set_id(source_set: str) -> int | None:
    normalized = source_set.strip().upper()
    if normalized.startswith("SRC"):
        normalized = normalized[3:]
    try:
        value = int(normalized)
    except ValueError:
        return None
    return value if value in {1, 2, 3} else None


def _source_set_uses_external_nav(parameters: Mapping[str, Any], *, prefix: str) -> bool:
    posxy = _int_param(parameters.get(f"{prefix}_POSXY"))
    velxy = _int_param(parameters.get(f"{prefix}_VELXY"))
    yaw = _int_param(parameters.get(f"{prefix}_YAW"))
    return posxy == 6 and velxy == 6 and yaw == 6


def source_set_uses_gps(parameters: Mapping[str, Any], *, prefix: str) -> bool:
    return any(_int_param(_param_value(parameters, f"{prefix}_{field}")) == 3 for field in ("POSXY", "VELXY", "VELZ"))


def _param_value(parameters: Mapping[str, Any], name: str) -> Any:
    value = parameters.get(name)
    if value not in (None, "", [], {}, ()):  # type: ignore[comparison-overlap]
        return value
    nested = parameters.get("parameters")
    if isinstance(nested, Mapping):
        return nested.get(name)
    return None


def _int_param(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
