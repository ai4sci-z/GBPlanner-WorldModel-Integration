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

print("======== B-07 冻结门/provenance 反例(显式 commit 覆盖中和派生噪声) ========")
import re as _re
import subprocess as _sp
HEAD = _sp.run(["git","rev-parse","HEAD"],cwd=os.path.dirname(os.path.abspath(__file__)),
               capture_output=True,text=True).stdout.strip()
REAL = open(A.DEFAULT_TSV,encoding="utf-8").read()

def with_meta(text):
    return text.replace("# schema="+A.SCHEMA_VERSION,
        "# schema="+A.SCHEMA_VERSION+"\n# tool_commit="+HEAD+"\n# data_commit="+HEAD)

def gate_rc(text, name, expect_nonzero=True, expect_substr=None):
    global FAIL
    with tempfile.NamedTemporaryFile("w",suffix=".tsv",delete=False,encoding="utf-8") as f:
        f.write(text); path=f.name
    try:
        r=_sp.run(["python3","open1_annotate.py","verify","--tsv",path],
                  cwd=os.path.dirname(os.path.abspath(__file__)),capture_output=True,text=True)
        ok = (r.returncode!=0) if expect_nonzero else (r.returncode==0)
        if ok and expect_substr and expect_substr not in r.stdout: ok=False
        tail=r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        print(("PASS" if ok else "FAIL")+f": {name} rc={r.returncode} :: {tail}")
        if not ok: FAIL+=1
    finally: os.unlink(path)

def _set(line, idx, val):
    parts=line.split("\t"); parts[idx]=val; return parts

def mut_rows(text, fn):
    out=[]
    for ln in text.split("\n"):
        out.append(fn(ln) if ln.startswith("2026") else ln)
    return "\n".join(out)

# 基准:真 TSV + 显式覆盖 → 门必须绿
gate_rc(with_meta(REAL), "B-07 基准(真TSV+覆盖)rc=0", expect_nonzero=False, expect_substr="PASS=5 FAIL=0 SKIP=0")
# 全 SKIP / 部分 SKIP
gate_rc(with_meta(REAL.replace("/world-model/artifacts","/nonexistent/artifacts")),
        "B-07 全SKIP→非零", expect_substr="SKIP=5")
one=REAL.replace("hover/20260715T204428","NOPE/20260715T204428",1)
gate_rc(with_meta(one), "B-07 部分SKIP(1)→非零", expect_substr="SKIP=1")
# 行数不足/多出
lines=with_meta(REAL).rstrip("\n").split("\n")
gate_rc("\n".join(lines[:-1])+"\n", "B-07 行数4→非零", expect_substr="行集")
extra=list(lines); dup=[l for l in lines if l.startswith("2026")][0].split("\t")
dup[0]="20260715T999999.000000000Z"; dup[1]="/tmp/none999"; extra.append("\t".join(dup))
gate_rc("\n".join(extra)+"\n", "B-07 行数6→非零")
# claimed SHA:短/非hex/deadbeef40/存在但错(288b486 全长,可解析但 registry 未记载)
gate_rc(with_meta(mut_rows(REAL, lambda l: "\t".join(_set(l,2,"eab0cc6")))), "B-07 短SHA→非零", expect_substr="40位")
gate_rc(with_meta(mut_rows(REAL, lambda l: "\t".join(_set(l,2,"z"*40)))), "B-07 非hex SHA→非零")
gate_rc(with_meta(mut_rows(REAL, lambda l: "\t".join(_set(l,2,"deadbeef"*5)))), "B-07 deadbeef40→非零", expect_substr="无法在 wm 仓解析")
SHA288=_sp.run(["git","-C","/home/ai4s/projects/world-model","rev-parse","288b486"],capture_output=True,text=True).stdout.strip()
gate_rc(with_meta(mut_rows(REAL, lambda l: "\t".join(_set(l,2,SHA288)))), "B-07 存在但错误commit→非零(registry未记载)", expect_substr="节内未记载该 commit")
# registry:文件不存在 / section 不存在 / 伪前缀内容
gate_rc(with_meta(mut_rows(REAL, lambda l: "\t".join(_set(l,3,"EXTERNAL_REGISTRY:governance/不存在.md#集合 A")))),
        "B-07 registry文件不存在→非零", expect_substr="registry 文件不存在")
gate_rc(with_meta(mut_rows(REAL, lambda l: "\t".join(_set(l,3,l.split("\t")[3].replace("#\u0023\u0023 1. \u6837\u672c\u5206\u5c42","#\u4e0d\u5b58\u5728\u7684\u8282") if False else l.split("\t")[3].replace("## 1. 样本分层","不存在的节"))))),
        "B-07 section不存在→非零", expect_substr="无该 section")
gate_rc(with_meta(mut_rows(REAL, lambda l: "\t".join(_set(l,3,"EXTERNAL_REGISTRY:FAKE-NOT-CHECKED")))),
        "B-07 伪registry串→非零")
# artifact path 不一致(run_dir 基名≠run_id)
def swap_dir(l):
    parts=l.split("\t")
    if parts[0].startswith("20260715T204428"):
        parts[1]="/home/ai4s/projects/world-model/artifacts/sim/hover/20260715T211927.641462689Z"
    return "\t".join(parts)
bad=mut_rows(REAL, swap_dir)
# 该变体产生重复 run_dir → schema 层拒;为测 path 绑定,同时改 211927 行 dir
def swap_both(l):
    parts=l.split("\t")
    if parts[0].startswith("20260715T204428"):
        parts[1]="/home/ai4s/projects/world-model/artifacts/sim/hover/20260715T211927.641462689Z"
    elif parts[0].startswith("20260715T211927"):
        parts[1]="/home/ai4s/projects/world-model/artifacts/sim/hover/20260715T204428.255001623Z"
    return "\t".join(parts)
gate_rc(with_meta(mut_rows(REAL, swap_both)), "B-07 artifact path交换→非零")

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
