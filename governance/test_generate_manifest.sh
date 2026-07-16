#!/usr/bin/env bash
# 治理生成器测试(阶段 B 两门版):正例 + GOV-05 全部失败反例。
# 每例打印【期望/实得】退出码;末尾分项汇总。真实仓库只做只读校验。
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
GEN="$HERE/generate_manifest.py"
MAIN_WT=$(cd "$HERE/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
check() { # name expected actual
  if [ "$2" -eq "$3" ]; then echo "PASS: $1 【期望 rc=$2 / 实得 rc=$3】"; PASS=$((PASS+1));
  else echo "FAIL: $1 【期望 rc=$2 / 实得 rc=$3】"; FAIL=$((FAIL+1)); fi
}
gitc(){ git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }

# ---------- fixture A:干净仓(非 ASCII/空文件/symlink/真 gitlink) ----------
A=$TMP/A
mkdir -p "$A/docs/archive" "$A/runbooks"
git -C "$A" init -q
printf 'l1\nl2\n' > "$A/a.md"
: > "$A/docs/空文件_中文名.md"
printf 'e\n' > "$A/runbooks/evidence.txt"
printf 'h\n' > "$A/docs/archive/old.md"
ln -s a.md "$A/link.md"
mkdir "$A/sub"; git -C "$A/sub" init -q; printf 's\n' > "$A/sub/s.txt"
gitc "$A/sub" add -A; gitc "$A/sub" commit -qm s
git -C "$A" add -A 2>/dev/null; gitc "$A" commit -qm init
C1=$(git -C "$A" rev-parse HEAD)

echo "=== 用法类反例 ==="
python3 "$GEN" >/dev/null 2>&1;                                check "参数缺失" 2 $?
python3 "$GEN" "$A" main "$TMP/x.tsv" extra >/dev/null 2>&1;   check "多余参数" 2 $?
python3 "$GEN" "$A" nosuch "$TMP/x.tsv" >/dev/null 2>&1;       check "非法repo_key" 2 $?
python3 "$GEN" "$TMP/nodir" main "$TMP/x.tsv" >/dev/null 2>&1; check "worktree不存在" 2 $?
python3 "$GEN" --verify "$A" main "$TMP/x.tsv" >/dev/null 2>&1;      check "旧--verify已拆分" 2 $?
python3 "$GEN" --verify-bound "$A" main "$TMP/nofile.tsv" >/dev/null 2>&1; check "清单不存在" 2 $?

echo "=== 正例:生成+两门自检(干净树,含 symlink/gitlink) ==="
python3 "$GEN" "$A" main "$TMP/m.tsv" >/dev/null 2>&1;   check "生成两门自检" 0 $?
grep -q "空文件_中文名" "$TMP/m.tsv";                     check "非ASCII路径入册" 0 $?
awk -F'\t' '!/^#/ && !/^path\t/ && NF!=6 {bad=1} END{exit bad}' "$TMP/m.tsv"; check "字段数=6" 0 $?
grep -qE ' +$|	$' "$TMP/m.tsv";                           check "无尾随空白(grep应不中)" 1 $?
grep -q "^sub	-1	" "$TMP/m.tsv";                          check "gitlink入册lines=-1" 0 $?
OUT=$(python3 "$GEN" --verify-bound "$A" main "$TMP/m.tsv" 2>&1); check "bound门通过" 0 $?
echo "$OUT" | grep -q "symlink_lines_skipped=1";           check "symlink跳过计数=1" 0 $?
python3 "$GEN" --verify-current "$A" main "$TMP/m.tsv" >/dev/null 2>&1; check "current门通过" 0 $?

echo "=== 行事实篡改反例(GOV-01;全部在合法枚举内篡改) ==="
tamper(){ python3 - "$1" "$TMP/m.tsv" "$2" <<'PY'
import re,sys
mode,src,out=sys.argv[1],sys.argv[2],sys.argv[3]
s=open(src).read()
m=re.search(r'^a\.md\t(\d+)\t(\S+)\t(\S+)\t([0-9a-f]{12})\t',s,flags=re.M); assert m
row=m.group(0)
rep={'lines':row.replace('\t'+m.group(1)+'\t','\t999999\t',1),
     'cat':row.replace('\t'+m.group(2)+'\t','\tARCHIVE\t',1),
     'audit':row.replace('\t'+m.group(3)+'\t','\tVERIFIED_PASS\t',1),
     'rowcommit':row.replace('\t'+m.group(4)+'\t','\tdeadbeefdead\t',1)}[mode]
open(out,'w').write(s.replace(row,rep,1))
PY
}
for mode in lines cat audit rowcommit; do
  tamper $mode "$TMP/t_$mode.tsv"
  python3 "$GEN" --verify-bound "$A" main "$TMP/t_$mode.tsv" >/dev/null 2>&1
  check "篡改${mode}被拒" 6 $?
done

echo "=== 格式/引用反例 ==="
sed '0,/\tACTIVE_REFERENCE\t/s//\tBOGUS_CATEGORY\t/' "$TMP/m.tsv" > "$TMP/badcat.tsv"
python3 "$GEN" --verify-bound "$A" main "$TMP/badcat.tsv" >/dev/null 2>&1; check "非法category枚举" 5 $?
sed '0,/\tUNVERIFIED\t/s//\tBOGUS_AUDIT\t/' "$TMP/m.tsv" > "$TMP/badaud.tsv"
python3 "$GEN" --verify-bound "$A" main "$TMP/badaud.tsv" >/dev/null 2>&1; check "非法audit枚举" 5 $?
{ cat "$TMP/m.tsv"; printf 'bad.md\t1\tACTIVE_REFERENCE\n'; } > "$TMP/badf.tsv"
python3 "$GEN" --verify-bound "$A" main "$TMP/badf.tsv" >/dev/null 2>&1;   check "字段数错" 5 $?
grep -v "HEAD=" "$TMP/m.tsv" > "$TMP/nohead.tsv"
python3 "$GEN" --verify-bound "$A" main "$TMP/nohead.tsv" >/dev/null 2>&1; check "缺绑定头" 5 $?
python3 - "$TMP/m.tsv" "$TMP/badint.tsv" <<'PY'
import re,sys
s=open(sys.argv[1]).read()
s=re.sub(r'^(a\.md\t)\d+(\t)', r'\1NaN\2', s, count=1, flags=re.M)
open(sys.argv[2],'w').write(s)
PY
python3 "$GEN" --verify-bound "$A" main "$TMP/badint.tsv" >/dev/null 2>&1; check "lines非整数" 5 $?
sed "s/HEAD=$C1/HEAD=0000000000000000000000000000000000000000/" "$TMP/m.tsv" > "$TMP/badcommit.tsv"
python3 "$GEN" --verify-bound "$A" main "$TMP/badcommit.tsv" >/dev/null 2>&1; check "绑定commit不存在" 5 $?

echo "=== 集合反例(bound 门) ==="
grep -v "^a.md	" "$TMP/m.tsv" > "$TMP/miss.tsv"
python3 "$GEN" --verify-bound "$A" main "$TMP/miss.tsv" >/dev/null 2>&1;   check "missing检出" 4 $?
{ cat "$TMP/m.tsv"; printf 'ghost.md\t1\tACTIVE_REFERENCE\tUNVERIFIED\t%s\t-\n' "${C1:0:12}"; } > "$TMP/extra.tsv"
python3 "$GEN" --verify-bound "$A" main "$TMP/extra.tsv" >/dev/null 2>&1;  check "extra检出" 4 $?
{ cat "$TMP/m.tsv"; grep -m1 "^a.md	" "$TMP/m.tsv"; } > "$TMP/dup.tsv"
python3 "$GEN" --verify-bound "$A" main "$TMP/dup.tsv" >/dev/null 2>&1;    check "duplicate检出" 4 $?

echo "=== 工作树反例(current 门;GOV-02) ==="
echo ghost > "$A/untracked.md"
python3 "$GEN" --verify-current "$A" main "$TMP/m.tsv" >/dev/null 2>&1; check "untracked使current非零" 7 $?
python3 "$GEN" --verify-bound "$A" main "$TMP/m.tsv" >/dev/null 2>&1;   check "untracked不影响bound" 0 $?
rm "$A/untracked.md"
rm "$A/runbooks/evidence.txt"
python3 "$GEN" --verify-current "$A" main "$TMP/m.tsv" >/dev/null 2>&1; check "tracked工作树缺失" 7 $?
git -C "$A" checkout -q -- runbooks/evidence.txt
printf 'new\n' > "$A/new.md"; git -C "$A" add new.md; gitc "$A" commit -qm add
python3 "$GEN" --verify-current "$A" main "$TMP/m.tsv" >/dev/null 2>&1; check "HEAD新增tracked(ADDED)" 7 $?
python3 "$GEN" --verify-bound "$A" main "$TMP/m.tsv" >/dev/null 2>&1;   check "HEAD前进后bound仍成立" 0 $?
git -C "$A" rm -q new.md; git -C "$A" rm -q docs/空文件_中文名.md; gitc "$A" commit -qm rm
python3 "$GEN" --verify-current "$A" main "$TMP/m.tsv" >/dev/null 2>&1; check "HEAD删除tracked(REMOVED)" 7 $?
git -C "$A" reset -q --hard "$C1"

echo "=== 生成时工作树不洁 → 生成失败关闭 ==="
printf 'dirty\n' >> "$A/a.md"
python3 "$GEN" "$A" main "$TMP/dirty.tsv" >/dev/null 2>&1; check "脏树生成被拒" 7 $?
git -C "$A" checkout -q -- a.md

echo "=== classifier 漂移反例(副本生成器改规则后校验原清单) ==="
python3 - "$GEN" "$A" "$TMP/m.tsv" <<'PY'
import subprocess,sys,tempfile,os
gen,wt,man=sys.argv[1],sys.argv[2],sys.argv[3]
src=open(gen).read()
bad=src.replace('return "ACTIVE_REFERENCE", "设计/审计文档;dated 快照以标注日期为界"',
                'return "ARCHIVE", "漂移"',1)
assert bad!=src
with tempfile.NamedTemporaryFile('w',suffix='.py',delete=False) as f: f.write(bad); tmp=f.name
r=subprocess.run(['python3',tmp,'--verify-bound',wt,'main',man],capture_output=True)
os.unlink(tmp)
print(f"  内层漂移生成器 rc={r.returncode}(预期 6)")
sys.exit(0 if r.returncode==6 else 1)
PY
check "classifier漂移被拒(外层判定=内层rc==6)" 0 $?

echo "=== tab 路径失败关闭 ==="
B=$TMP/B; mkdir -p "$B"; git -C "$B" init -q
printf 'x\n' > "$B/a	b.md"; git -C "$B" add -A; gitc "$B" commit -qm t
python3 "$GEN" "$B" main "$TMP/tab.tsv" >/dev/null 2>&1; check "tab路径失败关闭" 5 $?

echo "=== 确定性:同 HEAD 背靠背生成逐字节一致 ==="
python3 "$GEN" "$A" main "$TMP/d1.tsv" >/dev/null 2>&1
python3 "$GEN" "$A" main "$TMP/d2.tsv" >/dev/null 2>&1
cmp -s "$TMP/d1.tsv" "$TMP/d2.tsv"; check "确定性" 0 $?

echo "=== audit source 缺失(wm 种子破坏;双退出码) ==="
python3 - "$GEN" <<'PY'
import subprocess,sys,tempfile,os
gen=sys.argv[1]
src=open(gen).read()
bad=src.replace('"orchestration/sim/cmd/navlab-sim/main.go"','"orchestration/sim/cmd/navlab-sim/NOSUCH.go"',1)
with tempfile.NamedTemporaryFile('w',suffix='.py',delete=False) as f: f.write(bad); tmp=f.name
r=subprocess.run(['python3',tmp,'/home/ai4s/projects/world-model','wm','/dev/null'],capture_output=True)
os.unlink(tmp)
print(f"  内层生成器 rc={r.returncode}(预期 5)")
sys.exit(0 if r.returncode==5 else 1)
PY
check "audit种子未命中被拒(外层判定=内层rc==5)" 0 $?

echo "=== 真实仓只读校验(三仓 bound 门) ==="
python3 "$GEN" --verify-bound "$MAIN_WT" main "$HERE/manifest_main.tsv" >/dev/null 2>&1; check "真仓main bound" 0 $?
python3 "$GEN" --verify-bound /home/ai4s/projects/gbp-feat feat "$HERE/manifest_feat.tsv" >/dev/null 2>&1; check "真仓feat bound" 0 $?
python3 "$GEN" --verify-bound /home/ai4s/projects/world-model wm "$HERE/manifest_wm.tsv" >/dev/null 2>&1; check "真仓wm bound" 0 $?

echo "================================"
echo "结果: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
