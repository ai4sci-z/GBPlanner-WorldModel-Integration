#!/usr/bin/env bash
# GATE-0 宿主环境重建 —— 原生 Ubuntu 24.04(HANDOVER_LINUX.md §4 GATE-0)
#
#   sudo bash runbooks/migration/bootstrap_linux_gate0.sh
#
# 装: docker engine(官方源/清华镜像) + go(/usr/local/go,勿用发行版旧包) + native curl/git
# 宿主不装 ROS —— 全部容器化(HANDOVER §4)。
# 幂等: 已装的组件会跳过,可安全重跑。
set -euo pipefail

GO_VERSION="${GO_VERSION:-1.26.5}"          # 要求 ≥1.24
REAL_USER="${SUDO_USER:-$(id -un)}"
TUNA="https://mirrors.tuna.tsinghua.edu.cn"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m  ✅ %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "须用 sudo 运行"; exit 1; }

# ---------- 1. 基础包(snap curl 有沙箱限制,换 native) ----------
log "1/5 基础包: curl / git / ca-certificates"
apt-get update -qq
apt-get install -y -qq curl git ca-certificates gnupg lsb-release >/dev/null
ok "curl $(/usr/bin/curl --version | head -1 | cut -d' ' -f2) / git $(git --version | cut -d' ' -f3)"

# ---------- 2. docker engine ----------
if command -v docker >/dev/null 2>&1; then
  ok "docker 已存在,跳过: $(docker --version)"
else
  log "2/5 docker engine(清华镜像源)"
  install -m 0755 -d /etc/apt/keyrings
  /usr/bin/curl -fsSL "${TUNA}/docker-ce/linux/ubuntu/gpg" \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] ${TUNA}/docker-ce/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable
EOF
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
                        docker-buildx-plugin docker-compose-plugin >/dev/null
  systemctl enable --now docker
  ok "$(docker --version)"
fi

# docker 组(免 sudo 用 docker;生效需重新登录或 newgrp docker)
if id -nG "$REAL_USER" | grep -qw docker; then
  ok "用户 ${REAL_USER} 已在 docker 组"
else
  usermod -aG docker "$REAL_USER"
  ok "已把 ${REAL_USER} 加入 docker 组 —— 需重新登录或 newgrp docker 才生效"
fi

# ---------- 3. go ----------
CURRENT_GO="$(/usr/local/go/bin/go version 2>/dev/null | cut -d' ' -f3 || echo none)"
if [ "$CURRENT_GO" = "go${GO_VERSION}" ]; then
  ok "go${GO_VERSION} 已在 /usr/local/go,跳过"
else
  log "3/5 go ${GO_VERSION} → /usr/local/go"
  TARBALL="go${GO_VERSION}.linux-amd64.tar.gz"
  /usr/bin/curl -fL# -o "/tmp/${TARBALL}" "https://go.dev/dl/${TARBALL}"
  rm -rf /usr/local/go
  tar -C /usr/local -xzf "/tmp/${TARBALL}"
  rm -f "/tmp/${TARBALL}"
  ok "$(/usr/local/go/bin/go version)"
fi

# PATH(系统级,新 shell 生效)
if [ ! -f /etc/profile.d/go.sh ]; then
  cat > /etc/profile.d/go.sh <<'EOF'
export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin
EOF
  chmod 644 /etc/profile.d/go.sh
  ok "PATH 已写入 /etc/profile.d/go.sh"
fi
# 当前用户的 .bashrc 也加一条(非登录 shell 也能用)
USER_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
if ! grep -q '/usr/local/go/bin' "${USER_HOME}/.bashrc" 2>/dev/null; then
  echo 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin' >> "${USER_HOME}/.bashrc"
  ok "PATH 已追加到 ${REAL_USER} 的 .bashrc"
fi

# ---------- 4. docker 国内加速(可选,拉底图快) ----------
log "4/5 docker registry mirror"
if [ -f /etc/docker/daemon.json ]; then
  ok "/etc/docker/daemon.json 已存在,不覆盖(自行确认 mirror)"
else
  mkdir -p /etc/docker
  cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerproxy.net"
  ],
  "log-driver": "json-file",
  "log-opts": { "max-size": "100m", "max-file": "3" }
}
EOF
  systemctl restart docker
  ok "registry mirror 已配置"
fi

# ---------- 5. 验收门 ----------
log "5/5 GATE-0 验收"
FAIL=0
docker --version               || FAIL=1
docker info >/dev/null 2>&1 && ok "docker daemon 运行中" || { echo "  ❌ docker daemon 未运行"; FAIL=1; }
/usr/local/go/bin/go version   || FAIL=1
GO_MAJMIN="$(/usr/local/go/bin/go version | grep -oP 'go\K[0-9]+\.[0-9]+')"
awk -v v="$GO_MAJMIN" 'BEGIN{split(v,a,".");exit !(a[1]>1||(a[1]==1&&a[2]>=24))}' \
  && ok "go ${GO_MAJMIN} ≥ 1.24" || { echo "  ❌ go 版本低于 1.24"; FAIL=1; }

if [ "$FAIL" -eq 0 ]; then
  printf '\n\033[1;32m🎉 GATE-0 PASS\033[0m —— 下一步 GATE-1: docker pull ros:jazzy-ros-base\n'
  printf '   ⚠️  docker 组权限须重新登录(或 newgrp docker)才对当前 shell 生效\n\n'
else
  printf '\n\033[1;31m❌ GATE-0 FAIL\033[0m —— 见上方失败项\n\n'; exit 1
fi
