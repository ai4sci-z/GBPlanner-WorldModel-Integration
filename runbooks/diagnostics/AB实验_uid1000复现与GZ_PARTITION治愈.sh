#!/bin/bash
# 终局二连:A=忠实uid1000复刻(应复现gz瘫痪);B=+GZ_PARTITION(应治愈)
set -u
CY='<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
D=$(ls -dt /home/ai4s/ws/world-model/artifacts/sim/exploration/*/ | head -1)

run_case() {
  local name="$1"; shift
  docker rm -f manual-baseline >/dev/null 2>&1
  docker run -d --name manual-baseline --net=host --user 1000:1000 \
    -e HOME=/tmp -e ROS_LOG_DIR=/tmp/navlab-ros-logs -e XDG_CACHE_HOME=/tmp/navlab-cache \
    -e SESSION_ID=test123 -e CYCLONEDDS_URI="$CY" -e ROS_DOMAIN_ID=0 -e DDS_DOMAIN_ID=0 \
    -e DDS_ENABLE=1 -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e PYTHONPATH=/workspace \
    "$@" \
    -v /home/ai4s/ws/world-model:/workspace -w /workspace \
    -v "${D}runtime/config/model_overlay.sdf":/opt/navlab_official_ws/install/ardupilot_gz_description/share/ardupilot_gz_description/models/iris_with_lidar/model.sdf:ro \
    navlab/official-baseline:humble-latest \
    bash -lc "$(cat /home/ai4s/baseline_cmd.sh)" >/dev/null
  sleep 32
  local st=$(docker ps -a --filter name=manual-baseline --format '{{.Status}}' | head -1)
  local ml=$(docker exec --user 1000:1000 -e HOME=/tmp manual-baseline bash -c 'timeout 8 gz model --list 2>&1 | grep -c iris' 2>/dev/null || echo exec失败)
  local rq=$(docker logs manual-baseline 2>&1 | grep -cE 'Requesting list of world names')
  echo "[$name] 容器:$st | iris可见=$ml | create重试次数=$rq"
  docker rm -f manual-baseline >/dev/null 2>&1
}
run_case "A:忠实uid1000复刻"
run_case "B:+GZ_PARTITION=navlab" -e GZ_PARTITION=navlab
