#!/usr/bin/env bash
# GATE-2: jazzy 全栈 9 镜像重建 —— 原生 Linux 版(HANDOVER_LINUX.md §4 GATE-2)
#
#   sg docker -c 'bash runbooks/world-model-jazzy/build_all_jazzy_native.sh'
#
# 相对旧 build_jazzy.sh(WSL 版)修正三处缺陷:
#   1. 路径参数化(旧: REPO=/home/ai4s/ws/world-model 写死)
#   2. slam 的镜像名是 navlab/slam-cartographer,不是 navlab/slam(旧脚本按 IMG 名推导 → 打错 tag)
#   3. 多阶段 Dockerfile 必须传 --target(旧脚本完全没传 → 可能构建错 stage)
#   4. gazebo-sensor 改用 runbooks 里打过 ydlidar 补丁的 Dockerfile(in-repo 那份在 jazzy 编不过)
#   注: official-baseline 的代理**必须保留**——曾以为是旧 WSL 遗留而去掉,实测直连克隆
#       ArduPilot 在 ~90s 被掐(GnuTLS -110),加回 7897 代理才过。
#
# 镜像定义真源头 = ${WM}/orchestration/sim/config.toml [navlab.images.*]
# 铁律(施工指引 §五): 只认 docker images 真产物,不信退出码。
set -o pipefail

WM="${WM:-/home/ai4s/projects/world-model}"
GBP="${GBP:-/home/ai4s/projects/GBPlanner-WorldModel-Integration}"
DISTRO=jazzy
LOGDIR="${LOGDIR:-${HOME}/build-logs-jazzy}"
# official-baseline 要从 GitHub 克隆 ArduPilot 全家桶(大仓),直连实测在 ~90s 被掐
# (GnuTLS recv error -110)。走本机 Clash 混合端口。设 PROXY= 可关掉。
PROXY="${PROXY:-http://127.0.0.1:7897}"
NO_PROXY_HOSTS=localhost,127.0.0.1,mirrors.aliyun.com,packages.ros.org,packages.osrfoundation.org,archive.ubuntu.com,security.ubuntu.com

cd "$WM" || { echo "CD_FAIL: $WM"; exit 9; }
mkdir -p "$LOGDIR"
export DOCKER_BUILDKIT=1

# companion 的 tag_policy=distro-git-commit → tag 绑定 world-model 的 HEAD。
# ⚠️ 建完后若再动 HEAD,companion 必须重建,否则运行时找不到镜像。
COMMIT="$(git rev-parse --short=12 HEAD)"
echo "world-model HEAD = ${COMMIT}  (companion tag 绑定此值)"

# name|group|dockerfile|target|repository|tag|needs_proxy   —— ros-base 必须第一(其余 FROM 它)
#
# ⚠️ gazebo-sensor 用的是 runbooks 里打过补丁的 Dockerfile,不是 world-model in-repo 那份:
#    上游 ydlidar 用 declare_parameter("port") 无默认值重载,Galactic+ 的 rclcpp 已移除
#    → in-repo 版在 jazzy 上必编译失败(实测 2026-07-13 重现)。补丁 = 26 处 sed 补默认值
#    (语义不变)+ 一条 guard(改完不许有残留)。除该补丁块外与 in-repo 版逐行相同。
IMAGES=(
  "ros-base|base|docker/images/base/ros-base.Dockerfile||navlab/ros-base|${DISTRO}-latest|"
  "ardupilot-sitl|infra|docker/images/infra/ardupilot-sitl.Dockerfile||navlab/ardupilot-sitl|${DISTRO}-latest|"
  "mavlink-router|infra|docker/images/infra/mavlink-router.Dockerfile||navlab/mavlink-router|${DISTRO}-latest|"
  "fast-lio|infra|docker/images/infra/fast-lio.Dockerfile||navlab/fast-lio|${DISTRO}-latest|"
  "gazebo-headless|infra|docker/images/infra/gazebo-headless.Dockerfile||navlab/gazebo-headless|${DISTRO}-latest|"
  "slam-cartographer|runtime|docker/images/runtime/slam.Dockerfile|navlab-slam-cartographer|navlab/slam-cartographer|${DISTRO}-latest|"
  "gazebo-sensor|runtime|${GBP}/runbooks/world-model-jazzy/gazebo-sensor-jazzy.Dockerfile|navlab-gazebo-sensor|navlab/gazebo-sensor|${DISTRO}-latest|"
  "companion|runtime|docker/images/runtime/companion.Dockerfile|navlab-companion|navlab/companion|${DISTRO}-${COMMIT}|"
  "official-baseline|runtime|docker/images/runtime/official-baseline.Dockerfile|navlab-official-baseline|navlab/official-baseline|${DISTRO}-latest|proxy"
)

PASS=(); FAIL=()
START_ALL=$(date +%s)

for entry in "${IMAGES[@]}"; do
  IFS='|' read -r NAME GROUP DF TARGET REPOSITORY TAG NEEDS_PROXY <<< "$entry"
  IMAGE="${REPOSITORY}:${TAG}"
  LOG="${LOGDIR}/${NAME}.log"

  # 幂等: 已存在就跳过(重跑不浪费)
  if docker images --format '{{.Repository}}:{{.Tag}}' | grep -qx "${IMAGE}"; then
    echo "⏭️  SKIP ${NAME} (已存在 ${IMAGE})"; PASS+=("$NAME"); continue
  fi

  EXTRA_ARGS=()
  [ -n "$TARGET" ] && EXTRA_ARGS+=(--target "$TARGET")
  if [ "$NEEDS_PROXY" = "proxy" ] && [ -n "$PROXY" ]; then
    EXTRA_ARGS+=(--network=host
                 --build-arg HTTP_PROXY="$PROXY"
                 --build-arg HTTPS_PROXY="$PROXY"
                 --build-arg NO_PROXY="$NO_PROXY_HOSTS")
  fi

  echo ""
  echo "=== BUILD ${NAME} → ${IMAGE} $(date '+%H:%M:%S') ==="
  START=$(date +%s)
  docker build \
    --build-arg ROS_DISTRO="${DISTRO}" \
    --build-arg INFRA_TAG="${DISTRO}-latest" \
    "${EXTRA_ARGS[@]}" \
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
