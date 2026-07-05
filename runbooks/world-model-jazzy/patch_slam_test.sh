#!/usr/bin/env bash
# 清 80c0fa8 的测试欠账:SlamBackend.IMUTopic 默认已改 /navlab/slam/imu(防自吞回声),
# 测试仍断言旧值 /imu。更新断言 + 加回归守卫(imu_topic 不得再等于桥 source /imu)。
set -euo pipefail
F=/home/ai4s/ws/world-model/orchestration/sim/internal/tasks/helpers/slam_test.go
python3 - "$F" << 'PYEOF'
import sys
p=sys.argv[1]; s=open(p).read()
s=s.replace("\t\t`imu_topic = '/imu'`,","\t\t`imu_topic = '/navlab/slam/imu'`,")
guard='''	if strings.Contains(text, `cartographer_odometry_topic = '/odometry'`) {'''
new_guard='''	if strings.Contains(text, `imu_topic = '/imu'`) {
		t.Fatalf("slam backend imu_topic must not equal the bridge source /imu (self-echo loop):\\n%s", text)
	}
	if strings.Contains(text, `cartographer_odometry_topic = '/odometry'`) {'''
s=s.replace(guard,new_guard)
open(p,"w").write(s)
print("slam_test patched")
PYEOF
cd /home/ai4s/ws/world-model/orchestration/sim
PATH=/usr/local/go/bin:/usr/bin:/bin go test ./internal/tasks/helpers/ 2>&1 | tail -3
