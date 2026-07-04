# 无人机世界模型项目文档

这个目录只保留当前主线需要的文档。当前重点不是旧的接口验收，也不是直接跳到 hover 演示，而是先按官方基线建立真实闭环标准：

- 官方 ArduPilot ROS2/Gazebo/Cartographer baseline
- NavLab world/model/sensor 接入官方或官方等价机制
- 无 GPS 真实 SLAM feedback
- FCU 状态机、唯一 setpoint owner 和真实悬停
- MCAP rosbag 和 Foxglove 回放验收

## 主导航

### 室内无 GPS 主线

- `docs/scenarios/indoor/navlab_master_roadmap.md`: 总 roadmap，定义 P0-P13 顺序和完成标准
- `docs/scenarios/indoor/navlab_p0_official_baseline_design.md`: P0 官方基线验收设计
- `docs/scenarios/indoor/todos/P0_official_baseline_todo.md`: P0 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p1_official_maze_x2_design.md`: P1 官方 maze + NavLab X2 雷达接入设计
- `docs/scenarios/indoor/todos/P1_official_maze_x2_todo.md`: P1 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p2_rangefinder_imu_design.md`: P2 下视 rangefinder 与 IMU 机制验收设计
- `docs/scenarios/indoor/todos/P2_rangefinder_imu_todo.md`: P2 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p3_slam_backend_quality_design.md`: P3 SLAM backend 质量验收设计
- `docs/scenarios/indoor/todos/P3_slam_backend_quality_todo.md`: P3 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p4_fcu_state_machine_design.md`: P4 FCU 状态机和唯一控制器设计
- `docs/scenarios/indoor/todos/P4_fcu_state_machine_todo.md`: P4 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p5_frame_contract_design.md`: P5 Frame contract 自动验收设计
- `docs/scenarios/indoor/todos/P5_frame_contract_todo.md`: P5 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p6_slam_hover_gate_design.md`: P6 真实 SLAM hover gate 设计
- `docs/scenarios/indoor/todos/P6_slam_hover_gate_todo.md`: P6 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p7_official_maze_motion_gate_design.md`: P7 官方 maze 小范围运动 gate 设计
- `docs/scenarios/indoor/todos/P7_official_maze_motion_gate_todo.md`: P7 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p8_official_maze_exploration_design.md`: P8 官方 maze 探索任务设计
- `docs/scenarios/indoor/todos/P8_official_maze_exploration_todo.md`: P8 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p9_official_maze_overlay_replay_design.md`: P9 官方 maze 底图叠加与 Foxglove-lite 回放设计
- `docs/scenarios/indoor/todos/P9_official_maze_overlay_replay_todo.md`: P9 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p10_body_fixed_lidar_scan_integrity_design.md`: P10 机体固连 lidar 姿态补偿与 scan integrity gate 设计
- `docs/scenarios/indoor/todos/P10_body_fixed_lidar_scan_integrity_todo.md`: P10 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p11_bounded_2d_lidar_scan_stabilization_design.md`: P11 有界 2D lidar 姿态稳定化设计
- `docs/scenarios/indoor/todos/P11_bounded_2d_lidar_scan_stabilization_todo.md`: P11 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p12_airframe_disturbance_scan_robustness_design.md`: P12 机体扰动下的 2D lidar / SLAM 水平复原鲁棒性设计
- `docs/scenarios/indoor/todos/P12_airframe_disturbance_scan_robustness_todo.md`: P12 TODO 和验收标准
- `docs/scenarios/indoor/navlab_p13_nav2_indoor_navigation_design.md`: P13 Nav2 室内导航与主动探索设计
- `docs/scenarios/indoor/todos/P13_nav2_indoor_navigation_todo.md`: P13 TODO 和验收标准
- `docs/scenarios/indoor/navlab_unified_landing_sequence_design.md`: hover/P8/P12 统一降落流程设计
- `docs/scenarios/indoor/navlab_real_flight_preflight_doctor_design.md`: 真机飞行前 real preflight doctor 设计
- `docs/scenarios/indoor/navlab_real_prepare_and_task_doctor_design.md`: 真机 prepare / task doctor 分层设计
- `docs/scenarios/indoor/navlab_real_orchestration_rust_review.md`: Rust real orchestration 静态 review 结果和真机安全修复建议
- `docs/scenarios/indoor/navlab_ardupilot_externalnav_reading.md`: ArduPilot Cartographer / VIO / GPS-NonGPS / Guided / arm 文档阅读
- `docs/scenarios/indoor/navlab_real_motor_debug_design.md`: 真机无桨 motor-debug 的 Guided / ExternalNav / arm-disarm 设计
- `docs/scenarios/indoor/navlab_real_pre_takeoff_development_confirmation.md`: 真机起飞前开发确认文档
- `docs/scenarios/indoor/todos/real_flight_preflight_doctor_todo.md`: 真机飞行前 real preflight doctor TODO 和验收标准
- `docs/scenarios/indoor/todos/real_prepare_and_task_doctor_todo.md`: 真机 prepare / task doctor TODO 和验收标准
- `docs/scenarios/indoor/todos/unified_landing_sequence_todo.md`: 统一降落流程 TODO 和两阶段验收标准
- `docs/scenarios/indoor/navlab_ardupilot_ros2_official_alignment.md`: 当前系统与官方路线的对齐审计
- `docs/scenarios/indoor/navlab_reference_projects_analysis.md`: 四个参考仓库的综合分析和改进建议
- `docs/scenarios/indoor/navlab_cartographer_real_machine_tuning.md`: Cartographer 真机调参记录口径

