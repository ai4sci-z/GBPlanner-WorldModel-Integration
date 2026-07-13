#pragma once
// ros::Time / ros::Duration shims for the ROS-free gbplanner core (M3).
// The core only uses wall-clock deltas for timing/bookkeeping (verified by
// grep: Time::now(), operator-, toSec, Duration comparisons), so a
// steady_clock-backed double-seconds pair covers every call site.
#include <chrono>
#include <thread>

namespace pshim {

class Duration {
 public:
  Duration() = default;
  explicit Duration(double sec) : sec_(sec) {}
  double toSec() const { return sec_; }
  void sleep() const {
    if (sec_ > 0.0)
      std::this_thread::sleep_for(std::chrono::duration<double>(sec_));
  }
  bool operator>(const Duration& o) const { return sec_ > o.sec_; }
  bool operator<(const Duration& o) const { return sec_ < o.sec_; }
  bool operator>=(const Duration& o) const { return sec_ >= o.sec_; }
  bool operator<=(const Duration& o) const { return sec_ <= o.sec_; }

 private:
  double sec_ = 0.0;
};

class Time {
 public:
  Time() = default;
  explicit Time(double sec) : sec_(sec) {}
  static Time now() {
    return Time(std::chrono::duration<double>(
                    std::chrono::steady_clock::now().time_since_epoch())
                    .count());
  }
  double toSec() const { return sec_; }
  Duration operator-(const Time& o) const { return Duration(sec_ - o.sec_); }
  Time operator+(const Duration& d) const { return Time(sec_ + d.toSec()); }
  bool operator==(const Time& o) const { return sec_ == o.sec_; }
  bool operator!=(const Time& o) const { return sec_ != o.sec_; }

 private:
  double sec_ = 0.0;
};

struct TimerEvent {};

}  // namespace pshim
