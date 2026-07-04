#!/bin/bash
# 守株待兔:容器一出现就 inspect 存档
set -u
for i in $(seq 1 90); do
  if docker ps --format '{{.Names}}' | grep -q '^navlab-official-baseline$'; then
    docker inspect navlab-official-baseline > /home/ai4s/inspect_orch.json 2>/dev/null && echo CAPTURED && exit 0
  fi
  sleep 2
done
echo TIMEOUT_NO_CONTAINER
