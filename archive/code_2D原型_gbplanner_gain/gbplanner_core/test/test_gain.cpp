// gbplanner_core 单元测试:验证光线投射与体积增益的关键行为。
#include "gbplanner_core/dense_voxel_map.hpp"
#include "gbplanner_core/ray_caster.hpp"
#include <cstdio>

using namespace gbp;

static int failures = 0;
#define CHECK(cond, msg)                         \
  do {                                           \
    if (!(cond)) { std::printf("FAIL: %s\n", msg); ++failures; } \
    else { std::printf("ok  : %s\n", msg); }     \
  } while (0)

int main() {
  // 1) 全未知地图:一条射线应能数到若干未知体素
  DenseVoxelMap m(Vec3{0, 0, 0}, 1.0, 10, 1, 1, VoxelState::Unknown);
  int n = castRayUnknownCount(m, Vec3{0.5, 0.5, 0.5}, Vec3{1, 0, 0}, 9.0);
  CHECK(n > 0, "全未知:射线能数到未知体素");
  CHECK(n <= 10, "未知计数不超过地图范围");

  // 2) 在 x=5 处放一个占据体素:射线应在此停下,未知计数应少于无墙时
  DenseVoxelMap m2(Vec3{0, 0, 0}, 1.0, 10, 1, 1, VoxelState::Unknown);
  m2.setVoxel(5, 0, 0, VoxelState::Occupied);
  int n2 = castRayUnknownCount(m2, Vec3{0.5, 0.5, 0.5}, Vec3{1, 0, 0}, 9.0);
  CHECK(n2 > 0, "墙前仍能看到未知体素");
  CHECK(n2 < n, "遇占据体素射线停止 -> 未知计数减少");

  // 3) 体积增益:开阔环境 > 一侧被墙挡住
  DenseVoxelMap big(Vec3{-2, -2, 0}, 0.1, 40, 40, 20, VoxelState::Unknown);
  double g_open = computeVolumeGain(big, Vec3{0, 0, 1.0});
  big.fillBox(Vec3{0.3, -2, 0}, Vec3{0.4, 2, 2}, VoxelState::Occupied);
  double g_wall = computeVolumeGain(big, Vec3{0, 0, 1.0});
  CHECK(g_open > 0.0, "开阔环境体积增益为正");
  CHECK(g_wall < g_open, "加墙后体积增益下降");

  std::printf("\n%s (failures=%d)\n",
              failures == 0 ? "ALL TESTS PASSED" : "TESTS FAILED", failures);
  return failures == 0 ? 0 : 1;
}
