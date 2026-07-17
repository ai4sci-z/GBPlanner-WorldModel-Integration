#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0:自包含 MAVLink tlog STATUSTEXT 协议解码器(stdlib only,校验 CRC 传输完整性)。

不用 pymavlink(OPEN-2 栽在该环境债)。手写最小 v1/v2 帧解析。

诚实边界(逐条对应 Codex 现场击穿):
  - CRC 只证**传输完整性**,不证**签名身份**。X25(crc_extra)校验通过 ≠ authenticated。
  - 未知 incompat flag(除 signed 0x01 外任一 bit)→ 保守拒绝,记 unsupported_incompat_flags,
    不计入 valid_crc / valid_statustext / marker。
  - signed 帧(0x01)CRC 正确 → 可解码内容,但必须标 signature_status=UNVERIFIED,
    记 signed_frames_unverified;绝不把"消费 13 字节"当"签名校验通过"。
  - 伪造长度/损坏帧:不因单个候选 header 声称长度超缓冲就放弃后续输入;逐字节重同步,
    继续寻找下一个可读时间戳边界 + magic + 落在缓冲 + 已知消息 CRC 有效的 record。
    仅真正尾部不足一帧时才计 truncated_tail。
  - STATUSTEXT 文本只取固定字段 payload[1:51];v2 扩展 id!=0(分块)→ fail-closed 记 unsupported。
  - 只对已知 crc_extra 的 msgid(此处 STATUSTEXT=253)校验 CRC;其它 msgid 记 unsupported_message_frames。

CRC 算法独立性:x25_crc 是标准 CRC-16/MCRF4XX,公开已知向量 x25(b"123456789")==0x6F91
  (见 test G1 独立向量);crc_extra=83 绑 MAVLink common 方言 STATUSTEXT。
