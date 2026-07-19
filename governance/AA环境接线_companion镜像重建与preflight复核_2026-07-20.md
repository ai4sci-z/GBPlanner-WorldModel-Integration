# A/A 环境接线:companion 镜像重建 + preflight 复核(2026-07-20)

> 性质:**冻结证据(EVIDENCE)**。状态权威=CURRENT_STATUS.md。
> 本文只记录"A/A 启动前接缝"的闭合证据:①companion 镜像按候选基线 HEAD 重建;
> ②preflight(sourced+全计划+真实镜像 digest)复核 READY。
> **不改判任何门;E1 A/A 实验本体未启动,仍待负责人明确启动指令。**

## 1. 现场基线(执行时点)

| 项 | 值 |
|---|---|
| main HEAD | `bcbca492e138db3e197816ef14cbcf2d5745d452`(工作树净) |
| world-model HEAD | `9a1ce95c56e2901aad062e31c9d4a8006474b0fc`(冻结只读,工作树净;FUTURE_CANDIDATE) |
| 执行环境 | 宿主 Ubuntu 24.04,单 system docker daemon;ROS2 jazzy 按方案A pins(governance/ros2_host_env_pins_2026-07-20.md) |

## 2. companion 镜像重建(接缝①)

- 命令(= runbooks/world-model-jazzy/build_all_jazzy_native.sh 的 companion 条目,构建上下文=world-model 仓根,构建不修改仓库):

```bash
cd /home/ai4s/projects/world-model   # HEAD=9a1ce95c56e2,git status --porcelain 为空(构建前断言)
DOCKER_BUILDKIT=1 docker build \
  --build-arg ROS_DISTRO=jazzy --build-arg INFRA_TAG=jazzy-latest \
  --target navlab-companion \
  -f docker/images/runtime/companion.Dockerfile \
  -t navlab/companion:jazzy-9a1ce95c56e2 .
```

- 结果:**rc=0**;真产物核验(不信退出码):`docker images` 精确匹配
  `navlab/companion:jazzy-9a1ce95c56e2` 存在。
- 镜像 ID(manifest list digest):`sha256:2aab049e96f01fbe1e95bb7e218fa2612d15dc7e33424db97f6a0848d0486b99`
- 构建日志:`~/build-logs-jazzy/companion-9a1ce95c56e2.log`(宿主,不入仓)。
- **诚实注记**:全部层 CACHED——companion 构建上下文内容与上一版逐层一致
  (750032a→9a1ce95 的改动在 orchestration Go 侧,不进 companion 镜像内容)。
  本次实质=把镜像内容绑定到 tag_policy(distro-git-commit)要求的新 HEAD tag,
  消除"live run 按 HEAD 找 tag 找不到镜像"的接缝。这不是行为验证。

## 3. preflight 复核 READY(接缝②)

- 命令(operator shell 先 `source /opt/ros/jazzy/setup.bash`):

```bash
cd runbooks/world-model-jazzy/l0_hover/open1
python3 aa_preflight.py --input <plan.json> --output <pf.json>
```

- 结果:**rc=0,preflight_status=READY,18/18 全 PASS,acceptance_eligible=true,
  failed_checks=[],owner_decisions_required=[]**。
- 与 2026-07-20 早间"可达 READY"结论的差异:本次 plan 的 `image_digests.companion`
  是**刚重建镜像的真实 digest**(sha256:2aab04…),不再是占位符——镜像接缝在 preflight
  证据里真实闭合。
- 关键 PASS 摘录:main/wm SHA 匹配;双工作树净;宿主 rclpy/std_msgs sourced 可导入;
  readiness_topic=/mavlink_external_nav/status(权威登记表内);双域=7 且一致;
  容器身份=runtime/service_handles.json+负责人批准;evidence_contract=wp304.telemetry.v1;
  OFF×2+ON×2 配对冻结字段全一致;real_validation_claims 全 false。

### 3.1 plan 取值的诚实边界(计划级,非运行级)

- `config_hash` / `runtime_plan_hash` = 显式占位符 `PLAN_PENDING_REAL_RUN`:二者只能由
  真实 run 产生;preflight 本轮只验 presence。**E1 正式启动时必须以真实值重跑 preflight。**
- `identity_wait_sec=135.75` = 由唯一来源 `batch_lifecycle.identity_wait_sec()` 函数实算
  (startup=100 + duration=25 + teardown=0.5 + gap=0.25 + margin=10;预算值为计划级代表值,
  E1 实际预算以负责人启动指令为准,启动时以实际 argv 重新推导)。
