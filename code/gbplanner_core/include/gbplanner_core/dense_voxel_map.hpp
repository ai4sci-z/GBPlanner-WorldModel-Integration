#pragma once
#include "gbplanner_core/voxel_map_interface.hpp"
#include <cmath>
#include <vector>

namespace gbp {

// 一个简单的稠密 3D 栅格地图,用于离线测试/演示。
// (真实集成时会换成 ROS2 建图前端 octomap/nvblox,但接口一致,算法不用改。)
class DenseVoxelMap : public VoxelMapInterface {
public:
  DenseVoxelMap(const Vec3& origin, double res, int nx, int ny, int nz,
                VoxelState fill = VoxelState::Unknown)
      : origin_(origin), res_(res), nx_(nx), ny_(ny), nz_(nz),
        data_(static_cast<size_t>(nx) * ny * nz, fill) {}

  double resolution() const override { return res_; }

  bool inBounds(const Vec3& p) const override {
    int i, j, k;
    return toIndex(p, i, j, k);
  }

  VoxelState getState(const Vec3& p) const override {
    int i, j, k;
    if (!toIndex(p, i, j, k)) return VoxelState::Unknown;  // 界外按未知处理
    return data_[idx(i, j, k)];
  }

  // 测试用:按体素整数坐标直接设状态
  void setVoxel(int i, int j, int k, VoxelState s) {
    if (valid(i, j, k)) data_[idx(i, j, k)] = s;
  }

  // 测试用:把一个轴对齐长方体区域(世界坐标)设为某状态
  void fillBox(const Vec3& lo, const Vec3& hi, VoxelState s) {
    for (int i = 0; i < nx_; ++i)
      for (int j = 0; j < ny_; ++j)
        for (int k = 0; k < nz_; ++k) {
          Vec3 c = center(i, j, k);
          if (c.x >= lo.x && c.x <= hi.x && c.y >= lo.y && c.y <= hi.y &&
              c.z >= lo.z && c.z <= hi.z)
            data_[idx(i, j, k)] = s;
        }
  }

private:
  Vec3 origin_;
  double res_;
  int nx_, ny_, nz_;
  std::vector<VoxelState> data_;

  size_t idx(int i, int j, int k) const {
    return (static_cast<size_t>(k) * ny_ + j) * nx_ + i;
  }
  bool valid(int i, int j, int k) const {
    return i >= 0 && i < nx_ && j >= 0 && j < ny_ && k >= 0 && k < nz_;
  }
  bool toIndex(const Vec3& p, int& i, int& j, int& k) const {
    i = static_cast<int>(std::floor((p.x - origin_.x) / res_));
    j = static_cast<int>(std::floor((p.y - origin_.y) / res_));
    k = static_cast<int>(std::floor((p.z - origin_.z) / res_));
    return valid(i, j, k);
  }
  Vec3 center(int i, int j, int k) const {
    return {origin_.x + (i + 0.5) * res_, origin_.y + (j + 0.5) * res_,
            origin_.z + (k + 0.5) * res_};
  }
};

}  // namespace gbp
