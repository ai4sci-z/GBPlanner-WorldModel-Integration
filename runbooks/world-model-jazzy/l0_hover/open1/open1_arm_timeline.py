#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1 · 离线 arm 时间线派生(HEARTBEAT / COMMAND_LONG / COMMAND_ACK)。

复用 open1_tlog 的冻结帧机器(_try_header/x25_crc/双模式重同步),不改写其 decode。
新增 msgid 注册(crc_extra):
  HEARTBEAT=0→50, COMMAND_LONG=76→152, COMMAND_ACK=77→143
crc_extra 的独立验证 = 真实 tlog 自证(全量真帧 bad_crc=0)+ 判别性反证
(故意错 crc_extra 必致真帧 CRC 失败)——见 test_open1_arm_timeline.py G2。
命令常量的独立源 = 真实 run mission_summary(command:400/result:0 且 arm_ack_ok=True)。

时间纪律:tlog 记录前缀 8 字节 usec 时戳;仅在正常模式(记录边界可信)取时戳;
恢复模式锚定的帧 → t_unix="UNKNOWN"(不按文件顺序伪造精确因果时序)。
"""
import json
import os
import struct

import open1_tlog as T
import telemetry_sidecar as S

SCHEMA_VERSION = "wp304.arm_timeline.v1"

HEARTBEAT_MSGID = 0
COMMAND_LONG_MSGID = 76
COMMAND_ACK_MSGID = 77

# crc_extra 注册(验证方法见模块头;不与 open1_tlog.CRC_EXTRA 混表,互不改写)
ARM_CRC_EXTRA = {
    HEARTBEAT_MSGID: 50,
    COMMAND_LONG_MSGID: 152,
    COMMAND_ACK_MSGID: 143,
    T.STATUSTEXT_MSGID: 83,   # 与冻结解码器同值,复用其 STATUSTEXT 语义
}

MAV_CMD_COMPONENT_ARM_DISARM = 400   # 真实 mission_summary 实证(sent arm→ack command=400)
MAV_RESULT_ACCEPTED = 0              # 真实 mission_summary 实证(result:0 ∧ arm_ack_ok)

UNKNOWN = "UNKNOWN"


def _pad(payload, size):
    """MAVLink v2 零截断:载荷尾部零被截,解析前补齐。"""
    if len(payload) < size:
        return payload + b"\x00" * (size - len(payload))
    return payload[:size]


def parse_heartbeat(payload):
    p = _pad(payload, 9)
    custom_mode, = struct.unpack_from("<I", p, 0)
    return {"custom_mode": custom_mode, "type": p[4], "autopilot": p[5],
            "base_mode": p[6], "system_status": p[7], "mavlink_version": p[8]}


def parse_command_long(payload):
    p = _pad(payload, 33)
    params = struct.unpack_from("<7f", p, 0)
    command, = struct.unpack_from("<H", p, 28)
    return {"params": [round(x, 6) for x in params], "command": command,
            "target_system": p[30], "target_component": p[31], "confirmation": p[32]}


def parse_command_ack(payload):
    p = _pad(payload, 10)
    command, = struct.unpack_from("<H", p, 0)
    result = p[2]
    return {"command": command, "result": result}


_PARSERS = {
    HEARTBEAT_MSGID: parse_heartbeat,
    COMMAND_LONG_MSGID: parse_command_long,
    COMMAND_ACK_MSGID: parse_command_ack,
}


def _classify(msgid, fields, statustext=None):
    if msgid == COMMAND_LONG_MSGID and fields["command"] == MAV_CMD_COMPONENT_ARM_DISARM:
        return "arm_request" if fields["params"][0] == 1.0 else "disarm_request"
    if msgid == COMMAND_ACK_MSGID and fields["command"] == MAV_CMD_COMPONENT_ARM_DISARM:
        if fields["result"] == MAV_RESULT_ACCEPTED:
            return "arm_ack_accepted"
        return "arm_reject"
    if msgid == HEARTBEAT_MSGID:
        return "heartbeat"
    if msgid == T.STATUSTEXT_MSGID:
        return "statustext_reason"
    return None


def derive(data):
    """解析 tlog 字节/路径 → arm 时间线 + 诚实计数。
    双模式:正常(记录边界可信,取 8B usec 时戳)/恢复(逐字节重同步,
    锚定帧 t_unix=UNKNOWN)。CRC 失败/截断/未注册 msgid 分别计数,不静默吞。"""
    if isinstance(data, str):
        with open(data, "rb") as f:
            data = f.read()
    data = bytes(data)
    n = len(data)
    i = 0
    recovery = False
    events = []
    counters = {"heartbeat_valid": 0, "command_long_valid": 0, "command_ack_valid": 0,
                "statustext_valid": 0, "bad_crc": 0, "truncated": 0,
                "unsupported": 0, "unknown_time_events": 0, "resync_bytes": 0}

    def emit(hdr, pos, reliable):
        msgid = hdr["msgid"]
        parser = _PARSERS.get(msgid)
        if msgid == T.STATUSTEXT_MSGID:
            sev, text, chunked = T._statustext_fields(hdr["payload"])
            if chunked:
                counters["unsupported"] += 1
                return
            fields = {"severity": sev, "text": text}
        elif parser is not None:
            fields = parser(hdr["payload"])
        else:
            return
        kind = _classify(msgid, fields if msgid != T.STATUSTEXT_MSGID else {}, )
        if msgid == T.STATUSTEXT_MSGID:
            kind = "statustext_reason"
        if kind is None:
            return
        key = {HEARTBEAT_MSGID: "heartbeat_valid", COMMAND_LONG_MSGID: "command_long_valid",
               COMMAND_ACK_MSGID: "command_ack_valid", T.STATUSTEXT_MSGID: "statustext_valid"}[msgid]
        counters[key] += 1
        if reliable:
            t = struct.unpack_from(">Q", data, pos)[0] / 1e6
        else:
            t = UNKNOWN
            counters["unknown_time_events"] += 1
        if kind == "heartbeat":
            return  # 心跳只计数,不入事件表(体量控制;时间线只留 arm 链与 statustext)
        events.append({"kind": kind, "t_unix": t,
                       "ts_reliable": bool(reliable), "fields": fields})

    while i < n:
        if n - i < 12:
            counters["truncated"] += (n - i)
            break
        hdr = T._try_header(data, i, n)
        confirmed = (hdr is not None and hdr["fits"]
                     and not (hdr["incompat"] & ~T.KNOWN_INCOMPAT)
                     and hdr["msgid"] in ARM_CRC_EXTRA
                     and T.x25_crc(hdr["body"], ARM_CRC_EXTRA[hdr["msgid"]]) == hdr["crc_in"])
        if recovery:
            if confirmed:
                emit(hdr, i, reliable=False)   # 恢复锚定:时戳不可信 → UNKNOWN
                i += hdr["total"]
                recovery = False
            else:
                counters["resync_bytes"] += 1
                i += 1
            continue
        if hdr is None or not hdr["fits"]:
            if hdr is not None and not hdr["fits"]:
                counters["truncated"] += 1
            recovery = True
            counters["resync_bytes"] += 1
            i += 1
            continue
        if hdr["incompat"] & ~T.KNOWN_INCOMPAT:
            counters["unsupported"] += 1
            i += hdr["total"]
            continue
        if hdr["msgid"] in ARM_CRC_EXTRA:
            if confirmed:
                emit(hdr, i, reliable=True)
                i += hdr["total"]
            else:
                counters["bad_crc"] += 1
                recovery = True
                counters["resync_bytes"] += 1
                i += 1
        else:
            counters["unsupported"] += 1
            i += hdr["total"]
    return {"schema_version": SCHEMA_VERSION, "events": events, "counters": counters}


def write_arm_timeline(run_dir, timeline):
    """原子落盘 telemetry/arm_timeline.json(不覆盖既有证据)。"""
    path = os.path.join(run_dir, "telemetry", "arm_timeline.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    S.atomic_write(path, json.dumps(timeline, ensure_ascii=False, sort_keys=True,
                                    indent=1).encode("utf-8"), run_root=run_dir)
    return path