- `main_commit=bcbca492e138` 为执行时点值;本轮收口提交会前移 main HEAD,
  故**该 pf.json 不能复用于 E1 启动——启动时以当时 HEAD 重新生成 plan 并重跑 preflight**。
- plan/输出 JSON 原件见附录 A/B(全文冻结于本文档,不另存散件)。

## 4. 结论与不改判声明

- 接力棒所列 A/A 启动三前置:source /opt/ros/jazzy ✅(pins 落档)、
  companion 镜像重建 jazzy-9a1ce95c56e2 ✅(本文 §2)、preflight READY ✅(本文 §3)。
- **唯一待决=负责人明确下达 A/A 启动指令(OFF×2+ON×2)。**
- 未启动任何仿真/容器/负载;world-model 仓未做任何修改;不改判 G5/G6/G7/G8 任何门;
  真实仿真行为验收仍归 WP307。

## 附录 A:plan JSON(输入原件)

```json
{
 "main_commit": "bcbca492e138db3e197816ef14cbcf2d5745d452",
 "baseline_class": "FUTURE_CANDIDATE",
 "sidecar_backend": "real",
 "ros_readiness_topic": "/mavlink_external_nav/status",
 "ros_extnav_topic": "/external_nav/status",
 "sidecar_ros_domain": "7",
 "system_ros_domain": "7",
 "container_identity_source": "runtime/service_handles.json",
 "image_digests": {"companion": "sha256:2aab049e96f01fbe1e95bb7e218fa2612d15dc7e33424db97f6a0848d0486b99"},
 "runtime_plan_hash": "PLAN_PENDING_REAL_RUN",
 "identity_wait_sec": 135.75,
 "identity_wait_budgets": {"startup": 100.0, "duration": 25.0, "teardown": 0.5,
                           "gap": 0.25, "margin": 10.0,
                           "source": "batch_lifecycle.identity_wait_sec"},
 "evidence_contract_version": "wp304.telemetry.v1",
 "pair_plan": [
  {"off": {"run_id": "aa-plan-r1", "telemetry_mode": "OFF", "baseline_class": "FUTURE_CANDIDATE",
           "main_commit": "bcbca492e138db3e197816ef14cbcf2d5745d452",
           "world_model_commit": "9a1ce95c56e2901aad062e31c9d4a8006474b0fc",
           "image_digests": "sha256:2aab049e96f01fbe1e95bb7e218fa2612d15dc7e33424db97f6a0848d0486b99",
           "config_hash": "PLAN_PENDING_REAL_RUN", "task_id": "hover", "map_id": "iris_maze",
           "timeout_sec": 1500, "ros_domain_id": "7",
           "container_identity_source": "runtime/service_handles.json", "evidence_state": "COMPLETE"},
   "on": {"run_id": "aa-plan-r2", "telemetry_mode": "ON", "…其余字段": "与 off 逐字段相同"}},
  {"off": {"run_id": "aa-plan-r3", "telemetry_mode": "OFF", "…": "同上"},
   "on": {"run_id": "aa-plan-r4", "telemetry_mode": "ON", "…": "同上"}}
 ],
 "real_validation_claims": {"real_ros_graph": false, "real_docker_chain": false},
 "owner_approvals": {"ros_env_plan": true, "readiness_topic": true,
                     "container_identity_upstream": true}
}
```

(pair_plan 四条 run 记录除 run_id/telemetry_mode 外逐字段相同;冻结字段一致性由
preflight `pair_plan_frozen_fields_match=PASS` 机器判定,非人工声称。)

## 附录 B:preflight 输出(关键字段原件)

```json
{
 "preflight_status": "READY",
 "acceptance_eligible": true,
 "failed_checks": [],
 "owner_decisions_required": [],
 "warnings": [],
 "generated_at": "2026-07-19T22:09:38Z",
 "main_commit": "bcbca492e138db3e197816ef14cbcf2d5745d452",
 "world_model_commit": "9a1ce95c56e2901aad062e31c9d4a8006474b0fc",
 "checks": "18 项全 PASS(main_sha_match / wm_sha_matches_baseline_class / main_worktree_clean / wm_worktree_clean / host_rclpy_available / host_std_msgs_available / readiness_topic_decided_and_verified / extnav_topic_verified / ros_domains_configured / ros_domains_equal / container_identity_live_pipeline / image_digests_present / runtime_plan_hash_present / identity_wait_budget_derived / evidence_contract_current / sample_plan_off2_on2 / pair_plan_frozen_fields_match / no_fake_real_validation_claims)"
}
```
