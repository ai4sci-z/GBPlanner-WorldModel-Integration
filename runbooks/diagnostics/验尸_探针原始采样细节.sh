#!/bin/bash
set -u
D=$(ls -dt /home/ai4s/ws/world-model/artifacts/sim/exploration/*/ | head -1)
echo "run: $D"
python3 - "${D}summary.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
samples = d['metrics']['gate']['startup_readiness']['probe_semantics']['samples']
for k in sorted(samples):
    v = samples[k]
    print(f"{k}\n    ok={v.get('ok')} kind={v.get('failure_kind')} rc={v.get('return_code')} has_stdout={v.get('has_stdout')} state={v.get('parsed_state')}")
PYEOF
