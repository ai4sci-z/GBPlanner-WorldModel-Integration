#!/usr/bin/env bash
# 活体量 /ap/tf 频率(飞控实际收外部里程计的话题)。容器一出现就量,量到 3 次为止。
set -o pipefail
got=0
for i in $(seq 1 60); do
  C=$(docker ps --format '{{.Names}}' | grep -iE 'baseline' | head -1)
  if [ -n "$C" ]; then
    echo "[$i] baseline 容器=$C ,量 /ap/tf 与 /ap/pose ..."
    docker exec "$C" bash -c 'source /opt/ros/jazzy/setup.bash 2>/dev/null; timeout 6 ros2 topic hz /ap/tf 2>/dev/null | grep -m1 average || echo "  /ap/tf: 无数据"; ' 2>/dev/null
    docker exec "$C" bash -c 'source /opt/ros/jazzy/setup.bash 2>/dev/null; ros2 topic list 2>/dev/null | grep -iE "ap/tf|tf$|external_nav|ap/pose" | head' 2>/dev/null
    got=$((got+1))
    [ "$got" -ge 3 ] && break
    sleep 6
  else
    sleep 2
  fi
done
[ "$got" -eq 0 ] && echo "没等到 baseline 容器"
echo "=== 探测结束 ==="
