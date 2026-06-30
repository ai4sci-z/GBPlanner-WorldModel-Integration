#!/usr/bin/env bash
cd /home/ai4s/ws/world-model || exit 1
export DOCKER_BUILDKIT=1
SRC=docker/images/runtime/official-baseline.Dockerfile
DST=/home/ai4s/official-baseline-humble.Dockerfile
LOG=/home/ai4s/build_official4.log
sed -e 's/-ros-gz \\$/-ros-gzharmonic \\/' -e 's/--break-system-packages //g' "$SRC" > "$DST"
echo "=== BUILD official-baseline (host-net + 代理,大克隆走clash更稳) START $(date) ===" > "$LOG"
# github 走代理;apt 的国内镜像保持直连(放 NO_PROXY)以免变慢
docker build --network=host \
  --build-arg HTTP_PROXY=http://127.0.0.1:7897 \
  --build-arg HTTPS_PROXY=http://127.0.0.1:7897 \
  --build-arg NO_PROXY=localhost,127.0.0.1,mirrors.aliyun.com,packages.ros.org,packages.osrfoundation.org,archive.ubuntu.com,security.ubuntu.com \
  --build-arg INFRA_TAG=humble-latest --build-arg ROS_DISTRO=humble \
  -f "$DST" -t navlab/official-baseline:humble-latest . >> "$LOG" 2>&1
rc=$?
echo "OFFICIAL4_EXIT=$rc $(date)" >> "$LOG"
if docker images --format '{{.Repository}}:{{.Tag}}' | grep -q 'navlab/official-baseline:humble-latest'; then echo "IMAGE_EXISTS=YES" >> "$LOG"; else echo "IMAGE_EXISTS=NO" >> "$LOG"; fi
echo "DONE $(date)" >> "$LOG"
