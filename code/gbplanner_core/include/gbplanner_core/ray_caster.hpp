#pragma once
#include "gbplanner_core/voxel_map_interface.hpp"
#include <climits>
#include <cmath>

namespace gbp {

// === 光线投射(ray casting)===
// 从 origin 沿 dir 走,数沿途"未知"体素的个数,遇到"已占据"体素就停。
// 这是体积增益的最小单元:一条视线能新看见多少未知空间。
inline int castRayUnknownCount(const VoxelMapInterface& map, const Vec3& origin,
                               const Vec3& dir, double max_range) {
  const double res = map.resolution();
  const double step = res * 0.5;  // 半体素步长,避免漏掉体素
  Vec3 d = dir.normalized();
  int unknown = 0;
  long li = LONG_MIN, lj = LONG_MIN, lk = LONG_MIN;  // 记录上一个体素,避免重复计数
  for (double t = step; t <= max_range; t += step) {
    Vec3 p = origin + d * t;
    if (!map.inBounds(p)) break;
    long i = static_cast<long>(std::floor(p.x / res));
    long j = static_cast<long>(std::floor(p.y / res));
    long k = static_cast<long>(std::floor(p.z / res));
    if (i == li && j == lj && k == lk) continue;  // 还在同一个体素里
    li = i; lj = j; lk = k;
    VoxelState s = map.getState(p);
    if (s == VoxelState::Occupied) break;     // 被障碍挡住,视线到此为止
    if (s == VoxelState::Unknown) ++unknown;  // 看见一个未知体素
  }
  return unknown;
}

// 简化版传感器模型(决定向哪些方向发射线)
struct SensorModel {
  double max_range = 5.0;   // 最大视距(米)
  int h_rays = 36;          // 水平方向射线数(每 10°)
  int v_rays = 9;           // 垂直方向射线数
  double v_fov_deg = 60.0;  // 垂直视场角(±30°)
};

// === 体积增益(VolumeGain)===
// 从一个视点向四周发很多条射线,累加能看见的未知体素数,再乘以单体素体积。
// 这就是 GBPlanner 选路的核心评分:哪条路看见的未知空间多就更值得去。
inline double computeVolumeGain(const VoxelMapInterface& map,
                                const Vec3& viewpoint,
                                const SensorModel& sensor = SensorModel{}) {
  const double pi = 3.14159265358979323846;
  long unknown_total = 0;
  for (int h = 0; h < sensor.h_rays; ++h) {
    double az = 2 * pi * h / sensor.h_rays;  // 方位角 0..2π
    for (int v = 0; v < sensor.v_rays; ++v) {
      double frac = (sensor.v_rays <= 1) ? 0.0 : double(v) / (sensor.v_rays - 1);
      double el = (-sensor.v_fov_deg / 2 + sensor.v_fov_deg * frac) * pi / 180.0;  // 俯仰角
      Vec3 dir{std::cos(el) * std::cos(az), std::cos(el) * std::sin(az), std::sin(el)};
      unknown_total += castRayUnknownCount(map, viewpoint, dir, sensor.max_range);
    }
  }
  double vox_vol = map.resolution() * map.resolution() * map.resolution();
  return static_cast<double>(unknown_total) * vox_vol;  // 可见未知体积(m^3)
}

}  // namespace gbp