### 仿真和传感器

- `docs/sim/README.md`: Gazebo 仿真和传感器主线说明
- `docs/sim/todo.md`: 仿真路线 TODO
- `docs/sim/x2_lidar_simulation_design.md`: X2 虚拟串口协议级仿真设计
- `docs/sim/x2_lidar_protocol_todo.md`: X2 协议级仿真 TODO 和验收标准
- `docs/sim/examples/*.yaml`: 历史 mission 输入样例，仅作参考

### 工程重构

- `../contracts/README.md`: `navlab` runtime 与 `orchestration` 之间的语言无关协议入口
- `docs/general/lab_env_service_refactor_todo.md`: Python 服务边界、目录重构和测试拆分记录
- `docs/general/orchestration_runtime_backend_refactor_todo.md`: orchestration runtime backend 抽象和迁移 TODO
- `docs/general/orchestration_runtime_backend_guide.md`: DockerBackend / ProcessBackend 使用说明和排障口径
- `docs/general/orchestration_runtime_mode_real_vs_sim_design.md`: simulation/real runtime mode 分流设计
- `docs/general/orchestration_config_precedence_split_design.md`: orchestration 配置优先级和按 mode/task 拆分设计
- `docs/general/orchestration_runtime_backend_inventory.md`: runtime backend 迁移清单和当前样板
- `docs/general/orchestration_legacy_helper_deep_split_todo.md`: legacy helper 深拆和最终删除 TODO
- `docs/general/orchestration_sim_python_parity_audit.md`: Go sim 迁移旧 Python orchestration 的 SLAM/topic/frame/truth parity 审计
- `docs/general/navlab_real_sim_package_boundary_design.md`: `navlab.real` / `navlab.sim` / `navlab.common` 包边界设计
- `docs/general/orchestration_sim_tui_monitor_design.md`: Go sim TUI monitor 设计，覆盖 live 运行监控和 artifact replay

## 推荐阅读顺序

