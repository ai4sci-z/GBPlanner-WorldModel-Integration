from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

MAX_MOTOR_DEBUG_SEC = 5.0
MAX_MOTOR_DEBUG_COUNT = 8
REQUIRED_GUIDED_MODE_NAME = "GUIDED"
ARDUCOPTER_GUIDED_MODE_ID = 4
TASK_RESULT_SCHEMA_VERSION = "navlab.runtime.task_result.v1"


def build_motor_debug_plan(
    *,
    motor_percent: float,
    motor_sec: float,
    motor_count: int,
) -> dict[str, Any]:
    blockers = _validate_motor_debug_limits(
        motor_percent=motor_percent,
        motor_sec=motor_sec,
        motor_count=motor_count,
    )
    return {
        "schema_version": TASK_RESULT_SCHEMA_VERSION,
        "ok": not blockers,
        "blocked": bool(blockers),
        "blockers": blockers,
        "task": "motor-debug",
        "claim": "plan_only",
        "no_takeoff": True,
        "requires_no_props": True,
        "guided_mode_required": True,
        "required_mode": REQUIRED_GUIDED_MODE_NAME,
        "spin_mode": "armed_idle",
        "throttle_command_claim": "not_sent",
        "motor_percent": motor_percent,
        "motor_sec": motor_sec,
        "motor_count": motor_count,
        "steps": [
            {"step": "arm", "claim": "start_all_motors_at_fcu_armed_idle"},
            {"step": "hold", "duration_sec": motor_sec},
            {"step": "disarm", "claim": "stop_all_motors"},
        ],
        "shutdown": "send_disarm_after_idle_spin",
        "landing_claim": "not_evaluated_no_takeoff",
    }


def run_motor_debug_sequence(
    *,
    serial: str,
    baud: int | float,
    endpoint: str,
    motor_percent: float,
    motor_sec: float,
    motor_count: int,
    process_logger: Any | None = None,
) -> dict[str, Any]:
    plan = build_motor_debug_plan(motor_percent=motor_percent, motor_sec=motor_sec, motor_count=motor_count)
    summary: dict[str, Any] = {
        **plan,
        "claim": "evaluated",
        "serial": serial,
        "connection_endpoint": endpoint,
        "baud": baud,
        "arm_claim": "not_requested",
        "takeoff_claim": "not_evaluated",
        "landing_claim": "not_evaluated_no_takeoff",
        "guided_mode_claim": "not_evaluated",
        "shutdown_claim": "not_evaluated",
        "guided_mode": {},
        "acks": [],
    }
    if plan["blocked"]:
        if process_logger is not None:
            process_logger.warning("Motor-debug plan blocked before MAVLink connection: {}", plan["blockers"])
        return summary
    try:
        from pymavlink import mavutil
        from pymavlink.dialects.v20 import ardupilotmega as mavlink
    except ImportError as exc:
        summary["blockers"] = ["motor_debug_dependency_missing:pymavlink"]
        summary["blocked"] = True
        summary["ok"] = False
        summary["error"] = str(exc)
        if process_logger is not None:
            process_logger.error("Missing pymavlink dependency: {}", exc)
        return summary

    master = None
    try:
        if process_logger is not None:
            process_logger.info("Opening MAVLink connection: {} @ {}", endpoint, baud)
        master = mavutil.mavlink_connection(endpoint, baud=baud, autoreconnect=False, source_system=255)
        heartbeat = master.wait_heartbeat(timeout=10.0)
        if heartbeat is None:
            summary["blockers"] = ["motor_debug_heartbeat_missing"]
            summary["blocked"] = True
            summary["ok"] = False
            if process_logger is not None:
                process_logger.error("MAVLink heartbeat missing on {} @ {}", serial, baud)
            return summary
        target_system = master.target_system
        target_component = master.target_component
        summary["target_system"] = target_system
        summary["target_component"] = target_component
        if process_logger is not None:
            process_logger.info(
                "MAVLink heartbeat ok: target_system={} target_component={}",
                target_system,
                target_component,
            )
        guided_mode = ensure_guided_mode(master, mode_name=REQUIRED_GUIDED_MODE_NAME, timeout_sec=5.0)
        summary["guided_mode"] = guided_mode
        summary["guided_mode_claim"] = "evaluated"
        if not guided_mode.get("ok"):
            summary["blockers"] = [str(guided_mode.get("blocker", "motor_debug_guided_mode_not_confirmed"))]
            summary["blocked"] = True
            summary["ok"] = False
            if process_logger is not None:
                process_logger.error("GUIDED mode was not confirmed: {}", summary["blockers"])
            return summary
        if process_logger is not None:
            process_logger.info("GUIDED mode confirmed: {}", guided_mode)
        arm_ack = send_arm_disarm(master, target_system, target_component, mavlink, arm=True)
        summary["acks"].append({"action": "arm", **arm_ack})
        summary["arm_claim"] = "arm_command_sent"
        if not arm_ack.get("accepted"):
            summary["blockers"] = command_rejection_blockers(
                prefix="motor_debug_arm_rejected",
                ack=arm_ack,
            )
            summary["blocked"] = True
            summary["ok"] = False
            if process_logger is not None:
                process_logger.error("Motor idle spin arm rejected: {}", arm_ack)
            summary["shutdown_claim"] = "not_evaluated_arm_rejected"
            return summary
        if process_logger is not None:
            process_logger.info("Motor idle spin armed; holding for {} seconds", motor_sec)
        time.sleep(max(motor_sec, 0.0))
        disarm_ack = send_arm_disarm(master, target_system, target_component, mavlink, arm=False)
        summary["acks"].append({"action": "disarm", **disarm_ack})
        summary["shutdown_claim"] = "disarm_command_sent"
        if not disarm_ack.get("accepted"):
            summary["blockers"] = command_rejection_blockers(
                prefix="motor_debug_disarm_rejected",
                ack=disarm_ack,
            )
            summary["blocked"] = True
            summary["ok"] = False
            if process_logger is not None:
                process_logger.error("Motor idle spin disarm rejected: {}", disarm_ack)
            return summary
        if process_logger is not None:
            process_logger.info("Motor idle spin disarmed: {}", disarm_ack)
        summary["ok"] = True
        summary["blocked"] = False
        summary["blockers"] = []
        return summary
    except Exception as exc:  # pragma: no cover - hardware dependent.
        summary["blockers"] = [f"motor_debug_failed:{exc}"]
        summary["blocked"] = True
        summary["ok"] = False
        if process_logger is not None:
            process_logger.exception("Motor-debug arm/hold/disarm flow failed: {}", exc)
        return summary
    finally:
        if master is not None:
            master.close()


