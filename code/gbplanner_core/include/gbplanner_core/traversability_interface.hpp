#pragma once
#include "gbplanner_core/types.hpp"

namespace gbp {

// 可通行性抽象接口:判断某点能否通行、某段路径是否无碰撞。
// 真实集成时由 ROS2 外壳依据地图/可通行性分析实现;离线测试可用简单实现。
class TraversabilityInterface {
public:
  virtual ~TraversabilityInterface() = default;
  virtual bool isTraversable(const Vec3& p) const = 0;
  virtual bool isPathClear(const Vec3& a, const Vec3& b) const = 0;
};

}  // namespace gbp