1. `docs/scenarios/indoor/navlab_master_roadmap.md`
2. `docs/scenarios/indoor/navlab_p0_official_baseline_design.md`
3. `docs/scenarios/indoor/todos/P0_official_baseline_todo.md`
4. `docs/scenarios/indoor/navlab_p1_official_maze_x2_design.md`
5. `docs/scenarios/indoor/todos/P1_official_maze_x2_todo.md`
6. `docs/scenarios/indoor/navlab_p2_rangefinder_imu_design.md`
7. `docs/scenarios/indoor/todos/P2_rangefinder_imu_todo.md`
8. `docs/scenarios/indoor/navlab_p3_slam_backend_quality_design.md`
9. `docs/scenarios/indoor/todos/P3_slam_backend_quality_todo.md`
10. `docs/scenarios/indoor/navlab_p4_fcu_state_machine_design.md`
11. `docs/scenarios/indoor/todos/P4_fcu_state_machine_todo.md`
12. `docs/scenarios/indoor/navlab_p5_frame_contract_design.md`
13. `docs/scenarios/indoor/todos/P5_frame_contract_todo.md`
14. `docs/scenarios/indoor/navlab_p6_slam_hover_gate_design.md`
15. `docs/scenarios/indoor/todos/P6_slam_hover_gate_todo.md`
16. `docs/scenarios/indoor/navlab_p7_official_maze_motion_gate_design.md`
17. `docs/scenarios/indoor/todos/P7_official_maze_motion_gate_todo.md`
18. `docs/scenarios/indoor/navlab_p8_official_maze_exploration_design.md`
19. `docs/scenarios/indoor/todos/P8_official_maze_exploration_todo.md`
20. `docs/scenarios/indoor/navlab_p9_official_maze_overlay_replay_design.md`
21. `docs/scenarios/indoor/todos/P9_official_maze_overlay_replay_todo.md`
22. `docs/scenarios/indoor/navlab_p10_body_fixed_lidar_scan_integrity_design.md`
23. `docs/scenarios/indoor/todos/P10_body_fixed_lidar_scan_integrity_todo.md`
24. `docs/scenarios/indoor/navlab_p11_bounded_2d_lidar_scan_stabilization_design.md`
25. `docs/scenarios/indoor/todos/P11_bounded_2d_lidar_scan_stabilization_todo.md`
26. `docs/scenarios/indoor/navlab_p12_airframe_disturbance_scan_robustness_design.md`
27. `docs/scenarios/indoor/todos/P12_airframe_disturbance_scan_robustness_todo.md`
28. `docs/scenarios/indoor/navlab_p13_nav2_indoor_navigation_design.md`
29. `docs/scenarios/indoor/todos/P13_nav2_indoor_navigation_todo.md`
30. `docs/scenarios/indoor/navlab_unified_landing_sequence_design.md`
31. `docs/scenarios/indoor/navlab_real_flight_preflight_doctor_design.md`
32. `docs/scenarios/indoor/navlab_real_prepare_and_task_doctor_design.md`
33. `docs/scenarios/indoor/navlab_real_orchestration_rust_review.md`
34. `docs/scenarios/indoor/navlab_real_pre_takeoff_development_confirmation.md`
35. `docs/scenarios/indoor/todos/real_flight_preflight_doctor_todo.md`
36. `docs/scenarios/indoor/todos/real_prepare_and_task_doctor_todo.md`
37. `docs/scenarios/indoor/todos/unified_landing_sequence_todo.md`
38. `docs/scenarios/indoor/navlab_ardupilot_ros2_official_alignment.md`
39. `docs/scenarios/indoor/navlab_reference_projects_analysis.md`
40. `docs/sim/x2_lidar_simulation_design.md`
41. `docs/sim/x2_lidar_protocol_todo.md`
42. `docs/general/lab_env_service_refactor_todo.md`
43. `docs/general/orchestration_runtime_backend_refactor_todo.md`
44. `docs/general/orchestration_runtime_backend_guide.md`
45. `docs/general/orchestration_runtime_mode_real_vs_sim_design.md`
46. `docs/general/orchestration_config_precedence_split_design.md`
47. `docs/general/orchestration_legacy_helper_deep_split_todo.md`
48. `docs/general/orchestration_sim_python_parity_audit.md`
49. `docs/general/navlab_real_sim_package_boundary_design.md`
50. `docs/general/orchestration_sim_tui_monitor_design.md`
51. `contracts/README.md`