def _validate_motor_debug_limits(*, motor_percent: float, motor_sec: float, motor_count: int) -> list[str]:
    blockers: list[str] = []
    if motor_sec <= 0.0 or motor_sec > MAX_MOTOR_DEBUG_SEC:
        blockers.append(f"motor_debug_duration_out_of_range:{motor_sec:g}:max={MAX_MOTOR_DEBUG_SEC:g}")
    if motor_count <= 0 or motor_count > MAX_MOTOR_DEBUG_COUNT:
        blockers.append(f"motor_debug_motor_count_out_of_range:{motor_count}:max={MAX_MOTOR_DEBUG_COUNT}")
    return blockers


def wait_command_ack(master: Any, command: int, *, timeout_sec: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    status_text: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        msg = master.recv_match(
            type=["COMMAND_ACK", "STATUSTEXT"],
            blocking=True,
            timeout=max(deadline - time.monotonic(), 0.0),
        )
        if msg is None:
            break
        if _message_type(msg) == "STATUSTEXT":
            status_text.append(_status_text_summary(msg))
            continue
        if _message_type(msg) != "COMMAND_ACK":
            continue
        if int(getattr(msg, "command", -1)) != int(command):
            continue
        result = int(getattr(msg, "result", -1))
        if result != 0:
            status_text.extend(_drain_status_text(master, timeout_sec=1.0))
        return {
            "command": command,
            "result": result,
            "result_name": _mav_result_name(result),
            "result_param2": getattr(msg, "result_param2", None),
            "accepted": result == 0,
            "status_text": status_text,
        }
    return {
        "command": command,
        "result": None,
        "result_name": "timeout",
        "accepted": False,
        "timeout": True,
        "status_text": status_text,
    }


def send_arm_disarm(
    master: Any,
    target_system: int,
    target_component: int,
    mavlink: Any,
    *,
    arm: bool,
) -> dict[str, Any]:
    master.mav.command_long_send(
        target_system,
        target_component,
        mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        1 if arm else 0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    return wait_command_ack(master, mavlink.MAV_CMD_COMPONENT_ARM_DISARM, timeout_sec=3.0)


def _drain_status_text(master: Any, *, timeout_sec: float) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_sec
    status_text: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        msg = master.recv_match(
            type="STATUSTEXT",
            blocking=True,
            timeout=max(deadline - time.monotonic(), 0.0),
        )
        if msg is None:
            break
        status_text.append(_status_text_summary(msg))
    return status_text


def command_rejection_blockers(*, prefix: str, ack: dict[str, Any]) -> list[str]:
    result_name = str(ack.get("result_name") or ack.get("result") or "unknown")
    blockers = [f"{prefix}:{result_name}"]
    for item in ack.get("status_text", []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if text:
            blockers.append(f"{prefix}_status:{text}")
    return blockers


def _message_type(msg: Any) -> str:
    get_type = getattr(msg, "get_type", None)
    if callable(get_type):
        return str(get_type())
    return str(getattr(msg, "_type", ""))


def _status_text_summary(msg: Any) -> dict[str, Any]:
    return {
        "severity": getattr(msg, "severity", None),
        "text": str(getattr(msg, "text", "")).strip().rstrip("\x00"),
    }


def _mav_result_name(result: int | None) -> str:
    names = {
        0: "MAV_RESULT_ACCEPTED",
        1: "MAV_RESULT_TEMPORARILY_REJECTED",
        2: "MAV_RESULT_DENIED",
        3: "MAV_RESULT_UNSUPPORTED",
        4: "MAV_RESULT_FAILED",
        5: "MAV_RESULT_IN_PROGRESS",
        7: "MAV_RESULT_COMMAND_LONG_ONLY",
        8: "MAV_RESULT_COMMAND_INT_ONLY",
    }
    return names.get(result, f"MAV_RESULT_UNKNOWN:{result}")


def ensure_guided_mode(master: Any, *, mode_name: str, timeout_sec: float) -> dict[str, Any]:
    mapping = master.mode_mapping()
    mapped_mode_id = mapping.get(mode_name)
    mode_id = arducopter_mode_id(mode_name, mapped_mode_id=mapped_mode_id)
    result: dict[str, Any] = {
        "ok": False,
        "required_mode": mode_name,
        "mode_id": mode_id,
        "mode_mapping_mode_id": mapped_mode_id,
        "mode_mapping_has_mode": mapped_mode_id is not None,
        "set_mode_sent": False,
        "observed_mode_id": None,
    }
    if mode_id is None:
        result["blocker"] = f"motor_debug_required_mode_missing:{mode_name}"
        return result

    master.set_mode(mode_id)
    result["set_mode_sent"] = True
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        msg = master.recv_match(type="HEARTBEAT", blocking=True, timeout=max(deadline - time.monotonic(), 0.0))
        if msg is None:
            break
        observed = int(getattr(msg, "custom_mode", -1))
        result["observed_mode_id"] = observed
        if observed == int(mode_id):
            result["ok"] = True
            return result
    result["blocker"] = f"motor_debug_required_mode_not_observed:{mode_name}"
    return result


def arducopter_mode_id(mode_name: str, *, mapped_mode_id: int | None) -> int | None:
    normalized = mode_name.strip().upper()
    if normalized == REQUIRED_GUIDED_MODE_NAME:
        return ARDUCOPTER_GUIDED_MODE_ID
    return mapped_mode_id


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run real no-props motor-debug arm/hold/disarm runtime.")
    parser.add_argument("--serial", default="/dev/ttyUSB1")
    parser.add_argument("--baud", type=float, default=115200)
    parser.add_argument("--endpoint", default="udpin:127.0.0.1:14550")
    parser.add_argument("--motor-percent", type=float, default=5.0)
    parser.add_argument("--motor-sec", type=float, default=5.0)
    parser.add_argument("--motor-count", type=int, default=4)
    parser.add_argument("--summary-path", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    summary = run_motor_debug_sequence(
        serial=args.serial,
        baud=args.baud,
        endpoint=args.endpoint,
        motor_percent=args.motor_percent,
        motor_sec=args.motor_sec,
        motor_count=args.motor_count,
    )
    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.summary_path:
        summary_path = Path(args.summary_path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if summary.get("ok") else 20


if __name__ == "__main__":
    raise SystemExit(main())
