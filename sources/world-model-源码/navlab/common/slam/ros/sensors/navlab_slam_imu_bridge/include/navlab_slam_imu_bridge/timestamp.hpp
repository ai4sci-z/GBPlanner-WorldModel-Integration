#pragma once

#include <algorithm>
#include <cstdint>
#include <optional>

namespace navlab_slam_imu_bridge {

inline int64_t monotonic_output_stamp_nanoseconds(
    int64_t candidate_ns, const std::optional<int64_t> &previous_output_ns) {
  if (!previous_output_ns.has_value()) {
    return candidate_ns;
  }
  return std::max(candidate_ns, previous_output_ns.value() + 1);
}

}  // namespace navlab_slam_imu_bridge
