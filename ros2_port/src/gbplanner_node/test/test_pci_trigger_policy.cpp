#include <gtest/gtest.h>

#include "gbplanner_node/pci_trigger_policy.hpp"

using gbplanner_node::PciTriggerPolicy;

TEST(PciTriggerPolicy, DefaultsPreservePeriodicM4Behavior) {
  PciTriggerPolicy policy;
  policy.configure(false, false);

  EXPECT_TRUE(policy.mayTrigger());
  EXPECT_FALSE(policy.markNonEmptyPathPublished());
  EXPECT_TRUE(policy.mayTrigger());
}

TEST(PciTriggerPolicy, WaitsForAndRevokesEnableLease) {
  PciTriggerPolicy policy;
  policy.configure(true, false);

  EXPECT_FALSE(policy.mayTrigger());
  policy.observeEnable(true);
  EXPECT_TRUE(policy.mayTrigger());
  policy.observeEnable(false);
  EXPECT_FALSE(policy.mayTrigger());
}

TEST(PciTriggerPolicy, StopsOnlyAfterFirstNonEmptyPathIsPublished) {
  PciTriggerPolicy policy;
  policy.configure(true, true);

  policy.observeEnable(true);
  EXPECT_TRUE(policy.mayTrigger());
  EXPECT_TRUE(policy.markNonEmptyPathPublished());
  EXPECT_FALSE(policy.mayTrigger());
}
