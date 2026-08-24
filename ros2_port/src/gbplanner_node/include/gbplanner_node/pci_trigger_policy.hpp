#pragma once

namespace gbplanner_node {

class PciTriggerPolicy {
 public:
  void configure(bool wait_for_enable, bool stop_after_first_path) {
    wait_for_enable_ = wait_for_enable;
    stop_after_first_path_ = stop_after_first_path;
  }

  void observeEnable(bool enabled) { enabled_ = enabled; }

  bool mayTrigger() const {
    return (!wait_for_enable_ || enabled_) &&
           (!stop_after_first_path_ || !path_published_);
  }

  bool markNonEmptyPathPublished() {
    path_published_ = true;
    return stop_after_first_path_;
  }

 private:
  bool wait_for_enable_ = false;
  bool stop_after_first_path_ = false;
  bool enabled_ = false;
  bool path_published_ = false;
};

}  // namespace gbplanner_node
