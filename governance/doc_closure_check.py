#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 文档闭包机器检查:五指标全 0 才通过。仅只读,不改文件。"""
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
# --- A5 语义硬门:只防本次已知回归(过期 current 串),非自然语言审查 ---
def readf(p):
    try: return open(p,encoding="utf-8",errors="replace").read()
    except OSError: return ""
sem=[]
cs=readf("CURRENT_STATUS.md")
for badstr in ("S2-FIX 施工中","C1 生成器","连续授权施工中"):
    if badstr in cs: sem.append(f"CURRENT_STATUS 含过期串: {badstr}")
if "WP303" not in cs or "实现" not in cs:
    sem.append("CURRENT_STATUS 唯一下一动作未含 'WP303 实现'")
tk=readf("TASKS.md")
if "第二阶段治理施工中" in tk: sem.append("TASKS 含过期串: 第二阶段治理施工中")
bt=readf("接力棒_当前值班.md")
if "只做 R003-S2-FIX" in bt: sem.append("接力棒 含过期串: 只做 R003-S2-FIX")
# CURRENT 文档不得在 claim manifest 中以 '整档 ... CURRENT_CONSISTENT' 占位(要求逐主张)
cm_txt=readf("governance/claim_manifest.tsv")
for line in cm_txt.splitlines():
    if line.startswith("CURRENT_STATUS.md\t整档") and "CURRENT_CONSISTENT" in line:
        sem.append("claim: CURRENT_STATUS 仍为 '整档...CURRENT_CONSISTENT' 占位")
# A6 最小语义反例:同一文档不得既"申请放行/进入 阶段X"又"宣布 X 已完成/收口/执行完毕"(顶部申请/底部完成冲突)
_apply=re.compile(r"申请[^\n]{0,10}(放行|进入)[^\n]{0,6}(E0|E1|E2)")
_done=re.compile(r"(E0|E1|E2)[^\n]{0,6}(已完成|已收口|收口停点|执行完毕|已交付并|已放行并执行)")
for f in active_md:
    t=readf(f)
    applied={m.group(2) for m in _apply.finditer(t)}
    done={m.group(1) for m in _done.finditer(t)}
    conflict=sorted(applied & done)
    if conflict:
        sem.append(f"{f}: 同文档既申请放行/进入又宣布完成 阶段 {conflict}")

# A7 D5 机械门(R003-WP304-E0-CORRECT-2):文档事实闭包
tk=readf("TASKS.md"); bt=readf("接力棒_当前值班.md"); rd=readf("README.md")
cmt=readf("governance/claim_manifest.tsv"); bug=readf("docs/world-model端到端Bug台账_给作者PR.md")
# 1 三状态文档当前工作包一致(均含 WP304)
for nm,txt in (("CURRENT_STATUS",cs),("TASKS",tk),("接力棒",bt)):
    if "WP304" not in txt: sem.append(f"{nm} 未含当前工作包 WP304")
# 2 README 未历史化的"替换 frontier_lite"
for i,line in enumerate(rd.splitlines(),1):
    if "替换" in line and "frontier" in line and not any(w in line for w in ("非替换","历史","作废","并列","不指导")):
        sem.append(f"README:{i} 未历史化的'替换 frontier_lite'")
# 3 claim manifest 当前阶段不得仍是 WP303 施工点
if "施工点=WP303" in cmt and "WP303 已收口" not in cmt:
    sem.append("claim: 当前施工点仍写 WP303")
# 4 状态文档不得内嵌易过期精确 main HEAD(main@<hex>)
for nm,txt in (("CURRENT_STATUS",cs),("接力棒",bt)):
    if re.search(r'main@[`*]{0,2}[0-9a-f]{7,40}\b', txt):
        sem.append(f"{nm} 内嵌易过期精确 main HEAD(应引用 manifest 头)")
