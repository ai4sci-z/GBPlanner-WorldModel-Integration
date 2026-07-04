from __future__ import annotations

import json
import re
from pathlib import Path


def _load_topic_profile(path: Path) -> tuple[list[str], list[str]]:
    required: list[str] = []
    optional: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or parts[0] not in {"required", "optional"} or not parts[1].startswith("/"):
            raise ValueError(f"{path}:{line_number}: expected '<required|optional> /topic', got {raw_line!r}")
        if parts[0] == "required":
            required.append(parts[1])
        else:
            optional.append(parts[1])
    return required, optional


def _load_metadata_counts(path: Path) -> dict[str, int]:
    metadata = path.read_text(encoding="utf-8")
    counts: dict[str, int] = {}
    topic_matches = list(re.finditer(r"name: (/[^\n]+)", metadata))
    for index, match in enumerate(topic_matches):
        topic = match.group(1).strip()
        end = topic_matches[index + 1].start() if index + 1 < len(topic_matches) else len(metadata)
        block = metadata[match.end() : end]
        count_match = re.search(r"message_count:\s*(\d+)", block)
        counts[topic] = int(count_match.group(1)) if count_match else 0
    return counts


def validate_rosbag_profile(*, profile: Path, metadata: Path, summary_file: Path | None = None) -> dict[str, object]:
    required, optional = _load_topic_profile(profile)
    counts = _load_metadata_counts(metadata)
    missing_required = [topic for topic in required if topic not in counts]
    zero_count_required = [topic for topic in required if counts.get(topic, 0) <= 0]
    present_optional = [topic for topic in optional if counts.get(topic, 0) > 0]
    missing_optional = [topic for topic in optional if topic not in counts]
    summary: dict[str, object] = {
        "ok": not missing_required and not zero_count_required,
        "profile": str(profile),
        "metadata": str(metadata),
        "required_topics": required,
        "optional_topics": optional,
        "present_topics": sorted(counts),
        "message_counts": counts,
        "missing_required_topics": missing_required,
        "zero_count_required_topics": zero_count_required,
        "present_optional_topics": present_optional,
        "missing_optional_topics": missing_optional,
    }
    if summary_file is not None:
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary
