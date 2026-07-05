#!/usr/bin/env bash
# jazzy 单镜像构建器(直用 BuildKit，因编排器经典 builder 不支持 RUN --mount → 会假成功)
# 用法: build_jazzy.sh <infra|runtime> <image-name> [dockerfile-override]
# 铁律：只认 docker images 真产物，不信退出码/harness "OK"。
set -o pipefail
GROUP="$1"; IMG="$2"; DFOVR="$3"
if [ -z "$GROUP" ] || [ -z "$IMG" ]; then echo "usage: build_jazzy.sh <infra|runtime> <image> [dockerfile]"; exit 2; fi
REPO=/home/ai4s/ws/world-model
cd "$REPO" || { echo "CD_FAIL"; exit 9; }
export DOCKER_BUILDKIT=1
DF="${DFOVR:-docker/images/${GROUP}/${IMG}.Dockerfile}"
TAG="navlab/${IMG}:jazzy-latest"
LOG=/home/ai4s/build_jazzy_${IMG}.log
echo "=== BUILD START ${GROUP}/${IMG} -> ${TAG} $(date) df=${DF} ===" | tee "$LOG"

PROXY_ARGS=()
if [ "$IMG" = "official-baseline" ]; then
  PROXY_ARGS=(--network=host \
    --build-arg HTTP_PROXY=http://127.0.0.1:7897 \
    --build-arg HTTPS_PROXY=http://127.0.0.1:7897 \
    --build-arg NO_PROXY=localhost,127.0.0.1,mirrors.aliyun.com,packages.ros.org,packages.osrfoundation.org,archive.ubuntu.com,security.ubuntu.com)
fi

docker build "${PROXY_ARGS[@]}" \
  --build-arg INFRA_TAG=jazzy-latest \
  --build-arg ROS_DISTRO=jazzy \
  -f "$DF" -t "$TAG" . 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
echo "=== docker build rc=${RC} ===" | tee -a "$LOG"
if docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${TAG}$"; then
  echo "IMAGE_EXISTS=YES ${TAG}" | tee -a "$LOG"
else
  echo "IMAGE_EXISTS=NO ${TAG}" | tee -a "$LOG"; RC=1
fi
echo "=== BUILD END ${IMG} rc=${RC} $(date) ===" | tee -a "$LOG"
exit "$RC"
