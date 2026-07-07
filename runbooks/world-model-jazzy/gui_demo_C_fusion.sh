#!/usr/bin/env bash
# GUI-C·GBPlanner-in-world-model 融合演示(=gui_demo_master.sh 的正名别名)
# 展示点:同一 world-model 仿真里,GBPlanner(经薄桥)驱动飞机;RViz(GBPlanner 视角)+
# Gazebo(世界视角)双窗;RViz 密度低于 GUI-A 属桥接 2Hz 限流的已知特性,非故障;
# 窗口只在 run 进行期(~6 分钟)有活动画面。
exec bash "$(dirname "$0")/gui_demo_master.sh"
