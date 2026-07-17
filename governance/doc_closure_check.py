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
bad=len(broken)+len(unregistered)+len(claim_missing)+len(dup_auth)+len(lifecycle_missing)
sys.exit(1 if bad else 0)
