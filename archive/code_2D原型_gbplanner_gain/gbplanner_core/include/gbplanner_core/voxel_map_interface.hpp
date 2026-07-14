#pragma once
#include "gbplanner_core/types.hpp"

namespace gbp {

// 地图抽象接口:算法只通过这个接口查地图,不关心底层是 voxblox / octomap / 合成地图。
// 这是跨越两道"错配"的关键解耦点:
//   - 错配1(ROS1↔ROS2):核心算法不依赖任何 ROS,接口由外壳实现。
//   - 错配2(voxblox 只支持 ROS1):换成 ROS2 的建图库时,只需重新实现这个接口。
class VoxelMapInterface {
public:
  virtual ~VoxelMapInterface() = default;
  // 查询某世界坐标点所在体素的状态(未知/空闲/已占据)
  virtual VoxelState getState(const Vec3& p) const = 0;
  // 体素边长(米)
  virtual double resolution() const = 0;
  // 点是否在地图范围内
  virtual bool inBounds(const Vec3& p) const = 0;
};

}  // namespace gbp
