#!/usr/bin/env bash
# GATE-2: jazzy 全栈 9 镜像重建 —— 原生 Linux 版(HANDOVER_LINUX.md §4 GATE-2)
#
#   sg docker -c 'bash runbooks/world-model-jazzy/build_all_jazzy_native.sh'
#
# 相对旧 build_jazzy.sh(WSL 版)修正三处缺陷:
#   1. 路径参数化(旧: REPO=/home/ai4s/ws/world-model 写死)
#   2. slam 的镜像名是 navlab/slam-cartographer,不是 navlab/slam(旧脚本按 IMG 名推导 → 打错 tag)
#   3. 多阶段 Dockerfile 必须传 --target(旧脚本完全没传 → 可能构建错 stage)
#   另: 去掉 official-baseline 的 127.0.0.1:7897 代理(那是旧 WSL 的 Clash;本机直连可达)
#
# 镜像定义真源头 = ${WM}/orchestration/sim/config.toml [navlab.images.*]
# 铁律(施工指引 §五): 只认 docker images 真产物,不信退出码。
set -o pipefail

WM="${WM:-/home/ai4s/projects/world-model}"
DISTRO=jazzy
LOGDIR="${LOGDIR:-${HOME}/build-logs-jazzy}"

cd "$WM" || { echo "CD_FAIL: $WM"; exit 9; }
mkdir -p "$LOGDIR"
export DOCKER_BUILDKIT=1

# companion 的 tag_policy=distro-git-commit → tag 绑定 world-model 的 HEAD。
# ⚠️ 建完后若再动 HEAD,companion 必须重建,否则运行时找不到镜像。
COMMIT="$(git rev-parse --short=12 HEAD)"
echo "world-model HEAD = ${COMMIT}  (companion tag 绑定此值)"

# name|group|dockerfile|target|repository|tag        —— ros-base 必须第一(其余 FROM 它)
IMAGES=(
  "ros-base|base|docker/images/base/ros-base.Dockerfile||navlab/ros-base|${DISTRO}-latest"
  "ardupilot-sitl|infra|docker/images/infra/ardupilot-sitl.Dockerfile||navlab/ardupilot-sitl|${DISTRO}-latest"
  "mavlink-router|infra|docker/images/infra/mavlink-router.Dockerfile||navlab/mavlink-router|${DISTRO}-latest"
  "fast-lio|infra|docker/images/infra/fast-lio.Dockerfile||navlab/fast-lio|${DISTRO}-latest"
  "gazebo-headless|infra|docker/images/infra/gazebo-headless.Dockerfile||navlab/gazebo-headless|${DISTRO}-latest"
  "slam-cartographer|runtime|docker/images/runtime/slam.Dockerfile|navlab-slam-cartographer|navlab/slam-cartographer|${DISTRO}-latest"
  "gazebo-sensor|runtime|docker/images/runtime/gazebo-sensor.Dockerfile|navlab-gazebo-sensor|navlab/gazebo-sensor|${DISTRO}-latest"
  "companion|runtime|docker/images/runtime/companion.Dockerfile|navlab-companion|navlab/companion|${DISTRO}-${COMMIT}"
  "official-baseline|runtime|docker/images/runtime/official-baseline.Dockerfile|navlab-official-baseline|navlab/official-baseline|${DISTRO}-latest"
)

PASS=(); FAIL=()
START_ALL=$(date +%s)

for entry in "${IMAGES[@]}"; do
  IFS='|' read -r NAME GROUP DF TARGET REPOSITORY TAG <<< "$entry"
  IMAGE="${REPOSITORY}:${TAG}"
  LOG="${LOGDIR}/${NAME}.log"

  # 幂等: 已存在就跳过(重跑不浪费)
  if docker images --format '{{.Repository}}:{{.Tag}}' | grep -qx "${IMAGE}"; then
    echo "⏭️  SKIP ${NAME} (已存在 ${IMAGE})"; PASS+=("$NAME"); continue
  fi

  TARGET_ARGS=()
  [ -n "$TARGET" ] && TARGET_ARGS=(--target "$TARGET")

  echo ""
  echo "=== BUILD ${NAME} → ${IMAGE} $(date '+%H:%M:%S') ==="
  START=$(date +%s)
  docker build \
    --build-arg ROS_DISTRO="${DISTRO}" \
    --build-arg INFRA_TAG="${DISTRO}-latest" \
    "${TARGET_ARGS[@]}" \
    -f "$DF" -t "$IMAGE" . > "$LOG" 2>&1
  RC=$?
  DUR=$(( $(date +%s) - START ))

  # 真产物核验(不信退出码)
  if docker images --format '{{.Repository}}:{{.Tag}}' | grep -qx "${IMAGE}"; then
    SIZE=$(docker images --format '{{.Size}}' "$IMAGE" | head -1)
    echo "✅ ${NAME} OK  ${SIZE}  ${DUR}s"
    PASS+=("$NAME")
  else
    echo "❌ ${NAME} FAIL (rc=${RC}, ${DUR}s) —— 末 20 行:"
    tail -20 "$LOG" | sed 's/^/     /'
    FAIL+=("$NAME")
    # ros-base 是所有镜像的基底,它挂了后面全没意义
    [ "$NAME" = "ros-base" ] && { echo "🛑 ros-base 失败,中止"; break; }
  fi
done

echo ""
echo "================ GATE-2 汇总 ($(( ($(date +%s) - START_ALL) / 60 )) 分钟) ================"
echo "✅ PASS ${#PASS[@]}/9: ${PASS[*]}"
[ ${#FAIL[@]} -gt 0 ] && echo "❌ FAIL ${#FAIL[@]}/9: ${FAIL[*]}  (日志: ${LOGDIR}/)"
echo ""
docker images | grep -E 'navlab/' | sort
echo ""
if [ ${#FAIL[@]} -eq 0 ] && [ ${#PASS[@]} -eq 9 ]; then
  echo "🎉 GATE-2 PASS —— 9/9 jazzy 镜像齐"
else
  echo "⚠️  GATE-2 未达成 (${#PASS[@]}/9)"; exit 1
fi
