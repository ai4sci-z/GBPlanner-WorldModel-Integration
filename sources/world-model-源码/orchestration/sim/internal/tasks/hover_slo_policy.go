package tasks

import (
	"fmt"

	"navlab/orchestration-sim/internal/config"
)

func ApplyHoverSLOPolicy(runtimeConfig config.TaskRuntimeConfig, plan Plan) (config.TaskRuntimeConfig, error) {
	if !isHoverSLAMProfileTask(plan.TaskID) {
		return runtimeConfig, nil
	}
	if plan.HoverSpanTargetM > 0 {
		runtimeConfig.SlamHover.HoverSpanTargetM = plan.HoverSpanTargetM
	}
	if plan.HoverSpanHardCapM > 0 {
		runtimeConfig.SlamHover.HoverSpanHardCapM = plan.HoverSpanHardCapM
	}
	if err := config.NormalizeHoverSLOPolicy(&runtimeConfig.SlamHover); err != nil {
		return runtimeConfig, fmt.Errorf("hover SLO policy: %w", err)
	}
	return runtimeConfig, nil
}
