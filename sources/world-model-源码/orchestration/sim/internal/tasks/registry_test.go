package tasks

import (
	"testing"

	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func TestDefaultRegistryConfiguresKnownTask(t *testing.T) {
	registry := DefaultRegistry()
	task, err := registry.ConfigureOne(config.TaskConfig{
		ID:          "hover",
		Family:      "sim",
		Description: "custom hover",
		Task: config.TaskParameters{
			DurationSec:       90,
			SimulationProfile: "ideal",
		},
	})
	if err != nil {
		t.Fatalf("ConfigureOne() error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{DurationSec: 10, SimulationProfile: "realistic"}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan() error = %v", err)
	}
	if plan.DurationSec != 10 {
		t.Fatalf("DurationSec = %v, want 10", plan.DurationSec)
	}
	if plan.SimulationProfile != "realistic" {
		t.Fatalf("SimulationProfile = %q, want realistic", plan.SimulationProfile)
	}
	if len(plan.Steps) == 0 {
		t.Fatal("plan steps are empty")
	}
	if len(plan.Helpers) == 0 {
		t.Fatal("plan helpers are empty")
	}
}

func TestPlanUsesTaskTimeoutAsDeadline(t *testing.T) {
	registry := DefaultRegistry()
	task, err := registry.ConfigureOne(config.TaskConfig{
		ID:     "hover",
		Family: "sim",
		Task: config.TaskParameters{
			DurationSec: 90,
			TimeoutSec:  30,
		},
	})
	if err != nil {
		t.Fatalf("ConfigureOne() error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan() error = %v", err)
	}
	if plan.DurationSec != 30 {
		t.Fatalf("DurationSec = %v, want timeout deadline 30", plan.DurationSec)
	}
}

func TestDefaultRegistryRejectsUnregisteredTask(t *testing.T) {
	registry := DefaultRegistry()
	_, err := registry.ConfigureOne(config.TaskConfig{ID: "preflight", Family: "sim"})
	if err == nil {
		t.Fatal("ConfigureOne(preflight) error = nil, want error")
	}
}

func TestDefaultRegistryConfiguresNavigationTask(t *testing.T) {
	registry := DefaultRegistry()
	task, err := registry.ConfigureOne(config.TaskConfig{
		ID:     "navigation",
		Family: "sim",
		Task: config.TaskParameters{
			DurationSec:       180,
			SimulationProfile: "ideal",
		},
	})
	if err != nil {
		t.Fatalf("ConfigureOne(navigation) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(navigation) error = %v", err)
	}
	if !hasHelperID(plan.Helpers, "nav2-navigation-workflow") {
		t.Fatalf("navigation helpers missing nav2-navigation-workflow: %#v", plan.Helpers)
	}
}

func TestDefaultRegistryExplorationDoesNotUseHoverProbe(t *testing.T) {
	registry := DefaultRegistry()
	task, err := registry.ConfigureOne(config.TaskConfig{
		ID:     "exploration",
		Family: "sim",
		Task: config.TaskParameters{
			DurationSec:       150,
			SimulationProfile: "ideal",
		},
	})
	if err != nil {
		t.Fatalf("ConfigureOne(exploration) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(exploration) error = %v", err)
	}
	if hasHelperID(plan.Helpers, "slam-hover") {
		t.Fatalf("exploration helpers unexpectedly include slam-hover: %#v", plan.Helpers)
	}
	if !hasHelperID(plan.Helpers, "exploration-workflow") {
		t.Fatalf("exploration helpers missing exploration-workflow: %#v", plan.Helpers)
	}
}

func TestDefaultRegistryHoverUsesPythonMissionRuntimeOnly(t *testing.T) {
	registry := DefaultRegistry()
	task, err := registry.ConfigureOne(config.TaskConfig{
		ID:     "hover",
		Family: "sim",
		Task: config.TaskParameters{
			DurationSec:       90,
			SimulationProfile: "ideal",
		},
	})
	if err != nil {
		t.Fatalf("ConfigureOne(hover) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(hover) error = %v", err)
	}
	if hasHelperID(plan.Helpers, "fcu-controller") {
		t.Fatalf("hover helpers unexpectedly include fcu-controller: %#v", plan.Helpers)
	}
	if !hasHelperID(plan.Helpers, "slam-hover") {
		t.Fatalf("hover helpers missing slam-hover: %#v", plan.Helpers)
	}
}

func TestDefaultRegistryHoverSlamOnlyDoesNotUseHoverMission(t *testing.T) {
	registry := DefaultRegistry()
	task, err := registry.ConfigureOne(config.TaskConfig{
		ID:     "hover-slam-only",
		Family: "sim",
		Task: config.TaskParameters{
			DurationSec:       45,
			SimulationProfile: "ideal",
		},
	})
	if err != nil {
		t.Fatalf("ConfigureOne(hover-slam-only) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(hover-slam-only) error = %v", err)
	}
	if hasHelperID(plan.Helpers, "slam-hover") || hasHelperID(plan.Helpers, "landing") || hasHelperID(plan.Helpers, "fcu-controller") || hasHelperID(plan.Helpers, "frame-contract") {
		t.Fatalf("hover-slam-only must not include mission/landing/FCU helpers: %#v", plan.Helpers)
	}
	if !hasHelperID(plan.Helpers, "slam-only") {
		t.Fatalf("hover-slam-only helpers missing slam-only: %#v", plan.Helpers)
	}
}

func hasHelperID(helperDefinitions []helpers.Definition, id string) bool {
	for _, helper := range helperDefinitions {
		if helper.ID == id {
			return true
		}
	}
	return false
}
