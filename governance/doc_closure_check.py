#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档闭包机器检查:六类指标全 0 才通过。仅只读,不改文件。"""
import os, re, subprocess, sys
root=os.getcwd()
files=subprocess.run(["git","ls-files","-z"],capture_output=True,text=True).stdout.split("\0")
active_md=[f for f in files if f.endswith(".md") and not f.startswith(("archive/","docs/archive/","sources/"))]

# 1) 活跃相对链接断链
link_re=re.compile(r'\[[^\]]*\]\(([^)]+)\)')
broken=[]
for f in active_md:
    d=os.path.dirname(f)
    for ln,line in enumerate(open(f,errors="replace"),1):
        for m in link_re.finditer(line):
            t=m.group(1).split("#")[0].strip()
            if not t or t.startswith(("http://","https://","mailto:","/")): continue
            if not os.path.exists(os.path.join(root,os.path.normpath(os.path.join(d,t)))):
                broken.append(f"{f}:{ln}->{t}")

# claim manifest 解析
cm="governance/claim_manifest.tsv"
claim_paths=[]; lifecycle_missing=[]
VALID_LC={"CURRENT","REFERENCE","EVIDENCE","ARCHIVE","UNVERIFIED"}
for line in open(cm):
    if line.startswith("#") or line.startswith("path\t"): continue
    line=line.rstrip("\n")
    if not line: continue
    parts=line.split("\t")
    p=parts[0]; claim_paths.append(p)
    lc=parts[2] if len(parts)>2 else ""
    if lc not in VALID_LC: lifecycle_missing.append(p)

# 2) 未登记第一方文档
claimed=set(claim_paths)
unregistered=[f for f in active_md if f not in claimed]
# 3) claim 路径不存在
claim_missing=[p for p in claim_paths if not os.path.exists(os.path.join(root,p))]
# 4) 重复动态事实权威:三动态源之外的文档不得声明"唯一权威";CURRENT 文档中权威域重叠检测
# 简化:统计 authority 含"唯一权威"的行,其 path 必须∈{CURRENT_STATUS,TASKS,台账}
dyn_auth=[]
for line in open(cm):
    if line.startswith("#") or line.startswith("path\t"): continue
    parts=line.rstrip("\n").split("\t")
    if len(parts)>3 and "唯一权威" in parts[3]:
        dyn_auth.append(parts[0])
allowed={"CURRENT_STATUS.md","TASKS.md","docs/world-model端到端Bug台账_给作者PR.md"}
dup_auth=[p for p in dyn_auth if p not in allowed]

print(f"broken_active_links={len(broken)}")
for b in broken[:20]: print("  BROKEN:",b)
print(f"unregistered_first_party_docs={len(unregistered)}")
for u in unregistered[:20]: print("  UNREG:",u)
print(f"claim_paths_missing_on_disk={len(claim_missing)}")
for c in claim_missing[:20]: print("  MISSING:",c)
print(f"duplicate_dynamic_authority={len(dup_auth)}")
for d in dup_auth[:20]: print("  DUPAUTH:",d)
print(f"lifecycle_missing={len(lifecycle_missing)}")
for l in lifecycle_missing[:20]: print("  NOLC:",l)
# --- 语义硬门:防已知 current 回归,非自然语言全量审查 ---
def readf(p):
    try: return open(p,encoding="utf-8",errors="replace").read()
    except OSError: return ""
sem=[]
cs=readf("CURRENT_STATUS.md")
for badstr in ("S2-FIX 施工中","C1 生成器","连续授权施工中","第二阶段治理施工中"):
    if badstr in cs: sem.append(f"CURRENT_STATUS 含过期串: {badstr}")
tk=readf("TASKS.md")
if "第二阶段治理施工中" in tk: sem.append("TASKS 含过期串: 第二阶段治理施工中")
bt=readf("接力棒_当前值班.md")
if "只做 R003-S2-FIX" in bt: sem.append("接力棒 含过期串: 只做 R003-S2-FIX")

# 当前路线和停点:三份状态文档必须同时承认 P0/P1,唯一当前施工项为 P1-2。
route=("P0","P1","P2","P3","P4")
pos=[cs.find(x) for x in route]
if any(x < 0 for x in pos) or pos != sorted(pos):
    sem.append("CURRENT_STATUS 未按 P0→P1→P2→P3→P4 固定顺序声明路线")
for nm,txt in (("CURRENT_STATUS",cs),("TASKS",tk),("接力棒",bt)):
    if "P0" not in txt or "P1" not in txt:
        sem.append(f"{nm} 未同时包含当前 P0/P1 阶段")
    if "P1-2" not in txt:
        sem.append(f"{nm} 未登记当前施工项 P1-2")
if not re.search(r'P1-1[^\n]{0,40}(完成|已恢复)', cs):
    sem.append("CURRENT_STATUS 未把 P1-1 登记为完成")
for token in ("ok=true","RRG","voxblox","adapter","FCU"):
    if token not in cs and token not in bt:
        sem.append(f"当前短闭环验收边界缺少 {token}")

