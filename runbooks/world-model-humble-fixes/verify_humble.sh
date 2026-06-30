#!/usr/bin/env bash
LOG=/home/ai4s/navlab_build.log
echo "=== 实际存在的 humble 镜像 ==="
docker images --format '{{.Repository}}:{{.Tag}}' | grep 'navlab.*humble' | sort
echo ""
echo "=== 逐个核对(9个) ==="
ok=0; fail=0
for img in ros-base ardupilot-sitl mavlink-router gazebo-headless fast-lio companion slam-cartographer gazebo-sensor official-baseline; do
  # 镜像实际存在?
  if docker images --format '{{.Repository}}' | grep -q "navlab/${img}$"; then
    echo "  ✅ $img (镜像存在)"; ok=$((ok+1))
  else
    echo "  ❌ $img (镜像缺失)"; fail=$((fail+1))
  fi
done
echo ""
echo "总计: 成功 $ok / 失败 $fail (应为 9/0)"
echo ""
echo "=== 构建结尾 ==="
tail -2 "$LOG"
