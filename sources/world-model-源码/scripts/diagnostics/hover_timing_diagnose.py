#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INPUT_TOPICS = (
    "/scan",
    "/navlab/slam/imu",
    "/cartographer/odometry_input",
)
OUTPUT_TOPICS = (
    "/navlab/slam/tf",
    "/slam/odom",
)
AUX_TOPICS = (
    "/navlab/hover/status",
    "/gazebo/model/odometry",
)
HEADER_ONLY_TOPICS = (
    "/lidar",
    "/imu",
)
ALL_TOPICS = set(INPUT_TOPICS + OUTPUT_TOPICS + AUX_TOPICS + HEADER_ONLY_TOPICS)


@dataclass(frozen=True)
class Sample:
    recv: float
    stamp: float
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


def open_reader(uri: str) -> tuple[Any, dict[str, Any]]:
    try:
        from rosbag2_py import ConverterOptions, SequentialReader, StorageOptions
        from rosidl_runtime_py.utilities import get_message
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "hover_timing_diagnose.py must run in a sourced ROS 2 environment "
            "with rosbag2_py and rosidl_runtime_py available."
        ) from exc

    reader = SequentialReader()
    reader.open(
        StorageOptions(uri=uri, storage_id="mcap"),
        ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"),
    )
    types = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}
    classes = {name: get_message(type_name) for name, type_name in types.items() if name in ALL_TOPICS}
    return reader, classes


def header_stamp(msg: Any) -> float:
    header = getattr(msg, "header", None)
    if header is None:
        return float("nan")
    return float(header.stamp.sec) + float(header.stamp.nanosec) * 1e-9


def transform_stamp(transform: Any) -> float:
    return float(transform.header.stamp.sec) + float(transform.header.stamp.nanosec) * 1e-9


def xy_distance(first: Sample, current: Sample) -> float:
    return math.hypot(current.x - first.x, current.y - first.y)


def parse_bag(uri: str) -> dict[str, Any]:
    try:
        from rclpy.serialization import deserialize_message
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "hover_timing_diagnose.py must run in a sourced ROS 2 environment with rclpy available."
        ) from exc

    reader, classes = open_reader(uri)
    events: list[tuple[float, float, str]] = []
    series: dict[str, list[Sample]] = defaultdict(list)
    hover_events: list[tuple[float, dict[str, Any]]] = []

    while reader.has_next():
        topic, data, recv_ns = reader.read_next()
        if topic not in ALL_TOPICS or topic not in classes:
            continue
        recv = recv_ns * 1e-9
        msg = deserialize_message(data, classes[topic])

        if topic in INPUT_TOPICS:
            stamp = header_stamp(msg)
            events.append((recv, stamp, topic))
            if topic == "/cartographer/odometry_input":
                point = msg.pose.pose.position
                series[topic].append(Sample(recv, stamp, point.x, point.y, point.z))
        elif topic in HEADER_ONLY_TOPICS:
            events.append((recv, header_stamp(msg), topic))
        elif topic in ("/slam/odom", "/gazebo/model/odometry"):
            stamp = header_stamp(msg)
            point = msg.pose.pose.position
            series[topic].append(Sample(recv, stamp, point.x, point.y, point.z))
        elif topic == "/navlab/slam/tf":
            for transform in msg.transforms:
                if transform.header.frame_id == "map" and transform.child_frame_id == "base_link":
                    stamp = transform_stamp(transform)
                    point = transform.transform.translation
                    series[topic].append(Sample(recv, stamp, point.x, point.y, point.z))
        elif topic == "/navlab/hover/status":
            try:
                payload = json.loads(msg.data)
            except Exception:
                payload = {}
            hover_events.append((recv, payload))

    return {"events": events, "series": dict(series), "hover_events": hover_events}