# CURRENT 文档不得在 claim manifest 中以 '整档 ... CURRENT_CONSISTENT' 占位(要求逐主张)
cm_txt=readf("governance/claim_manifest.tsv")
for line in cm_txt.splitlines():
    if line.startswith("CURRENT_STATUS.md\t整档") and "CURRENT_CONSISTENT" in line:
        sem.append("claim: CURRENT_STATUS 仍为 '整档...CURRENT_CONSISTENT' 占位")
# 最小语义反例:同一文档不得既申请阶段又宣布同阶段完成。
_apply=re.compile(r"申请[^\n]{0,10}(放行|进入)[^\n]{0,6}(E0|E1|E2)")
_done=re.compile(r"(E0|E1|E2)[^\n]{0,6}(已完成|已收口|收口停点|执行完毕|已交付并|已放行并执行)")
for f in active_md:
    t=readf(f)
    applied={m.group(2) for m in _apply.finditer(t)}
    done={m.group(1) for m in _done.finditer(t)}
    conflict=sorted(applied & done)
    if conflict:
        sem.append(f"{f}: 同文档既申请放行/进入又宣布完成 阶段 {conflict}")

# 文档事实闭包
rd=readf("README.md")
cmt=readf("governance/claim_manifest.tsv"); bug=readf("docs/world-model端到端Bug台账_给作者PR.md")
# README 未历史化的"替换 frontier_lite"
for i,line in enumerate(rd.splitlines(),1):
    if "替换" in line and "frontier" in line and not any(w in line for w in ("非替换","历史","作废","并列","不指导")):
        sem.append(f"README:{i} 未历史化的'替换 frontier_lite'")
# 状态文档不得把治理主仓写成易过期的 main@<hex>;精确绑定看 manifest 头。
for nm,txt in (("CURRENT_STATUS",cs),("接力棒",bt)):
    if re.search(r'治理[^\n]{0,80}main@[`*]{0,2}[0-9a-f]{7,40}\b', txt):
        sem.append(f"{nm} 内嵌易过期精确 main HEAD(应引用 manifest 头)")
# 阶段升级门:P1 未关闭时,P2/P3/P4 不得写成正在施工或通过。
if not re.search(r'P1[^\n]{0,30}(进行中|未通过)', cs):
    sem.append("CURRENT_STATUS 未明确 P1 仍在进行中/未通过")
for stage in ("P2","P3","P4"):
    rows=[line for line in cs.splitlines() if re.match(rf'\| {stage}(?:\s|\||：)',line)]
    if not rows or not all("阻塞" in line for line in rows):
        sem.append(f"CURRENT_STATUS 未把 {stage} 阶段门保持为阻塞")

# 活跃 UNVERIFIED md 必须带历史/UNVERIFIED 标记(不得承担 current 权威)
for line in cmt.splitlines():
    p=line.split("\t")
    if len(p)>2 and p[0].endswith(".md") and p[2]=="UNVERIFIED":
        head="\n".join(readf(p[0]).splitlines()[:4])
        if "UNVERIFIED" not in head and "不构成当前施工指令" not in head:
            sem.append(f"UNVERIFIED 活跃文档缺历史标记: {p[0]}")
# 默认主线 6/3/3 与诊断臂 4/3/3 不得无分层混写。
for nm,txt in (("CURRENT_STATUS",cs),("Bug台账",bug)):
    for line in txt.splitlines():
        z=line.replace(" ","")
        if "6/3/3" in z and "4/3/3" in z and not any(w in line for w in ("分层","旁证","诊断臂")):
            sem.append(f"{nm} 默认主线6/3/3与诊断臂4/3/3混写未分层")
# claim manifest 章节引用闭包:CURRENT_STATUS 行引用的标题必须真实存在。
for line in cmt.splitlines():
    if line.startswith("CURRENT_STATUS.md\t"):
        sec=line.split("\t")[1]
        title=re.sub(r'^§[一二三四五六七八九十]+\s*','',sec)
        if title and title not in cs:
            sem.append(f"claim: CURRENT_STATUS 行引用不存在的章节: {sec}")
# CURRENT 行 last_verified_commit 不得早于文件最后变更 commit;HEAD 表示随本次 review commit 绑定。
for line in cmt.splitlines():
    p=line.rstrip("\n").split("\t")
    if line.startswith("#") or line.startswith("path\t") or len(p)<11: continue
    if p[2]!="CURRENT" or p[10] in ("HEAD","-",""): continue
    lastc=subprocess.run(["git","log","-1","--format=%H","--",p[0]],capture_output=True,text=True).stdout.strip()
    if not lastc: continue
    r=subprocess.run(["git","merge-base","--is-ancestor",lastc,p[10]],capture_output=True,text=True)
    if r.returncode!=0:
        sem.append(f"claim: {p[0]}({p[1]}) last_verified={p[10][:7]} 早于文件最后变更 {lastc[:7]}(时效失守)")
print(f"semantic_violations={len(sem)}")
for x in sem[:40]: print("  SEM:",x)

bad=len(broken)+len(unregistered)+len(claim_missing)+len(dup_auth)+len(lifecycle_missing)+len(sem)
sys.exit(1 if bad else 0)
