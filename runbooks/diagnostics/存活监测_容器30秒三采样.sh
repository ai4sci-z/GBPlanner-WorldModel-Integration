#!/bin/bash
set -u
docker rm -f repro-sensor >/dev/null 2>&1
docker run -d --name repro-sensor \
  -v /home/ai4s/ws/world-model:/workspace -w /workspace \
  navlab/gazebo-sensor:humble-latest \
  bash -lc 'source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && source /opt/navlab_sensor_ws/install/setup.bash && exec /opt/gazebo-sensor-venv/bin/python -m navlab.sim.gazebo_sensor.cli --runtime --log-file /tmp/gs.runtime.log' >/dev/null
for t in 10 20 30; do
  sleep 10
  echo "t=${t}s: $(docker ps -a --filter name=repro-sensor --format '{{.Status}}')"
done
echo "== 进程树(应有 bridge/driver/emulator 一家子) =="
docker exec repro-sensor ps -eo pid,comm 2>/dev/null | head -12
echo "== 最后日志 =="
docker logs repro-sensor 2>&1 | tail -3
docker rm -f repro-sensor >/dev/null 2>&1
