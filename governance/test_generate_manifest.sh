#!/usr/bin/env bash
# 治理生成器自动测试(R003 第二阶段补正·动作 7):正例 + 失败反例。
# 覆盖:参数缺失/未知仓库类型/闭包 missing/extra/duplicate/字段数/尾随空白/确定性。
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
GEN="$HERE/generate_manifest.py"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" -eq "$3" ]; then echo "PASS: $1 (rc=$3)"; PASS=$((PASS+1)); else echo "FAIL: $1 期望 rc=$2 实得 rc=$3"; FAIL=$((FAIL+1)); fi; }

# 造一个含非 ASCII 路径/空文件/子目录的最小 git 仓库
REPO=$TMP/repo
mkdir -p "$REPO/docs/archive" "$REPO/runbooks"
git -C "$REPO" init -q
printf 'x\n' > "$REPO/README.md"
: > "$REPO/docs/空文件_中文名.md"
printf 'e\n' > "$REPO/runbooks/evidence.txt"
git -C "$REPO" add -A && git -C "$REPO" -c user.email=t@t -c user.name=t commit -qm init

echo "=== 反例:参数缺失 ==="
python3 "$GEN" >/dev/null 2>&1; check "参数缺失" 2 $?
echo "=== 反例:未知仓库类型 ==="
python3 "$GEN" "$REPO" nosuch "$TMP/x.tsv" >/dev/null 2>&1; check "未知仓库类型" 2 $?
echo "=== 反例:worktree 不存在 ==="
python3 "$GEN" "$TMP/nodir" main "$TMP/x.tsv" >/dev/null 2>&1; check "worktree不存在" 2 $?

echo "=== 正例:生成+自校验(含非 ASCII 与空文件) ==="
python3 "$GEN" "$REPO" main "$TMP/m.tsv" >/dev/null 2>&1; check "生成自校验" 0 $?
grep -q "空文件_中文名" "$TMP/m.tsv"; check "非ASCII路径入册" 0 $?
awk -F'\t' '!/^#/ && !/^path\t/ && NF!=6 {bad=1} END{exit bad}' "$TMP/m.tsv"; check "字段数=6" 0 $?
grep -qE ' +$|\t$' "$TMP/m.tsv"; check "无尾随空白(grep应不中)" 1 $?

echo "=== 正例:--verify 闭包成立 ==="
python3 "$GEN" --verify "$REPO" main "$TMP/m.tsv" >/dev/null 2>&1; check "verify通过" 0 $?

echo "=== 反例:missing(清单少一行) ==="
grep -v "README.md" "$TMP/m.tsv" > "$TMP/miss.tsv"
python3 "$GEN" --verify "$REPO" main "$TMP/miss.tsv" >/dev/null 2>&1; check "missing检出" 4 $?
echo "=== 反例:extra(清单多一行) ==="
{ cat "$TMP/m.tsv"; printf 'ghost.md\t1\tACTIVE_REFERENCE\tUNVERIFIED\tdeadbeef0000\t-\n'; } > "$TMP/extra.tsv"
python3 "$GEN" --verify "$REPO" main "$TMP/extra.tsv" >/dev/null 2>&1; check "extra检出" 4 $?
echo "=== 反例:duplicate(清单重复行) ==="
{ cat "$TMP/m.tsv"; grep -m1 "^README.md" "$TMP/m.tsv"; } > "$TMP/dup.tsv"
python3 "$GEN" --verify "$REPO" main "$TMP/dup.tsv" >/dev/null 2>&1; check "duplicate检出" 4 $?
echo "=== 反例:字段数错 ==="
{ cat "$TMP/m.tsv"; printf 'bad.md\t1\tACTIVE_REFERENCE\n'; } > "$TMP/badf.tsv"
python3 "$GEN" --verify "$REPO" main "$TMP/badf.tsv" >/dev/null 2>&1; check "字段数错检出" 5 $?
echo "=== 反例:清单文件不存在 ==="
python3 "$GEN" --verify "$REPO" main "$TMP/nofile.tsv" >/dev/null 2>&1; check "清单不存在" 2 $?

echo "=== 反例:多余参数 ==="
python3 "$GEN" "$REPO" main "$TMP/x.tsv" extra_arg >/dev/null 2>&1; check "多余参数" 2 $?

echo "=== 反例:tracked 路径含 tab(失败关闭) ==="
REPO2=$TMP/repo_tab
mkdir -p "$REPO2"; git -C "$REPO2" init -q
printf 'x\n' > "$REPO2/a	b.md"
git -C "$REPO2" add -A && git -C "$REPO2" -c user.email=t@t -c user.name=t commit -qm t
python3 "$GEN" "$REPO2" main "$TMP/tab.tsv" >/dev/null 2>&1; check "tab路径失败关闭" 5 $?