## 当前目录结构

```text
docs/
  README.md
  decisions.md
  general/
    lab_env_service_refactor_todo.md
    orchestration_runtime_backend_refactor_todo.md
    orchestration_runtime_backend_guide.md
    orchestration_runtime_backend_inventory.md
    orchestration_runtime_mode_real_vs_sim_design.md
    orchestration_config_precedence_split_design.md
    orchestration_legacy_helper_deep_split_todo.md
    orchestration_sim_python_parity_audit.md
    navlab_real_sim_package_boundary_design.md
    orchestration_sim_tui_monitor_design.md
  scenarios/
    indoor/
      navlab_master_roadmap.md
      navlab_p0_official_baseline_design.md
      navlab_p1_official_maze_x2_design.md
      navlab_p2_rangefinder_imu_design.md
      navlab_p3_slam_backend_quality_design.md
      navlab_p4_fcu_state_machine_design.md
      navlab_p5_frame_contract_design.md
      navlab_p6_slam_hover_gate_design.md
      navlab_p7_official_maze_motion_gate_design.md
      navlab_p8_official_maze_exploration_design.md
      navlab_p9_official_maze_overlay_replay_design.md
      navlab_p10_body_fixed_lidar_scan_integrity_design.md
      navlab_p11_bounded_2d_lidar_scan_stabilization_design.md
      navlab_p12_airframe_disturbance_scan_robustness_design.md
      navlab_p13_nav2_indoor_navigation_design.md
      navlab_unified_landing_sequence_design.md
      navlab_real_flight_preflight_doctor_design.md
      navlab_real_prepare_and_task_doctor_design.md
      navlab_real_orchestration_rust_review.md
      navlab_ardupilot_externalnav_reading.md
      navlab_real_motor_debug_design.md
      navlab_real_pre_takeoff_development_confirmation.md
      navlab_ardupilot_ros2_official_alignment.md
      navlab_reference_projects_analysis.md
      navlab_cartographer_real_machine_tuning.md
      todos/
        P0_official_baseline_todo.md
        P1_official_maze_x2_todo.md
        P2_rangefinder_imu_todo.md
        P3_slam_backend_quality_todo.md
        P4_fcu_state_machine_todo.md
        P5_frame_contract_todo.md
        P6_slam_hover_gate_todo.md
        P7_official_maze_motion_gate_todo.md
        P8_official_maze_exploration_todo.md
        P9_official_maze_overlay_replay_todo.md
        P10_body_fixed_lidar_scan_integrity_todo.md
        P11_bounded_2d_lidar_scan_stabilization_todo.md
        P12_airframe_disturbance_scan_robustness_todo.md
        P13_nav2_indoor_navigation_todo.md
        real_flight_preflight_doctor_todo.md
        real_prepare_and_task_doctor_todo.md
        unified_landing_sequence_todo.md
  sim/
    README.md
    todo.md
    x2_lidar_simulation_design.md
    x2_lidar_protocol_todo.md
    examples/
      blocked_by_stop_guard.yaml
      straight_line_demo.yaml
```

## 当前约束

- Gazebo 只负责世界、物理和传感器。
- SITL 等价于真实飞控。
- companion 等价于机载计算盒子。
- P0 必须先证明官方 `/ap/*` DDS baseline，而不是直接把自定义 MAVLink bridge 当作完成标准。
- SLAM 必须消费真实等价的传感器输入，例如 `/scan`、`/imu` 和 SLAM 自己需要的
  frame/state；Gazebo `/odometry`、Gazebo pose TF、seed map 和 official maze map
  默认只能 diagnostic/review，不能作为 SLAM/Nav2/ExternalNav/controller 输入。
- ExternalNav 验收必须来自真实 SLAM `/slam/odom` 或官方等价 ExternalNav 路线。
- Gazebo truth 只能用于诊断和误差对照。
- 上游代码不能直接 `set_pose` 移动 Gazebo 无人机。
- 每次 acceptance 必须输出 MCAP rosbag，方便 Foxglove 回放。
