#include "navlab_slam_imu_bridge/timestamp.hpp"

#include <gtest/gtest.h>

using navlab_slam_imu_bridge::monotonic_output_stamp_nanoseconds;

TEST(ImuTimestamp, KeepsFirstCandidate) {
  EXPECT_EQ(monotonic_output_stamp_nanoseconds(100, std::nullopt), 100);
}

TEST(ImuTimestamp, KeepsForwardCandidate) {
  EXPECT_EQ(monotonic_output_stamp_nanoseconds(150, 100), 150);
}

TEST(ImuTimestamp, ClampsEqualCandidate) {
  EXPECT_EQ(monotonic_output_stamp_nanoseconds(100, 100), 101);
}

TEST(ImuTimestamp, ClampsBackwardCandidate) {
  EXPECT_EQ(monotonic_output_stamp_nanoseconds(90, 100), 101);
}
