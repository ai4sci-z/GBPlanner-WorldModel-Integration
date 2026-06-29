#pragma once
#include <cmath>

namespace gbp {

// 三维向量(位置/方向通用)
struct Vec3 {
  double x{0}, y{0}, z{0};
  Vec3() = default;
  Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}
  Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
  Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
  Vec3 operator*(double s) const { return {x * s, y * s, z * s}; }
  double norm() const { return std::sqrt(x * x + y * y + z * z); }
  Vec3 normalized() const {
    double n = norm();
    return n > 1e-9 ? Vec3{x / n, y / n, z / n} : Vec3{0, 0, 0};
  }
};

// 体素三态:未知 / 空闲 / 已占据 —— GBPlanner 探索的根基就是去"看见未知"
enum class VoxelState { Unknown, Free, Occupied };

}  // namespace gbp
