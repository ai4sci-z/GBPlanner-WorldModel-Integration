package tasks

import (
	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

type Definition struct {
	ID          string
	Description string
	Steps       []string
	HelperIDs   []string
}

type ConfiguredTask struct {
	Definition Definition
	Config     config.TaskConfig
}

type PlanOptions struct {
	DurationSec       float64
	SimulationProfile string
	HoverSpanTargetM  float64
	HoverSpanHardCapM float64
}

type Plan struct {
	TaskID            string                `json:"task_id"`
	Description       string                `json:"description"`
	DurationSec       float64               `json:"duration_sec"`
	SimulationProfile string                `json:"simulation_profile"`
	HoverSpanTargetM  float64               `json:"hover_span_target_m,omitempty"`
	HoverSpanHardCapM float64               `json:"hover_span_hard_cap_m,omitempty"`
	Capabilities      []string              `json:"capabilities"`
	Steps             []string              `json:"steps"`
	Helpers           []helpers.Definition  `json:"helpers"`
	Execution         helpers.ExecutionPlan `json:"execution_plan"`
}

func (task ConfiguredTask) Plan(options PlanOptions, helperRegistry *helpers.Registry) (Plan, error) {
	durationSec := task.Config.Task.DurationSec
	if task.Config.Task.TimeoutSec > 0 {
		durationSec = task.Config.Task.TimeoutSec
	}
	if options.DurationSec > 0 {
		durationSec = options.DurationSec
	}
	simulationProfile := task.Config.Task.SimulationProfile
	if options.SimulationProfile != "" {
		simulationProfile = options.SimulationProfile
	}
	helperDefinitions, err := helperRegistry.Resolve(task.Definition.HelperIDs)
	if err != nil {
		return Plan{}, err
	}
	execution, err := helpers.BuildExecutionPlan(task.Config, durationSec, simulationProfile, helperDefinitions)
	if err != nil {
		return Plan{}, err
	}
	return Plan{
		TaskID:            task.Config.ID,
		Description:       task.Config.Description,
		DurationSec:       durationSec,
		SimulationProfile: simulationProfile,
		HoverSpanTargetM:  options.HoverSpanTargetM,
		HoverSpanHardCapM: options.HoverSpanHardCapM,
		Capabilities:      append([]string(nil), task.Config.Capabilities...),
		Steps:             append([]string(nil), task.Definition.Steps...),
		Helpers:           helperDefinitions,
		Execution:         execution,
	}, nil
}
