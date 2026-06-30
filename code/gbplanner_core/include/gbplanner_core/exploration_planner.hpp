#pragma once
#include "gbplanner_core/voxel_map_interface.hpp"
#include "gbplanner_core/ray_caster.hpp"
#include <vector>
#include <cmath>

namespace gbp {

// 一个候选目标(GBPlanner 局部规划:在机器人附近采样的候选点)
struct Candidate {
  Vec3 point;          // 候选目标点
  double heading = 0;  // 从机器人指向它的方向(rad)
  double gain = 0;     // 体积增益(m^3):站到这里能新看见多少未知空间
  double dist = 0;     // 到机器人的距离(m)
  double turn = 0;     // 相对当前朝向的转角(rad)
  double score = 0;    // 综合评分 = gain - k_dist*dist - k_turn*turn
  bool chosen = false; // 是否被选中
};

struct PlannerParams {
  int num_candidates = 16;  // 采样方向数
  double radius = 0.4;      // 候选点离机器人半径(m)
  double k_dist = 1.0;      // 距离惩罚权重
  double k_turn = 2.0;      // 转向惩罚权重
  SensorModel sensor;       // 传感器模型(算增益用)
};

// === GBPlanner 核心决策(对应 mentor md)===
// 在机器人周围采样候选目标点 → 对每个点用光线投射算"体积增益" → 减去距离/转向惩罚
// → 选评分最高、且落在已知空闲(可达避障)的候选。返回所有候选(含选中标记)。
inline std::vector<Candidate> planExploration(const VoxelMapInterface& map,
                                              const Vec3& robot, double robot_heading,
                                              const PlannerParams& p = PlannerParams{}) {
  std::vector<Candidate> cands;
  const double pi = 3.14159265358979323846;
  for (int i = 0; i < p.num_candidates; ++i) {
    double th = 2 * pi * i / p.num_candidates;
    Vec3 pt{robot.x + p.radius * std::cos(th), robot.y + p.radius * std::sin(th), robot.z};
    if (map.getState(pt) != VoxelState::Free) continue;  // 只接受可达的已知空闲点(避障)
    Candidate c;
    c.point = pt;
    c.heading = th;
    c.gain = computeVolumeGain(map, pt, p.sensor);  // 体积增益
    c.dist = p.radius;
    double dh = std::fabs(th - robot_heading);
    while (dh > pi) dh = 2 * pi - dh;
    c.turn = dh;
    c.score = c.gain - p.k_dist * c.dist - p.k_turn * c.turn;
    cands.push_back(c);
  }
  int best = -1;
  double bs = -1e18;
  for (size_t i = 0; i < cands.size(); ++i)
    if (cands[i].score > bs) { bs = cands[i].score; best = static_cast<int>(i); }
  if (best >= 0) cands[best].chosen = true;
  return cands;
}

}  // namespace gbp