# 5 阶段状态升级门:WP305 不得写成通过;WP306 三项不得写成完成;WP307/308 不得写成已开始
if re.search(r'WP305[^\n]{0,16}(通过|完成|CLOSED|已关闭)', cs): sem.append("CURRENT_STATUS 把 WP305 写成通过/完成")
if re.search(r'WP30[78][^\n]{0,16}(已开始|进行中|运行中|10/10 通过)', cs): sem.append("CURRENT_STATUS 把 WP307/308 写成已开始")
# 6 "E0/运行时埋点已完成"违规(运行时埋点未实现);逐行 + 否定守卫(排除"不得称…已完成"这类禁止句)
for nm,txt in (("CURRENT_STATUS",cs),("TASKS",tk),("接力棒",bt),("Bug台账",bug),("open1/README",readf("runbooks/world-model-jazzy/l0_hover/open1/README.md"))):
    for line in txt.splitlines():
        if any(x in line for x in ("E0 埋点已完成","运行时埋点已完成","运行时埋点已实现")):
            if not any(neg in line for neg in ("不得","未实现","尚未","禁止","非","不是","≠","不能")):
                sem.append(f"{nm} 违规:声称 E0/运行时埋点已完成")
# 7 活跃 UNVERIFIED md 必须带历史/UNVERIFIED 标记(不得承担 current 权威)
for line in cmt.splitlines():
    p=line.split("\t")
    if len(p)>2 and p[0].endswith(".md") and p[2]=="UNVERIFIED":
        head="\n".join(readf(p[0]).splitlines()[:4])
        if "UNVERIFIED" not in head and "不构成当前施工指令" not in head:
            sem.append(f"UNVERIFIED 活跃文档缺历史标记: {p[0]}")
# 8 默认主线 6/3/3 与诊断臂 4/3/3 混写(同行两组分母且未标分层/旁证/诊断臂)
for nm,txt in (("CURRENT_STATUS",cs),("Bug台账",bug)):
    for line in txt.splitlines():
        z=line.replace(" ","")
        if "6/3/3" in z and "4/3/3" in z and not any(w in line for w in ("分层","旁证","诊断臂")):
            sem.append(f"{nm} 默认主线6/3/3与诊断臂4/3/3混写未分层")
# A8 claim manifest 语义时效门(R003-WP304-E0-EVIDENCE-GATE-CORRECT 包C):
# 防"生成头/last_verified 卡死在历史 commit、章节引用失效、跨源结论矛盾"类语义陈旧
# 1 跨源矛盾:claim 写 "WP303 已收口" 而 CURRENT_STATUS 写 G5 PARTIAL/实现停点
if "WP303 已收口" in cmt and re.search(r'WP303[^\n]{0,60}(PARTIAL|实现停点)', cs):
    sem.append("claim: 'WP303 已收口' 与 CURRENT_STATUS 'WP303 实现停点/PARTIAL' 跨源矛盾")
# 2 下一步矛盾:claim 仍写 进入 E1 方案停点,而 CURRENT_STATUS 已是 E1 sidecar 实现(方案已交付)
if "E1 方案停点" in cmt and ("E1 sidecar 实现" in cs or "E1 观测方案已交付" in cs):
    sem.append("claim: 下一动作仍写 'E1 方案停点',与 CURRENT_STATUS 'E1 sidecar 实现' 矛盾")
# 3 章节引用闭包:CURRENT_STATUS 行引用的章节标题必须真实存在于正文
for line in cmt.splitlines():
    if line.startswith("CURRENT_STATUS.md\t"):
        sec=line.split("\t")[1]
        title=re.sub(r'^§[一二三四五六七八九十]+\s*','',sec)
        if title and title not in cs:
            sem.append(f"claim: CURRENT_STATUS 行引用不存在的章节: {sec}")
# 4 时效:CURRENT 行 last_verified_commit 不得早于该文件最后变更 commit(短/长 SHA 均可;无效 rev 失败关闭)
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
