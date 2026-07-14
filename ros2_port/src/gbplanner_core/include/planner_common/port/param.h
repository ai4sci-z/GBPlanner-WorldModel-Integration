#pragma once
// ros::param::get shim for the ROS-free gbplanner core (M3).
//
// The core's param loaders (params.cpp, random_sampler.cpp,
// geofence_manager.cpp, adaptive_obb.cpp) all funnel through
// ros::param::get(name, out). This shim keeps those ~150 call sites intact:
// the ROS2 node shell (M4) or a unit test fills the registry first
// (pshim::param::set), then the loaders read from it.
#include <any>
#include <cstdint>
#include <map>
#include <string>
#include <type_traits>
#include <vector>

namespace pshim {
namespace param {

inline std::map<std::string, std::any>& registry() {
  static std::map<std::string, std::any> reg;
  return reg;
}

template <typename T>
inline void set(const std::string& name, const T& value) {
  registry()[name] = value;
}

template <typename T>
inline bool get(const std::string& name, T& out) {
  const auto it = registry().find(name);
  if (it == registry().end()) return false;
  if (const T* v = std::any_cast<T>(&it->second)) {
    out = *v;
    return true;
  }
  // Numeric tolerance: the ROS2 shell stores YAML integers as int64_t and
  // reals as double; the vendored loaders ask for int/float/double/bool.
  if constexpr (std::is_arithmetic_v<T>) {
    if (const int64_t* v = std::any_cast<int64_t>(&it->second)) {
      out = static_cast<T>(*v);
      return true;
    }
    if (const double* v = std::any_cast<double>(&it->second)) {
      out = static_cast<T>(*v);
      return true;
    }
    if (const int* v = std::any_cast<int>(&it->second)) {
      out = static_cast<T>(*v);
      return true;
    }
    if (const bool* v = std::any_cast<bool>(&it->second)) {
      out = static_cast<T>(*v);
      return true;
    }
  }
  if constexpr (std::is_same_v<T, std::vector<double>>) {
    if (const auto* v =
            std::any_cast<std::vector<int64_t>>(&it->second)) {
      out.assign(v->begin(), v->end());
      return true;
    }
  }
  return false;  // wrong type stored
}

inline void clear() { registry().clear(); }

}  // namespace param
}  // namespace pshim
