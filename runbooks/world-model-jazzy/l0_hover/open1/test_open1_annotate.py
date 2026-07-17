#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 · 独立标注工具 schema/provenance 失败关闭测试(B3/B6 反例)。

以正式 TSV 为底,逐反例单变量注入(控制变量),断言 parse_tsv 失败关闭;
provenance 反例经 cmd_verify 断言 FAIL。全部环境无关(不依赖 world-model 产物在盘)。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import open1_annotate as A  # noqa: E402

FAIL = 0


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def parse_fails(name, text):
    with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8") as f:
        f.write(text)
        p = f.name
    try:
        A.parse_tsv(p)
        ck(name, "被放行", "ValueError")
    except ValueError as e:
        ck(name, "ValueError", "ValueError")
        print(f"    ↳ {e}")
    finally:
        os.unlink(p)


SHA = "a" * 64
ROW = ["20260715T204428.255001623Z", "/tmp/rd1", "eab0cc6",
       "EXTERNAL_REGISTRY:runbooks/x.md#s", "p", "m",
       SHA, SHA, SHA, SHA, SHA, "true", "TASK_STATUS_OK", "true",
       "Arm: Accels inconsistent", "20", "prov", "notprov", "meth", "src"]
ROW2 = list(ROW)
ROW2[0] = "20260715T211927.641462689Z"
ROW2[1] = "/tmp/rd2"
HEAD = "# schema=" + A.SCHEMA_VERSION + "\n" + "\t".join(A.COLUMNS) + "\n"


def tsv(rows):
    return HEAD + "\n".join("\t".join(r) for r in rows) + "\n"


print("======== 合法基准必须通过 ========")
with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8") as f:
    f.write(tsv([ROW, ROW2]))
    okp = f.name
try:
    meta, rows = A.parse_tsv(okp)
    ck("合法两行 parse 通过", len(rows), 2)
finally:
    os.unlink(okp)

print("======== B3/B6 失败关闭反例(单变量注入) ========")
r = list(ROW2); r[0] = ROW[0]
parse_fails("B6-03 重复 run_id", tsv([ROW, r]))
r = list(ROW2); r[1] = ROW[1]
parse_fails("B6-04 重复 run_dir", tsv([ROW, r]))
r = list(ROW); r[7] = SHA[:16]
parse_fails("B6-05 短 hash(16位前缀)", tsv([r]))
r = list(ROW); r[7] = "z" * 64
parse_fails("B6-06 非十六进制 hash", tsv([r]))
cols = [c for c in A.COLUMNS if c != "tlog_sha256"]
parse_fails("B6-07 缺必需列", "# schema=" + A.SCHEMA_VERSION + "\n" + "\t".join(cols) + "\n"
            + "\t".join(v for c, v in zip(A.COLUMNS, ROW) if c != "tlog_sha256") + "\n")
parse_fails("B6-08 未知额外列", "# schema=" + A.SCHEMA_VERSION + "\n" + "\t".join(A.COLUMNS + ["mystery"]) + "\n"
            + "\t".join(ROW + ["x"]) + "\n")
r = list(ROW); r[11] = "yes"
parse_fails("B6-09 非法布尔", tsv([r]))
r = list(ROW); r[15] = "not_a_number"
parse_fails("B6-10a 非法 target_count", tsv([r]))
r = list(ROW); r[15] = "-1"
parse_fails("B6-10b 负数 target_count", tsv([r]))
r = list(ROW); r[0] = "run-without-format"
parse_fails("B3-11 非法 run_id 格式", tsv([r]))
parse_fails("B3-14 未知 schema 版本", "# schema=unknown.v9\n" + "\t".join(A.COLUMNS) + "\n" + "\t".join(ROW) + "\n")
parse_fails("B3-15 空文件", "")
parse_fails("B3-16 仅注释无数据", "# schema=" + A.SCHEMA_VERSION + "\n# only comments\n")
r = list(ROW); r[len(ROW) - 1:] = []  # 少一个字段
parse_fails("B3-04 字段数不足", tsv([r]))
r = list(ROW) + ["extra_field"]
parse_fails("B3-05 字段数过多", tsv([r]))

print("======== B6-11 不存在 commit(显式覆盖)必须 FAIL ========")
with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8") as f:
    f.write("# schema=" + A.SCHEMA_VERSION + "\n# tool_commit=" + "d" * 40 + "\n# data_commit=" + "e" * 40 + "\n"
            + "\t".join(A.COLUMNS) + "\n" + "\t".join(ROW) + "\n")
    bad = f.name
try:
    rc = A.cmd_verify(bad)
    ck("B6-11 伪 commit → verify rc=1", rc, 1)
finally:
    os.unlink(bad)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