def phase_ranges(hover_events: list[tuple[float, dict[str, Any]]]) -> list[tuple[str, float, float]]:
    ranges: list[tuple[str, float, float]] = []
    current_phase: str | None = None
    start: float | None = None
    previous: float | None = None
    for recv, payload in hover_events:
        phase = payload.get("phase")
        if phase != current_phase:
            if current_phase is not None and start is not None and previous is not None:
                ranges.append((current_phase, start, previous))
            current_phase = phase
            start = recv
        previous = recv
    if current_phase is not None and start is not None and previous is not None:
        ranges.append((current_phase, start, previous))
    return ranges


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def input_timing_stats(events: list[tuple[float, float, str]]) -> dict[str, Any]:
    by_topic: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for recv, stamp, topic in events:
        by_topic[topic].append((recv, stamp))

    topics: dict[str, Any] = {}
    for topic in INPUT_TOPICS + HEADER_ONLY_TOPICS:
        samples = by_topic.get(topic, [])
        if not samples:
            topics[topic] = {"count": 0}
            continue
        recv0, stamp0 = samples[0]
        skews = [(recv - recv0) - (stamp - stamp0) for recv, stamp in samples]
        deltas = [recv - stamp for recv, stamp in samples]
        topics[topic] = {
            "count": len(samples),
            "recv_start": samples[0][0],
            "recv_end": samples[-1][0],
            "stamp_start": samples[0][1],
            "stamp_end": samples[-1][1],
            "recv_span": samples[-1][0] - samples[0][0],
            "stamp_span": samples[-1][1] - samples[0][1],
            "topic_stamp_inversions": sum(1 for idx in range(1, len(samples)) if samples[idx][1] < samples[idx - 1][1]),
            "relative_skew_min": min(skews),
            "relative_skew_median": median(skews),
            "relative_skew_max": max(skews),
            "recv_minus_stamp_min": min(deltas),
            "recv_minus_stamp_median": median(deltas),
            "recv_minus_stamp_max": max(deltas),
        }

    global_inversions = 0
    examples: list[dict[str, Any]] = []
    transitions: Counter[tuple[str, str]] = Counter()
    previous: tuple[float, float, str] | None = None
    collation_topics = set(INPUT_TOPICS)
    for recv, stamp, topic in events:
        if topic not in collation_topics:
            continue
        if previous is not None:
            transitions[(previous[2], topic)] += 1
            if stamp < previous[1]:
                global_inversions += 1
                if len(examples) < 10:
                    examples.append(
                        {
                            "prev_topic": previous[2],
                            "prev_stamp": previous[1],
                            "topic": topic,
                            "stamp": stamp,
                            "stamp_delta": stamp - previous[1],
                            "recv": recv,
                        }
                    )
        previous = (recv, stamp, topic)

    return {
        "topics": topics,
        "global_stamp_inversions_by_receive_order": global_inversions,
        "first_global_inversions": examples,
        "top_receive_transitions": [
            {"from": pair[0], "to": pair[1], "count": count} for pair, count in transitions.most_common(12)
        ],
    }


def select_window(
    samples: list[Sample],
    *,
    stamp_window: tuple[float, float] | None = None,
    recv_window: tuple[float, float] | None = None,
) -> list[Sample]:
    selected = samples
    if stamp_window is not None:
        start, end = stamp_window
        selected = [sample for sample in selected if start <= sample.stamp <= end]
    if recv_window is not None:
        start, end = recv_window
        selected = [sample for sample in selected if start <= sample.recv <= end]
    return selected


def series_stats(
    samples: list[Sample],
    *,
    stamp_window: tuple[float, float] | None = None,
    recv_window: tuple[float, float] | None = None,
) -> dict[str, Any]:
    selected = select_window(samples, stamp_window=stamp_window, recv_window=recv_window)
    if len(selected) < 2:
        return {"count": len(selected)}
    first = selected[0]
    last = selected[-1]
    distances = [xy_distance(first, sample) for sample in selected]
    return {
        "count": len(selected),
        "recv_start": first.recv,
        "recv_end": last.recv,
        "stamp_start": first.stamp,
        "stamp_end": last.stamp,
        "first_xy": [first.x, first.y],
        "last_xy": [last.x, last.y],
        "xy_drift": xy_distance(first, last),
        "xy_max_from_first": max(distances),
    }


def threshold_crossing(samples: list[Sample], threshold: float) -> dict[str, float] | None:
    if not samples:
        return None
    first = samples[0]
    for sample in samples:
        drift = xy_distance(first, sample)
        if drift >= threshold:
            return {"recv": sample.recv, "stamp": sample.stamp, "xy_drift": drift}
    return None


