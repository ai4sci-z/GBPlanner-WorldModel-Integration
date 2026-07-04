from __future__ import annotations

import subprocess
from pathlib import Path

from navlab.common import rosbag
from navlab.common.rosbag import RosbagOptions, load_rosbag_topics, parse_rosbag_topic_line, with_rosbag_recording


def test_load_rosbag_topics_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    topic_file = tmp_path / "topics.txt"
    topic_file.write_text("# comment\n\n/scan\n /tf \n", encoding="utf-8")
    assert load_rosbag_topics(topic_file) == ["/scan", "/tf"]


def test_load_rosbag_topics_accepts_required_optional_profile_lines(tmp_path: Path) -> None:
    topic_file = tmp_path / "topics.txt"
    topic_file.write_text("required /scan\noptional /ap/tf\n", encoding="utf-8")
    assert load_rosbag_topics(topic_file) == ["/scan", "/ap/tf"]


def test_parse_rosbag_topic_line_rejects_malformed_profile_line() -> None:
    try:
        parse_rosbag_topic_line("required")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_load_rosbag_topics_requires_existing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    try:
        load_rosbag_topics(missing)
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")


def test_decorator_executes_function_without_recording() -> None:
    calls: list[str] = []

    @with_rosbag_recording
    def sample(value: str) -> str:
        calls.append(value)
        return value.upper()

    result = sample("ok", rosbag_options=RosbagOptions(enabled=False))
    assert result == "OK"
    assert calls == ["ok"]


def test_recorder_sends_sigint_to_process_group(monkeypatch, tmp_path: Path) -> None:
    topic_file = tmp_path / "topics.txt"
    topic_file.write_text("/scan\n", encoding="utf-8")
    signals: list[tuple[int, int]] = []
    waited: list[int] = []

    class _FakeProcess:
        pid = 4242

        def wait(self, timeout: float) -> None:
            waited.append(int(timeout))

    def fake_popen(command: list[str], start_new_session: bool) -> _FakeProcess:
        assert command[:4] == ["ros2", "bag", "record", "-o"]
        assert "/test/demo/" in command[4]
        assert command[4].endswith("/rosbag")
        assert start_new_session is True
        return _FakeProcess()

    monkeypatch.setattr(rosbag.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(rosbag.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(rosbag.os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    with rosbag.RosbagRecorder(
        RosbagOptions(
            enabled=True,
            label="demo",
            session_id="test",
            topic_file=topic_file,
            output_root=tmp_path,
        )
    ):
        pass

    assert signals == [(4242, rosbag.signal.SIGINT)]
    assert waited == [15]


def test_recorder_kills_process_group_after_timeout(monkeypatch, tmp_path: Path) -> None:
    topic_file = tmp_path / "topics.txt"
    topic_file.write_text("/scan\n", encoding="utf-8")
    signals: list[tuple[int, int]] = []
    waits: list[int] = []

    class _FakeProcess:
        pid = 5151

        def wait(self, timeout: float) -> None:
            waits.append(int(timeout))
            if len(waits) == 1:
                raise subprocess.TimeoutExpired(cmd=["ros2", "bag", "record"], timeout=timeout)

    monkeypatch.setattr(rosbag.subprocess, "Popen", lambda *_args, **_kwargs: _FakeProcess())
    monkeypatch.setattr(rosbag.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(rosbag.os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    with rosbag.RosbagRecorder(
        RosbagOptions(
            enabled=True,
            label="demo",
            session_id="test",
            topic_file=topic_file,
            output_root=tmp_path,
        )
    ):
        pass

    assert signals == [
        (5151, rosbag.signal.SIGINT),
        (5151, rosbag.signal.SIGKILL),
    ]
    assert waits == [15, 5]
