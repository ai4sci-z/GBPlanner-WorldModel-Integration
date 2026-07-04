package tasks

import (
	"testing"

	"navlab/orchestration-sim/internal/config"
)

func TestApplyHoverSLOPolicyAppliesCLIOverrides(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		SlamHover: config.SlamHoverConfig{
			MaxHoverHorizontalDriftM: 0.10,
			HoverSpanTargetM:         0.10,
			HoverSpanHardCapM:        0.15,
		},
	}
	updated, err := ApplyHoverSLOPolicy(runtimeConfig, Plan{
		TaskID:            "hover",
		HoverSpanTargetM:  0.12,
		HoverSpanHardCapM: 0.18,
	})
	if err != nil {
		t.Fatalf("ApplyHoverSLOPolicy() error = %v", err)
	}
	if updated.SlamHover.HoverSpanTargetM != 0.12 || updated.SlamHover.HoverSpanHardCapM != 0.18 {
		t.Fatalf("hover SLO policy = target %v hard cap %v", updated.SlamHover.HoverSpanTargetM, updated.SlamHover.HoverSpanHardCapM)
	}
}

func TestApplyHoverSLOPolicyRejectsInvalidOverrides(t *testing.T) {
	_, err := ApplyHoverSLOPolicy(config.TaskRuntimeConfig{}, Plan{
		TaskID:            "hover",
		HoverSpanTargetM:  0.20,
		HoverSpanHardCapM: 0.15,
	})
	if err == nil {
		t.Fatal("ApplyHoverSLOPolicy() error = nil, want invalid policy error")
	}
}