def log_stats(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    log_path = Path(path)
    if not log_path.is_file():
        return {"path": str(log_path), "missing": True}
    text = log_path.read_text(errors="ignore")
    patterns = (
        "Queue waiting for data",
        "Dropped",
        "odom rate:",
        "scan rate:",
        "imu rate:",
        "rejected odom TF",
        "Non-sorted",
        "FATAL",
    )
    rate_lines = [
        line[:320]
        for line in text.splitlines()
        if any(
            token in line
            for token in (
                "odom rate:",
                "scan rate:",
                "imu rate:",
                "rejected odom TF",
                "Non-sorted",
                "FATAL",
                "Queue waiting for data",
            )
        )
    ]
    return {
        "path": str(log_path),
        "counts": {pattern: text.count(pattern) for pattern in patterns},
        "selected_lines": rate_lines[:80],
    }


def analyze_bag(
    uri: str,
    *,
    inherited_stamp_window: tuple[float, float] | None = None,
) -> tuple[dict[str, Any], tuple[float, float] | None]:
    data = parse_bag(uri)
    phases = phase_ranges(data["hover_events"])
    hover_recv_window = None
    for phase, start, end in phases:
        if phase == "hover_hold":
            hover_recv_window = (start, end)
            break

    hover_stamp_window = inherited_stamp_window
    if hover_recv_window is not None:
        odom_samples = select_window(
            data["series"].get("/cartographer/odometry_input", []),
            recv_window=hover_recv_window,
        )
        if len(odom_samples) >= 2:
            hover_stamp_window = (odom_samples[0].stamp, odom_samples[-1].stamp)

    full_series = {topic: series_stats(samples) for topic, samples in data["series"].items()}
    receive_window_series = {}
    if hover_recv_window is not None:
        receive_window_series = {
            topic: series_stats(samples, recv_window=hover_recv_window) for topic, samples in data["series"].items()
        }
    stamp_window_series = {}
    threshold_crossings = {}
    if hover_stamp_window is not None:
        for topic, samples in data["series"].items():
            selected = select_window(samples, stamp_window=hover_stamp_window)
            stamp_window_series[topic] = series_stats(samples, stamp_window=hover_stamp_window)
            threshold_crossings[topic] = {
                str(threshold): threshold_crossing(selected, threshold) for threshold in (0.1, 0.5, 1.0, 5.0)
            }

    result = {
        "uri": uri,
        "input_timing": input_timing_stats(data["events"]),
        "phase_ranges": [
            {"phase": phase, "recv_start": start, "recv_end": end, "duration": end - start}
            for phase, start, end in phases
        ],
        "hover_receive_window": hover_recv_window,
        "hover_input_stamp_window": hover_stamp_window,
        "full_series": full_series,
        "hover_receive_window_series": receive_window_series,
        "hover_input_stamp_window_series": stamp_window_series,
        "threshold_crossings_in_stamp_window": threshold_crossings,
    }
    return result, hover_stamp_window


def format_topic_stats(topic: str, stats: dict[str, Any]) -> str:
    if stats.get("count", 0) < 2:
        return f"{topic}: n={stats.get('count', 0)}"
    return (
        f"{topic}: n={stats['count']} recv={stats['recv_start']:.3f}->{stats['recv_end']:.3f} "
        f"stamp={stats['stamp_start']:.3f}->{stats['stamp_end']:.3f} "
        f"xy={stats['xy_drift']:.4f} max={stats['xy_max_from_first']:.4f}"
    )


def write_text_summary(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    for label in ("live", "replay"):
        if label not in payload:
            continue
        bag = payload[label]
        lines.append(f"===== {label.upper()} =====")
        timing = bag["input_timing"]
        lines.append(f"global_header_inversions={timing['global_stamp_inversions_by_receive_order']}")
        for topic, stats in timing["topics"].items():
            if stats.get("count", 0) == 0:
                lines.append(f"{topic}: missing")
                continue
            lines.append(
                f"{topic}: n={stats['count']} recv_span={stats['recv_span']:.3f}s "
                f"stamp_span={stats['stamp_span']:.3f}s skew_med={stats['relative_skew_median']:.3f}s "
                f"stamp_inv={stats['topic_stamp_inversions']}"
            )
        lines.append(f"hover_receive_window={bag['hover_receive_window']}")
        lines.append(f"hover_input_stamp_window={bag['hover_input_stamp_window']}")
        lines.append("-- receive hover window --")
        for topic in ("/cartographer/odometry_input", "/navlab/slam/tf", "/slam/odom", "/gazebo/model/odometry"):
            lines.append(format_topic_stats(topic, bag["hover_receive_window_series"].get(topic, {"count": 0})))
        lines.append("-- input stamp window --")
        for topic in ("/cartographer/odometry_input", "/navlab/slam/tf", "/slam/odom", "/gazebo/model/odometry"):
            lines.append(format_topic_stats(topic, bag["hover_input_stamp_window_series"].get(topic, {"count": 0})))
        lines.append("")

    for label in ("live_log", "replay_log"):
        if label in payload:
            lines.append(f"===== {label.upper()} =====")
            lines.append(json.dumps(payload[label].get("counts", {}), ensure_ascii=False, sort_keys=True))
            for line in payload[label].get("selected_lines", [])[:20]:
                lines.append(line)
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose hover Cartographer live/replay timing behavior.")
    parser.add_argument("--live-bag", required=True)
    parser.add_argument("--replay-bag")
    parser.add_argument("--live-log")
    parser.add_argument("--replay-log")
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--text-out", required=True)
    args = parser.parse_args()

    payload: dict[str, Any] = {}
    live_result, hover_stamp_window = analyze_bag(args.live_bag)
    payload["live"] = live_result
    if args.replay_bag:
        replay_result, _ = analyze_bag(args.replay_bag, inherited_stamp_window=hover_stamp_window)
        payload["replay"] = replay_result
    payload["live_log"] = log_stats(args.live_log)
    payload["replay_log"] = log_stats(args.replay_log)

    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    write_text_summary(Path(args.text_out), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