"""
import struct

STATUSTEXT_MSGID = 253
# crc_extra 来源:MAVLink common 方言 STATUSTEXT 消息(消息名+字段签名的 CRC 尾字节)= 83。
CRC_EXTRA = {STATUSTEXT_MSGID: 83}
KNOWN_INCOMPAT = 0x01           # MAVLINK_IFLAG_SIGNED;其余 bit 视为未知,保守拒绝
_STATUSTEXT_FIXED_LEN = 51      # severity(1)+text(50);其后为扩展 id(2)+chunk_seq(1)
_MIN_RECORD = 16               # 8B ts + 最小 v1 帧(6 header + 0 payload + 2 crc)

_STAT_KEYS = (
    "candidate_records", "valid_crc_frames", "crc_failed_frames", "truncated_candidates",
    "unsupported_message_frames", "unsupported_incompat_flags", "signed_frames_unverified",
    "recovered_records", "resync_bytes", "truncated_tail",
    "valid_statustext", "unsupported_chunked_statustext",
    # 兼容旧字段(不用单一 ok 混合;仅镜像便于既有引用)
    "statustext_valid", "statustext_bad_crc",
)


def x25_crc(buf, crc_extra=None):
    """MAVLink X25 = CRC-16/MCRF4XX(init 0xFFFF,poly 0x1021 反射,无 final xor)。
    公开已知向量:x25_crc(b'123456789') == 0x6F91。crc_extra 非 None 时作尾字节喂入。"""
    crc = 0xFFFF
    data = bytes(buf) + (bytes([crc_extra]) if crc_extra is not None else b"")
    for b in data:
        tmp = b ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


def _statustext_fields(payload):
    """返回 (severity, text, chunked)。chunked = v2 扩展 id!=0(不支持重组→上层记 unsupported)。"""
    severity = payload[0]
    text = payload[1:_STATUSTEXT_FIXED_LEN].split(b"\x00")[0].decode("ascii", "replace")
    chunked = False
    if len(payload) >= 53:
        ext_id = payload[51] | (payload[52] << 8)
        if ext_id != 0:
            chunked = True
    return severity, text, chunked


def _try_header(data, i, n):
    """在位置 i 解析 [8B ts][magic frame] 的结构;返回 dict 或 None(magic 不符/头不足)。
    dict 含 total/fits/msgid/payload/crc_in/body/incompat/signed。"""
    if i + 9 > n:
        return None
    magic = data[i + 8]
    if magic == 0xFD:
        if i + 8 + 10 > n:
            return None
        ln = data[i + 9]
        incompat = data[i + 10]
        siglen = 13 if (incompat & 0x01) else 0
        total = 8 + 10 + ln + 2 + siglen
        fits = (i + total <= n)
        d = {"total": total, "fits": fits, "incompat": incompat, "signed": bool(incompat & 0x01)}
        if fits:
            d["msgid"] = data[i + 15] | (data[i + 16] << 8) | (data[i + 17] << 16)
            d["payload"] = data[i + 18: i + 18 + ln]
            d["crc_in"] = data[i + 18 + ln] | (data[i + 18 + ln + 1] << 8)
            d["body"] = data[i + 9: i + 18 + ln]
        return d
    if magic == 0xFE:
        if i + 8 + 6 > n:
            return None
        ln = data[i + 9]
        total = 8 + 6 + ln + 2
        fits = (i + total <= n)
        d = {"total": total, "fits": fits, "incompat": 0, "signed": False}
        if fits:
            d["msgid"] = data[i + 13]
            d["payload"] = data[i + 14: i + 14 + ln]
            d["crc_in"] = data[i + 14 + ln] | (data[i + 14 + ln + 1] << 8)
            d["body"] = data[i + 9: i + 14 + ln]
        return d
    return None


def decode(data):
    """顺序解析,返回 (statustexts, stats)。
    statustexts = [(t_unix, severity, text, signature_status)];仅 CRC 校验通过、
    incompat 合法、非分块的 STATUSTEXT。signature_status ∈ {UNSIGNED, UNVERIFIED}。"""
    if isinstance(data, str):
        with open(data, "rb") as f:
            data = f.read()
    data = bytes(data)
    n = len(data)
    i = 0
    out = []
    stats = {k: 0 for k in _STAT_KEYS}
    # 双模式:normal 信任 len 前进(真实 tlog 准确/快);recovery 逐字节重同步,只认 CRC 确认的
    # STATUSTEXT 再锚定(坏帧/截断帧后不信任 len,避免过冲吞掉后续合法帧)。
    recovery = False

    def _resync():
        nonlocal i
        stats["resync_bytes"] += 1
        i += 1

    def _emit_statustext(hdr, pos):
        sev, text, chunked = _statustext_fields(hdr["payload"])
        if chunked:
            stats["unsupported_chunked_statustext"] += 1
            return
        sig_status = "UNVERIFIED" if hdr["signed"] else "UNSIGNED"
        if hdr["signed"]:
            stats["signed_frames_unverified"] += 1
        stats["valid_statustext"] += 1
        stats["statustext_valid"] += 1  # 兼容镜像
        out.append((struct.unpack_from(">Q", data, pos)[0] / 1e6, sev, text, sig_status))

    while i < n:
        if n - i < _MIN_RECORD:
            stats["truncated_tail"] += (n - i)
            break
        hdr = _try_header(data, i, n)
        confirmed = (hdr is not None and hdr["fits"]
                     and not (hdr["incompat"] & ~KNOWN_INCOMPAT)
                     and hdr["msgid"] in CRC_EXTRA
                     and x25_crc(hdr["body"], CRC_EXTRA[hdr["msgid"]]) == hdr["crc_in"])

        if recovery:
            # 恢复模式:只接受 CRC 确认的 STATUSTEXT 再锚定;其余一律逐字节重同步
            if confirmed:
                stats["valid_crc_frames"] += 1
                stats["recovered_records"] += 1
                if hdr["msgid"] == STATUSTEXT_MSGID and len(hdr["payload"]) >= 1:
                    _emit_statustext(hdr, i)
                i += hdr["total"]
                recovery = False
            else:
                _resync()
            continue

        # 正常模式
        if hdr is None:
            recovery = True
            _resync()
            continue
        if not hdr["fits"]:
            stats["truncated_candidates"] += 1
            recovery = True
            _resync()
            continue
        stats["candidate_records"] += 1
        msgid = hdr["msgid"]
        if hdr["incompat"] & ~KNOWN_INCOMPAT:      # A1 未知 incompat:拒绝,结构跳过
            stats["unsupported_incompat_flags"] += 1
            i += hdr["total"]
            continue
        if msgid in CRC_EXTRA:
            if confirmed:
                stats["valid_crc_frames"] += 1
                if msgid == STATUSTEXT_MSGID and len(hdr["payload"]) >= 1:
                    _emit_statustext(hdr, i)
                i += hdr["total"]
            else:
                stats["crc_failed_frames"] += 1
                if msgid == STATUSTEXT_MSGID:
                    stats["statustext_bad_crc"] += 1  # 兼容镜像
                recovery = True   # CRC 失败:进入恢复,不信任 len
                _resync()
        else:
            stats["unsupported_message_frames"] += 1
            i += hdr["total"]
    return out, stats


def iter_statustext(data):
    """产出 CRC 校验通过、incompat 合法、非分块的 STATUSTEXT (t_unix, severity, text, signature_status)。"""
    out, _ = decode(data)
    for rec in out:
        yield rec


def summarize(data):
    """STATUSTEXT 汇总 + 结构化协议计数(A5)。accels_inconsistent 仅计 CRC 通过的帧。"""
    from collections import Counter
    out, stats = decode(data)
    counts = Counter(text for _t, _s, text, _sig in out)
    first = out[0][0] if out else None
    last = out[-1][0] if out else None
    return {
        "statustext_total": len(out),
        "window_sec": round((last - first), 3) if first is not None else 0.0,
        "accels_inconsistent_count": sum(v for k, v in counts.items() if "Accels inconsistent" in k),
        "signed_unverified_statustext": sum(1 for r in out if r[3] == "UNVERIFIED"),
        "markers_seen": {  # 仅"该 marker 文本出现",不升级为"完整 boot 完成"
            "ardupilot_ready_marker": any("ArduPilot Ready" in k for k in counts),
            "ekf_origin_set_marker": any("origin set" in k for k in counts),
            "baro_calibrated_marker": any("Barometer" in k and "calibration complete" in k for k in counts),
        },
        "distinct_texts": len(counts),
        "protocol_stats": stats,
    }


# ---------- 测试辅助:构造帧(计算真实 CRC);普通组合测试用,非唯一 oracle(见 A4 独立向量) ----------
def build_frame(msgid, payload, *, mavlink2=True, incompat=0x00, signature=b"",
                seq=0, sysid=1, compid=1, crc_extra=None, corrupt_crc=False):
    """构造单个 MAVLink 帧(真实 X25 CRC)。incompat 显式可控(测试未知 flag);
    signature 为附加签名字节(仅在 incompat&0x01 时随帧输出)。corrupt_crc 翻转 CRC 一位。"""
    if crc_extra is None:
        crc_extra = CRC_EXTRA.get(msgid)
    if mavlink2:
        hdr = bytes([0xFD, len(payload), incompat, 0, seq, sysid, compid,
                     msgid & 0xFF, (msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF])
    else:
        hdr = bytes([0xFE, len(payload), seq, sysid, compid, msgid & 0xFF])
    crc = x25_crc(hdr[1:] + payload, crc_extra)
    if corrupt_crc:
        crc ^= 0x0001
    frame = hdr + payload + struct.pack("<H", crc)
    if mavlink2 and (incompat & 0x01):
        frame += (signature if signature else b"\x00" * 13)
    return frame


def build_record(ts_us, frame):
    return struct.pack(">Q", ts_us) + frame


def build_statustext_record(ts_us, severity, text, *, mavlink2=True, incompat=0x00,
                            signature=b"", corrupt_crc=False, chunk_id=0, chunk_seq=0):
    tb = text.encode("ascii")[:50]
    payload = bytes([severity]) + tb
    if chunk_id or chunk_seq:
        payload = bytes([severity]) + tb.ljust(50, b"\x00") + struct.pack("<H", chunk_id) + bytes([chunk_seq])
    frame = build_frame(STATUSTEXT_MSGID, payload, mavlink2=mavlink2, incompat=incompat,
                        signature=signature, crc_extra=83, corrupt_crc=corrupt_crc)
    return build_record(ts_us, frame)


if __name__ == "__main__":
    import sys
    import json
    print(json.dumps(summarize(sys.argv[1]), ensure_ascii=False, indent=2))
