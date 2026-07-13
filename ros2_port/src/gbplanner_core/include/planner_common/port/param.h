#pragma once
// ros::param::get shim for the ROS-free gbplanner core (M3).
//
// The core's param loaders (params.cpp, random_sampler.cpp,
// geofence_manager.cpp, adaptive_obb.cpp) all funnel through
// ros::param::get(name, out). This shim keeps those ~150 call sites intact:
// the ROS2 node shell (M4) or a unit test fills the registry first
// (pshim::param::set), then the loaders read from it.
#include <any>
#include <map>
#include <string>

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
  const T* v = std::any_cast<T>(&it->second);
  if (v == nullptr) return false;  // wrong type stored
  out = *v;
  return true;
}

inline void clear() { registry().clear(); }

}  // namespace param
}  // namespace pshim