echo "=== 边界:symlink / 假 gitlink / tracked但缺失 ==="
ln -s README.md "$REPO/link.md"
git -C "$REPO" update-index --add --cacheinfo 160000,$(git -C "$REPO" rev-parse HEAD),fakemod
rm "$REPO/runbooks/evidence.txt"
git -C "$REPO" add link.md 2>/dev/null
git -C "$REPO" -c user.email=t@t -c user.name=t commit -qm edge >/dev/null 2>&1
python3 "$GEN" "$REPO" main "$TMP/edge.tsv" >/dev/null 2>&1; check "边界生成" 0 $?
grep -q "^link.md	1	" "$TMP/edge.tsv"; check "symlink按目标行数入册" 0 $?
grep -q "^fakemod	-1	.*gitlink" "$TMP/edge.tsv"; check "gitlink入册lines=-1" 0 $?
grep -q "^runbooks/evidence.txt	-1	" "$TMP/edge.tsv"; check "tracked但工作树缺失入册lines=-1" 0 $?

echo "=== 边界:分类优先级(docs/archive 优先于 docs/) ==="
mkdir -p "$REPO/docs/archive"; printf 'h\n' > "$REPO/docs/archive/old.md"
git -C "$REPO" add -A && git -C "$REPO" -c user.email=t@t -c user.name=t commit -qm prio
python3 "$GEN" "$REPO" main "$TMP/prio.tsv" >/dev/null 2>&1
grep -q "^docs/archive/old.md	1	ARCHIVE	" "$TMP/prio.tsv"; check "优先级冲突取ARCHIVE" 0 $?

echo "=== 反例:非法 category / 非法 audit_status ==="
python3 "$GEN" "$REPO" main "$TMP/v.tsv" >/dev/null 2>&1
sed '0,/\tACTIVE_REFERENCE\t/s//\tBOGUS_CATEGORY\t/' "$TMP/v.tsv" > "$TMP/badcat.tsv"
python3 "$GEN" --verify "$REPO" main "$TMP/badcat.tsv" >/dev/null 2>&1; check "非法category检出" 5 $?
sed '0,/\tUNVERIFIED\t/s//\tBOGUS_AUDIT\t/' "$TMP/v.tsv" > "$TMP/badaud.tsv"
python3 "$GEN" --verify "$REPO" main "$TMP/badaud.tsv" >/dev/null 2>&1; check "非法audit检出" 5 $?

echo "=== 反例:头部缺绑定 commit ==="
grep -v "HEAD=" "$TMP/v.tsv" > "$TMP/nohead.tsv"
python3 "$GEN" --verify "$REPO" main "$TMP/nohead.tsv" >/dev/null 2>&1; check "缺HEAD头检出" 5 $?

echo "=== 语义:绑定 commit 判定 + 当前 HEAD 增量为信息项 ==="
printf 'n\n' > "$REPO/newfile.md"
git -C "$REPO" add newfile.md && git -C "$REPO" -c user.email=t@t -c user.name=t commit -qm new
OUT=$(python3 "$GEN" --verify "$REPO" main "$TMP/v.tsv" 2>&1); RC=$?
check "绑定commit集合仍通过" 0 $RC
echo "$OUT" | grep -q "added=1"; check "当前HEAD增量=1被报告" 0 $?

echo "=== 确定性:同 HEAD 背靠背生成逐字节一致 ==="
python3 "$GEN" "$REPO" main "$TMP/det1.tsv" >/dev/null 2>&1
python3 "$GEN" "$REPO" main "$TMP/det2.tsv" >/dev/null 2>&1
cmp -s "$TMP/det1.tsv" "$TMP/det2.tsv"; check "确定性" 0 $?

echo "=== 真仓种子校验:wm 30 种子必须全部命中(反例=破坏一条) ==="
python3 - "$GEN" <<'PYEOF'
import subprocess,sys,tempfile,os
gen=sys.argv[1]
src=open(gen).read()
bad=src.replace('"orchestration/sim/cmd/navlab-sim/main.go"','"orchestration/sim/cmd/navlab-sim/NOSUCH.go"',1)
with tempfile.NamedTemporaryFile('w',suffix='.py',delete=False) as f:
    f.write(bad); tmp=f.name
r=subprocess.run(['python3',tmp,'/home/ai4s/projects/world-model','wm','/dev/null'],capture_output=True)
os.unlink(tmp)
print(f"  内层生成器 rc={r.returncode}(预期 5)")
sys.exit(0 if r.returncode==5 else 1)
PYEOF
check "种子未命中检出(外层判定=内层rc==5)" 0 $?

echo "================================"
echo "结果: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
