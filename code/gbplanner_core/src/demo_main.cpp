// 离线演示:不依赖 ROS、不依赖仿真,手搓一个合成 3D 地图,
// 计算"体积增益",直观展示 GBPlanner 的核心思想。
#include "gbplanner_core/dense_voxel_map.hpp"
#include "gbplanner_core/ray_caster.hpp"
#include <cstdio>

using namespace gbp;

int main() {
  // 造一个 4m × 4m × 2m 的地图(分辨率 0.1m),整体初始为"未知"。
  DenseVoxelMap map(Vec3{-2, -2, 0}, 0.1, 40, 40, 20, VoxelState::Unknown);
  // 机器人周围一小块设为"空闲"(已探索区域)。
  map.fillBox(Vec3{-0.5, -0.5, 0.4}, Vec3{0.5, 0.5, 1.2}, VoxelState::Free);

  Vec3 viewpoint{0, 0, 0.8};

  // 1) 开阔未知环境下的体积增益
  double g_open = computeVolumeGain(map, viewpoint);
  std::printf("开阔未知环境的体积增益 = %.3f m^3\n", g_open);

  // 2) 在 x 正方向竖一堵墙(已占据),挡住该方向视线,增益应下降
  map.fillBox(Vec3{1.0, -2, 0}, Vec3{1.1, 2, 2}, VoxelState::Occupied);
  double g_wall = computeVolumeGain(map, viewpoint);
  std::printf("一侧加墙后的体积增益   = %.3f m^3\n", g_wall);

  std::printf("结论:加墙后增益下降 = %s\n",
              (g_wall < g_open ? "是(符合预期:被挡住就看不见那侧未知空间)"
                               : "否(异常!)"));
  return 0;
}
