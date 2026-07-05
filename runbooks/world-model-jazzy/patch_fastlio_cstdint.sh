#!/usr/bin/env bash
# jazzy/GCC13 修复:Livox-SDK2 头文件用 uintN_t 未 #include <cstdint> → cmake 加 -include cstdint 全局注入。
# 向后兼容(humble/GCC11 无害)。改 in-repo Dockerfile,进 PR。
set -euo pipefail
DF=/home/ai4s/ws/world-model/docker/images/infra/fast-lio.Dockerfile
echo "=== 改前 ==="; grep -n 'cmake \.\.' "$DF"
sed -i 's@&& cmake \.\. \\@\&\& cmake .. -DCMAKE_CXX_FLAGS="-include cstdint" \\@' "$DF"
echo "=== 改后 ==="; grep -n 'cmake \.\.' "$DF"
