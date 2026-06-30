#!/usr/bin/env bash
# official-baseline humble 完整构建:含全部修复
#   ① ros-gz->ros-gzharmonic ② 去 --break-system-packages ③ host网+代理(大克隆稳)
#   ④ MICRO_ROS_AGENT_REF=humble(关键:用 Fast-CDR 1 兼容的 humble 分支,修 fastcdr v2 不兼容)
cd /home/ai4s/ws/world-model || exit 1
export DOCKER_BUILDKIT=1
SRC=docker/images/runtime/official-baseline.Dockerfile
DST=/home/ai4s/official-baseline-humble.Dockerfile
LOG=/home/ai4s/build_official5.log
sed -e 's/-ros-gz \\$/-ros-gzharmonic \\/' -e 's/--break-system-packages //g' "$SRC" > "$DST"
echo "BUILD official-baseline START $(date)" > "$LOG"
docker build --network=host \
  --build-arg HTTP_PROXY=http://127.0.0.1:7897 \
  --build-arg HTTPS_PROXY=http://127.0.0.1:7897 \
  --build-arg NO_PROXY=localhost,127.0.0.1,mirrors.aliyun.com,packages.ros.org,packages.osrfoundation.org,archive.ubuntu.com,security.ubuntu.com \
  --build-arg INFRA_TAG=humble-latest --build-arg ROS_DISTRO=humble \
  --build-arg MICRO_ROS_AGENT_REF=humble \
  -f "$DST" -t navlab/official-baseline:humble-latest . >> "$LOG" 2>&1
rc=$?
echo "OFFICIAL5_EXIT=$rc $(date)" >> "$LOG"
if docker images --format '{{.Repository}}:{{.Tag}}' | grep -q 'navlab/official-baseline:humble-latest'; then echo "IMAGE_EXISTS=YES" >> "$LOG"; else echo "IMAGE_EXISTS=NO" >> "$LOG"; fi
echo "DONE $(date)" >> "$LOG"
