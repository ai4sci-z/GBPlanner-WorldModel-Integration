#!/usr/bin/env bash
# 查 exploration_probe 判定源码:code 20 条件、strategy 是否要求匹配 spec
CLEAN=/home/ai4s/ws-clean/world-model
echo "=== 定位 exploration probe 源 ==="
grep -rln "ExplorationStatusTopic" "$CLEAN/orchestration/sim/internal" | head -5
for f in $(grep -rln "ExplorationStatusTopic" "$CLEAN/orchestration/sim/internal" | head -5); do
  echo "---- $f ----"
  grep -n "Strategy\|strategy\|ok\|accepted\|code\|exit\|20" "$f" | head -40
done
echo "=== 4c 实际 probe 输出(判定字段) ==="
RUNDIR=$(ls -td "$CLEAN"/artifacts/sim/exploration/*/ | head -1)
python3 -c "
import json
d=json.load(open('$RUNDIR/probes/exploration_probe.json'))
def walk(o,p=''):
    if isinstance(o,dict):
        for k,v in o.items():
            if isinstance(v,(dict,list)): walk(v,p+'.'+str(k))
            else:
                kl=str(k).lower()
                if any(t in kl for t in ('ok','strategy','claim','accepted','path','blocker','status','reason','code','pass','fail')):
                    print(p+'.'+str(k),'=',v)
    elif isinstance(o,list):
        for i,v in enumerate(o): walk(v,'%s[%d]'%(p,i))
walk(d)" | head -40
