#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1C-03 · run registry 反例门(12 fixture 案)。

expected 来源=E1C-03.1 硬规则(三身份分离/唯一新增/结构约束/失败关闭)。
全部临时目录 fixture,零 world-model 访问、零仿真。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_registry as RR  # noqa: E402

FAIL = 0
RID1 = "20260715T204428.255001623Z"
RID2 = "20260715T205113.276955543Z"


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def cli(*args):
    return subprocess.run([sys.executable, os.path.join(HERE, "run_registry.py"), *args],
                          capture_output=True, text=True, timeout=30)


def setup():
    base = tempfile.mkdtemp(prefix="rr_")
    watch = os.path.join(base, "hover")
    os.makedirs(watch)
    reg = os.path.join(base, "run_registry")
    return base, watch, reg


def begin(reg, watch, idx=1, batch="b1"):
    cp = cli("begin", "--registry-dir", reg, "--batch-id", batch,
             "--run-index", str(idx), "--watch-dir", watch)
    assert cp.returncode == 0, cp.stderr
    return cp


def resolve(reg, idx=1, timeout="0.2"):
    cp = cli("resolve", "--registry-dir", reg, "--run-index", str(idx),
             "--timeout-sec", timeout)
    return json.loads(cp.stdout.strip().splitlines()[-1])


print("======== 案1 唯一新增目录 → RESOLVED ========")
base, watch, reg = setup()
os.makedirs(os.path.join(watch, "20260101T000000.000000000Z"))  # 旧目录
begin(reg, watch)
os.makedirs(os.path.join(watch, RID1))
r = resolve(reg)
ck("案1 RESOLVED", r["identity_status"], "RESOLVED")
ck("案1 run_id=目录基名", r["world_model_run_id"], RID1)

print("======== 案2 没有新增 → UNKNOWN ========")
base, watch, reg = setup()
begin(reg, watch)
r = resolve(reg)
ck("案2 UNKNOWN(零新增不猜)", r["identity_status"], "UNKNOWN")

print("======== 案3 同时新增两个 → UNKNOWN(禁止猜一个)========")
base, watch, reg = setup()
begin(reg, watch)
os.makedirs(os.path.join(watch, RID1))
os.makedirs(os.path.join(watch, RID2))
r = resolve(reg)
ck("案3 UNKNOWN", r["identity_status"], "UNKNOWN")

print("======== 案4 旧目录 mtime 被修改 → 不算新增 ========")
base, watch, reg = setup()
old = os.path.join(watch, "20260101T000000.000000000Z")
os.makedirs(old)
begin(reg, watch)
os.utime(old, None)   # 触碰 mtime
r = resolve(reg)
ck("案4 UNKNOWN(集合差不看 mtime)", r["identity_status"], "UNKNOWN")

print("======== 案5 symlink 新目录 → 拒绝 ========")
base, watch, reg = setup()
real_elsewhere = tempfile.mkdtemp()
begin(reg, watch)
os.symlink(real_elsewhere, os.path.join(watch, RID1))
r = resolve(reg)
ck("案5 UNKNOWN(symlink 拒)", r["identity_status"], "UNKNOWN")
ck("案5b 拒因登记", any("symlink" in x for x in r["rejected"]), True)

print("======== 案6 新目录名非法 → 拒绝 ========")
base, watch, reg = setup()
begin(reg, watch)
os.makedirs(os.path.join(watch, "not-a-run-id"))
r = resolve(reg)
ck("案6 UNKNOWN(名字不符 run_id 模式)", r["identity_status"], "UNKNOWN")

print("======== 案7 registry 半写 → 失败关闭 ========")
base, watch, reg = setup()
os.makedirs(reg)
open(os.path.join(reg, "attempt_1.json"), "w").write('{"schema_version": "wp304.run_')
out = RR.load_registry(reg, "b1")
ck("案7 半写条目入 errors", len(out["errors"]) >= 1, True)
cp = cli("read", "--registry-dir", reg, "--batch-id", "b1")
ck("案7b read rc=1(失败关闭)", cp.returncode, 1)

print("======== 案8 batch_id 错 → 拒绝 ========")
base, watch, reg = setup()
begin(reg, watch, batch="b1")
os.makedirs(os.path.join(watch, RID1))
resolve(reg)
out = RR.load_registry(reg, "OTHER_BATCH")
ck("案8 batch 不符入 errors", any("batch_id 不符" in x for x in out["errors"]), True)

print("======== 案9 run_index 重复 → 拒绝 ========")
base, watch, reg = setup()
begin(reg, watch, idx=1)
os.makedirs(reg, exist_ok=True)
import shutil
shutil.copy(os.path.join(reg, "attempt_1.json"), os.path.join(reg, "attempt_2.json"))
out = RR.load_registry(reg, "b1")
ck("案9 重复 run_index 检出", any("run_index 重复" in x for x in out["errors"]), True)

print("======== 案10 run_id 重复(同 batch)→ 拒绝 ========")
base, watch, reg = setup()
begin(reg, watch, idx=1)
os.makedirs(os.path.join(watch, RID1))
resolve(reg, idx=1)
begin(reg, watch, idx=2)
# 手工把 attempt_2 也 resolve 到同一 run_id(模拟旧目录复用)
e = json.load(open(os.path.join(reg, "attempt_2.json")))
e["world_model_run_id"] = RID1
e["world_model_run_dir"] = os.path.join(watch, RID1)
e["identity_status"] = "RESOLVED"
open(os.path.join(reg, "attempt_2.json"), "w").write(json.dumps(e))
out = RR.load_registry(reg, "b1")
ck("案10 重复 run_id 检出", any("world_model_run_id 重复" in x for x in out["errors"]), True)

print("======== 案11 attempt 失败但目录已创建 → launched 保留 ========")
base, watch, reg = setup()
begin(reg, watch, idx=1)
os.makedirs(os.path.join(watch, RID1))
resolve(reg, idx=1)
cli("finish", "--registry-dir", reg, "--run-index", "1", "--rc", "1")
out = RR.load_registry(reg, "b1")
ck("案11 rc=1 attempt 在册", out["entries"][0]["rc"], 1)
ck("案11b identity 仍 RESOLVED", out["entries"][0]["identity_status"], "RESOLVED")

print("======== 案12 attempt 结束前 sidecar 已读 start registry ========")
base, watch, reg = setup()
begin(reg, watch, idx=1)
os.makedirs(os.path.join(watch, RID1))
resolve(reg, idx=1)   # start 已 resolve,finish 未发生
out = RR.load_registry(reg, "b1")
ck("案12 未 finish 条目可读(rc=None,phase=resolved)",
   (out["entries"][0]["rc"], out["entries"][0]["phase"]), (None, "resolved"))
ck("案12b run_id 与目录基名一致校验通过", out["errors"], [])

print("======== 三身份分离(run_index≠run_id≠batch)========")
e = out["entries"][0]
ck("run_index 是批内序号", e["run_index"], 1)
ck("world_model_run_id 是目录基名", e["world_model_run_id"], RID1)
ck("batch_id 独立", e["batch_id"], "b1")
ck("三者互不相等", len({str(e["run_index"]), e["world_model_run_id"], e["batch_id"]}), 3)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
