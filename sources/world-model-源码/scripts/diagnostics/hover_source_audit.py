#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

SUMMARIZED_CHAIN = (
    "gazebo_model_odometry",
    "slam_odom_corrected",
    "external_nav_odom_candidate",
    "external_nav_odom",
    "fcu_local_position_pose",
)

EXPECTED_TOPICS = {
    "gazebo_model_states": "/gazebo/model_states",
    "gazebo_link_states": "/gazebo/link_states",
    "gazebo_model_odometry": "/gazebo/model/odometry",
    "scan_reference_drift_odom": "/navlab/scan_reference_drift/odom",
    "scan_reference_drift_status": "/navlab/scan_reference_drift/status",
    "slam_odom": "/slam/odom",
    "slam_odom_corrected": "/slam/odom_corrected",
    "external_nav_odom_candidate": "/external_nav/odom_candidate",
    "external_nav_odom": "/external_nav/odom",
    "fcu_local_position_pose": "/navlab/fcu/local_position_pose",
    "fcu_filtered_pose": "/ap/v1/pose/filtered",
    "mavlink_external_nav_status": "/mavlink_external_nav/status",
}


def _as_map(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _fmt(value: Any, digits: int = 3) -> str:
    number = _as_float(value)
    if number is None:
        if value is None:
            return ""
        return str(value)
    return f"{number:.{digits}f}"


def _magnitude(x: Any, y: Any) -> float | None:
    x_f = _as_float(x)
    y_f = _as_float(y)
    if x_f is None or y_f is None:
        return None
    return math.hypot(x_f, y_f)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _topic_counts_from_metadata(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    topics: dict[str, dict[str, Any]] = {}
    current_name: str | None = None
    current_type: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("name: "):
            current_name = stripped.removeprefix("name: ").strip()
            current_type = None
        elif stripped.startswith("type: ") and current_name:
            current_type = stripped.removeprefix("type: ").strip()
        elif stripped.startswith("message_count: ") and current_name:
            raw = stripped.removeprefix("message_count: ").strip()
            if re.fullmatch(r"\d+", raw):
                topics[current_name] = {"message_count": int(raw), "type": current_type or ""}
                current_name = None
                current_type = None
    return topics


def _metrics(summary: dict[str, Any]) -> dict[str, Any]:
    return _as_map(_as_map(summary.get("metrics")).get("gate"))


def _source_row(key: str, source: dict[str, Any], *, role: str, trust_status: str, note: str = "") -> dict[str, Any]:
    final_x = source.get("final_x_m")
    final_y = source.get("final_y_m")
    comparison_x = source.get("comparison_final_x_m", final_x)
    comparison_y = source.get("comparison_final_y_m", final_y)
    return {
        "key": key,
        "topic": source.get("source_topic", ""),
        "role": role,
        "trust_status": trust_status,
        "frame_id": source.get("frame_id", ""),
        "child_frame_id": source.get("child_frame_id", ""),
        "comparison_frame": source.get("comparison_frame", source.get("frame_id", "")),
        "sample_count": source.get("sample_count", 0),
        "raw_sample_count": source.get("raw_sample_count", 0),
        "window_source": source.get("window_source", ""),
        "window_start_sec": source.get("window_start_sec"),
        "window_end_sec": source.get("window_end_sec"),
        "window_duration_sec": source.get("window_duration_sec"),
        "final_x_m": final_x,
        "final_y_m": final_y,
        "final_magnitude_m": _magnitude(final_x, final_y),
        "comparison_final_x_m": comparison_x,
        "comparison_final_y_m": comparison_y,
        "comparison_magnitude_m": _magnitude(comparison_x, comparison_y),
        "max_horizontal_drift_m": source.get("max_horizontal_drift_m"),
        "x_span_m": source.get("x_span_m"),
        "y_span_m": source.get("y_span_m"),
        "z_span_m": source.get("z_span_m"),
        "note": note,
    }


def _pair_key(
    left: str,
    right: str,
    pairwise: dict[str, Any],
) -> tuple[str, dict[str, Any]] | tuple[None, dict[str, Any]]:
    direct = f"{left}__{right}"
    reverse = f"{right}__{left}"
    if direct in pairwise:
        return direct, _as_map(pairwise[direct])
    if reverse in pairwise:
        pair = dict(_as_map(pairwise[reverse]))
        left_mag = pair.get("left_magnitude_m")
        right_mag = pair.get("right_magnitude_m")
        pair["left_magnitude_m"] = right_mag
        pair["right_magnitude_m"] = left_mag
        pair["reversed_from"] = reverse
        return reverse, pair
    return None, {}


def _divergence_reason(pair: dict[str, Any]) -> str | None:
    if not pair:
        return "missing_pairwise"
    if pair.get("sample_count_ok") is False:
        return "sample_count_not_ok"
    direction = _as_float(pair.get("direction_cosine"))
    scale = _as_float(pair.get("scale_ratio"))
    if direction is not None and direction < 0.50:
        return "direction_mismatch"
    if scale is not None and scale < 0.50:
        return "scale_mismatch"
    return None


def _first_summarized_divergence(pairwise: dict[str, Any]) -> dict[str, Any]:
    for left, right in zip(SUMMARIZED_CHAIN, SUMMARIZED_CHAIN[1:], strict=True):
        key, pair = _pair_key(left, right, pairwise)
        reason = _divergence_reason(pair)
        if reason:
            return {
                "status": "found",
                "scope": "summarized_sources_only",
                "left": left,
                "right": right,
                "pair_key": key,
                "reason": reason,
                "direction_cosine": pair.get("direction_cosine"),
                "scale_ratio": pair.get("scale_ratio"),
                "left_magnitude_m": pair.get("left_magnitude_m"),
                "right_magnitude_m": pair.get("right_magnitude_m"),
                "note": (
                    "This is the first divergence among sources already summarized by hover_xy_alignment. "
                    "It is not a final root cause until raw /slam/odom, scan-reference, and Gazebo model/link "
                    "origin evidence are audited in the same window."
                ),
            }
    return {
        "status": "not_found",
        "scope": "summarized_sources_only",
        "note": "No direction/scale divergence was found among currently summarized sources.",
    }


def build_audit(artifact_dir: Path) -> dict[str, Any]:
    summary_path = artifact_dir / "summary.json"
    summary = _load_json(summary_path)
    metrics = _metrics(summary)
    alignment = _as_map(metrics.get("hover_xy_alignment"))
    sources = _as_map(alignment.get("sources"))
    pairwise = _as_map(alignment.get("pairwise"))
    topic_counts = _topic_counts_from_metadata(artifact_dir / "rosbag" / "hover_rosbag" / "metadata.yaml")
    raw_audit_path = artifact_dir / "raw_source_audit.json"
    raw_audit = _load_json(raw_audit_path) if raw_audit_path.exists() else {}

    rows: list[dict[str, Any]] = []
    roles = {
        "gazebo_model_odometry": "simulation_world_model_pose_evidence",
        "slam_odom_corrected": "corrected_slam_estimate",
        "external_nav_odom_candidate": "selector_output_candidate",
        "external_nav_odom": "external_nav_bridge_output",
        "fcu_local_position_pose": "fcu_local_position_mirror",
    }
    for key in SUMMARIZED_CHAIN:
        source = _as_map(sources.get(key))
        if source:
            trust_status = "review_only_needs_cross_check" if key == "gazebo_model_odometry" else "estimate_evidence"
            rows.append(_source_row(key, source, role=roles[key], trust_status=trust_status))

    scan_runtime = _as_map(metrics.get("scan_reference_runtime_drift"))
    if scan_runtime:
        scan_source = {
            "source_topic": "/navlab/scan_reference_drift/odom",
            "frame_id": scan_runtime.get("frame_id", "scan_reference"),
            "child_frame_id": scan_runtime.get("child_frame_id", "base_link"),
            "window_source": "hover_status_phase_hover_hold",
            "window_duration_sec": scan_runtime.get("window_duration_sec")
            or _as_map(sources.get("gazebo_model_odometry")).get("window_duration_sec"),
            "sample_count": scan_runtime.get("hover_window_quality_good_count"),
            "raw_sample_count": scan_runtime.get("raw_sample_count"),
            "final_x_m": scan_runtime.get("final_x_m"),
            "final_y_m": scan_runtime.get("final_y_m"),
            "max_horizontal_drift_m": scan_runtime.get("max_horizontal_drift_m"),
        }
        rows.append(
            _source_row(
                "scan_reference_drift_odom",
                scan_source,
                role="range_scan_reference_estimate",
                trust_status="estimate_evidence_not_pairwise_summarized",
                note=(
                    "Final values come from scan_reference_runtime_drift summary; "
                    "not in hover_xy_alignment pairwise table."
                ),
            )
        )

    scan_hover = _as_map(metrics.get("scan_reference_hover_drift"))
    if scan_hover:
        rows.append(
            _source_row(
                "scan_reference_hover_drift_from_scan",
                scan_hover,
                role="derived_scan_range_residual_estimate",
                trust_status="derived_evidence_not_runtime_input",
                note=(
                    "Derived from /scan range residuals; frame/origin must be compared with "
                    "scan_reference_drift_odom before use as truth."
                ),
            )
        )

    availability: dict[str, Any] = {}
    summarized_topics = {row["topic"] for row in rows if row.get("topic")}
    for key, topic in EXPECTED_TOPICS.items():
        metadata = topic_counts.get(topic)
        if topic in summarized_topics:
            status = "summarized"
        elif metadata and metadata.get("message_count", 0) > 0:
            status = "available_in_bag_not_summarized"
        elif metadata:
            status = "topic_present_zero_messages"
        else:
            status = "missing_from_bag_metadata"
        availability[key] = {
            "topic": topic,
            "status": status,
            "message_count": metadata.get("message_count") if metadata else 0,
            "type": metadata.get("type") if metadata else "",
        }

    return {
        "schema": "navlab.hover_source_audit.v1",
        "run_id": summary.get("run_id", artifact_dir.name),
        "artifact_dir": str(artifact_dir),
        "summary_path": str(summary_path),
        "ok": False,
        "diagnostic_only": True,
        "runtime_control_unchanged": True,
        "window": {
            "source": alignment.get("window_source"),
            "start_sec": alignment.get("window_start_sec"),
            "end_sec": alignment.get("window_end_sec"),
            "duration_sec": alignment.get("window_duration_sec"),
        },
        "source_rows": rows,
        "topic_availability": availability,
        "pairwise": pairwise,
        "raw_bag_audit_path": str(raw_audit_path) if raw_audit else "",
        "raw_bag_audit": raw_audit,
        "first_summarized_divergence": _first_summarized_divergence(pairwise),
        "blockers": alignment.get("blockers", []),
        "gazebo_evidence": alignment.get("gazebo_model_odometry_evidence", {}),
        "limitations": [
            "This audit is summary-based and uses evidence already decoded by gate_evaluation.",
            (
                "It does not yet decode raw /gazebo/model_states or /gazebo/link_states; "
                "those topics are absent in the current hover bags."
            ),
            (
                "Raw /slam/odom is included when raw_source_audit.json exists; "
                "/ap/v1/pose/filtered and MAVLink tlog ODOMETRY are still not part of this table."
            ),
            "A first summarized divergence is a reproducible evidence gap, not proof of final root cause.",
        ],
    }


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def render_markdown(audit: dict[str, Any]) -> str:
    source_rows = []
    for row in audit["source_rows"]:
        source_rows.append(
            [
                str(row["key"]),
                str(row["topic"]),
                str(row["frame_id"]),
                str(row["child_frame_id"]),
                str(row["comparison_frame"]),
                str(row["sample_count"]),
                _fmt(row["comparison_final_x_m"]),
                _fmt(row["comparison_final_y_m"]),
                _fmt(row["comparison_magnitude_m"]),
                _fmt(row["max_horizontal_drift_m"]),
                str(row["trust_status"]),
            ]
        )

    availability_rows = []
    for key, item in audit["topic_availability"].items():
        availability_rows.append(
            [
                key,
                str(item["topic"]),
                str(item["status"]),
                str(item["message_count"]),
                str(item["type"]),
            ]
        )

    pair_rows = []
    for key, pair_any in sorted(audit["pairwise"].items()):
        pair = _as_map(pair_any)
        pair_rows.append(
            [
                key,
                _fmt(pair.get("direction_cosine")),
                _fmt(pair.get("scale_ratio")),
                _fmt(pair.get("left_magnitude_m")),
                _fmt(pair.get("right_magnitude_m")),
                str(pair.get("xy_swap_suspicious", "")),
            ]
        )

    raw_audit = _as_map(audit.get("raw_bag_audit"))
    raw_source_rows = []
    for key, source_any in sorted(_as_map(raw_audit.get("sources")).items()):
        source = _as_map(source_any)
        raw_source_rows.append(
            [
                key,
                str(source.get("source_topic", "")),
                str(source.get("frame_id", "")),
                str(source.get("child_frame_id", "")),
                str(source.get("sample_count", "")),
                _fmt(source.get("final_x_m")),
                _fmt(source.get("final_y_m")),
                _fmt(_magnitude(source.get("final_x_m"), source.get("final_y_m"))),
                _fmt(source.get("max_horizontal_drift_m")),
            ]
        )
    raw_pair_rows = []
    for key, pair_any in sorted(_as_map(raw_audit.get("pairwise")).items()):
        pair = _as_map(pair_any)
        raw_pair_rows.append(
            [
                key,
                _fmt(pair.get("direction_cosine")),
                _fmt(pair.get("scale_ratio")),
                _fmt(pair.get("left_magnitude_m")),
                _fmt(pair.get("right_magnitude_m")),
            ]
        )

    divergence = audit["first_summarized_divergence"]
    raw_divergence = _as_map(raw_audit.get("first_raw_chain_divergence"))
    correction_stage = _as_map(raw_audit.get("correction_stage_classification"))
    selector_contract = _as_map(raw_audit.get("selector_contract_classification"))
    lines = [
        f"# Hover Source Audit: {audit['run_id']}",
        "",
        "Diagnostic-only audit. Runtime control input was not changed.",
        "",
        "## Window",
        "",
        f"- source: `{audit['window'].get('source')}`",
        f"- start_sec: `{_fmt(audit['window'].get('start_sec'), 6)}`",
        f"- end_sec: `{_fmt(audit['window'].get('end_sec'), 6)}`",
        f"- duration_sec: `{_fmt(audit['window'].get('duration_sec'), 3)}`",
        "",
        "## Source Table",
        "",
        _markdown_table(
            [
                "key",
                "topic",
                "frame",
                "child",
                "comparison_frame",
                "samples",
                "dx",
                "dy",
                "mag",
                "max_drift",
                "trust",
            ],
            source_rows,
        ),
        "",
        "## Topic Availability",
        "",
        _markdown_table(["key", "topic", "status", "messages", "type"], availability_rows),
        "",
        "## First Summarized Divergence",
        "",
        f"- status: `{divergence.get('status')}`",
        f"- scope: `{divergence.get('scope')}`",
        f"- left: `{divergence.get('left', '')}`",
        f"- right: `{divergence.get('right', '')}`",
        f"- reason: `{divergence.get('reason', '')}`",
        f"- direction_cosine: `{_fmt(divergence.get('direction_cosine'))}`",
        f"- scale_ratio: `{_fmt(divergence.get('scale_ratio'))}`",
        f"- note: {divergence.get('note', '')}",
        "",
        "## Pairwise Summary",
        "",
        _markdown_table(["pair", "cos", "scale", "left_mag", "right_mag", "xy_swap_suspicious"], pair_rows),
        "",
        "## Raw-Bag Chain Audit",
        "",
    ]
    if raw_audit:
        lines.extend(
            [
                f"- raw_audit_path: `{audit.get('raw_bag_audit_path')}`",
                f"- window_source: `{raw_audit.get('window_source')}`",
                f"- window_duration_sec: `{_fmt(raw_audit.get('window_duration_sec'))}`",
                f"- first_raw_chain_divergence: `{raw_divergence.get('status')}` "
                f"`{raw_divergence.get('left', '')}` -> `{raw_divergence.get('right', '')}` "
                f"`{raw_divergence.get('reason', '')}`",
                f"- correction_stage_classification: `{correction_stage.get('status')}`",
                f"- selector_contract_classification: `{selector_contract.get('status')}`",
                "",
                _markdown_table(
                    ["key", "topic", "frame", "child", "samples", "dx", "dy", "mag", "max_drift"],
                    raw_source_rows,
                ),
                "",
                _markdown_table(["pair", "cos", "scale", "left_mag", "right_mag"], raw_pair_rows),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "No `raw_source_audit.json` was found next to this artifact.",
                "",
            ]
        )
    lines.extend(
        [
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in audit["limitations"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a diagnostic-only hover source evidence audit.")
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json-name", default="source_audit.json")
    parser.add_argument("--md-name", default="source_audit.md")
    args = parser.parse_args()

    audit = build_audit(args.artifact_dir)
    output_dir = args.output_dir or args.artifact_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / args.json_name
    md_path = output_dir / args.md_name
    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(audit), encoding="utf-8")
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
