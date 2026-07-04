package config

import (
	"path/filepath"
	"testing"
)

func TestBuildTaskRuntimeConfigAppliesTaskOverrides(t *testing.T) {
	loader := NewLoader(filepath.Join("..", "..", "config.toml"))
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatal(err)
	}
	task, err := loader.LoadTask(project, "hover")
	if err != nil {
		t.Fatal(err)
	}

	runtimeConfig, err := BuildTaskRuntimeConfig(project, task)
	if err != nil {
		t.Fatal(err)
	}

	if runtimeConfig.FCUController.TakeoffAltM != 0.5 {
		t.Fatalf("takeoff alt = %v", runtimeConfig.FCUController.TakeoffAltM)
	}
	if runtimeConfig.FCUController.TakeoffMinHeightM != 0.15 || runtimeConfig.FCUController.TakeoffMinHeightRatio != 0.35 {
		t.Fatalf("takeoff readiness threshold = %v/%v", runtimeConfig.FCUController.TakeoffMinHeightM, runtimeConfig.FCUController.TakeoffMinHeightRatio)
	}
	if runtimeConfig.SlamHover.HoverWindowSec != 18 {
		t.Fatalf("hover window = %v", runtimeConfig.SlamHover.HoverWindowSec)
	}
	if runtimeConfig.SlamHover.HoverSpanTargetM != 0.10 || runtimeConfig.SlamHover.HoverSpanHardCapM != 0.15 {
		t.Fatalf("hover SLO policy = target %v hard cap %v", runtimeConfig.SlamHover.HoverSpanTargetM, runtimeConfig.SlamHover.HoverSpanHardCapM)
	}
	policy := runtimeConfig.SlamHover.StartupReadinessPolicy
	if policy.TimeoutSec != 35 || policy.GraceSec != 8 || policy.ProgressWindowSec != 3 || policy.RestartLimit != 0 {
		t.Fatalf("startup readiness policy = %#v", policy)
	}
	if runtimeConfig.Landing.HoverPolicy != "ap_land_mode_after_hover" {
		t.Fatalf("hover landing policy = %q", runtimeConfig.Landing.HoverPolicy)
	}
	if runtimeConfig.FrameContract.MapFrameID != "map" {
		t.Fatalf("default frame contract not preserved: %#v", runtimeConfig.FrameContract)
	}
}

func TestNormalizeHoverSLOPolicyRejectsHardCapBelowTarget(t *testing.T) {
	cfg := SlamHoverConfig{
		MaxHoverHorizontalDriftM: 0.10,
		HoverSpanTargetM:         0.10,
		HoverSpanHardCapM:        0.05,
	}
	if err := NormalizeHoverSLOPolicy(&cfg); err == nil {
		t.Fatal("NormalizeHoverSLOPolicy() error = nil, want invalid policy error")
	}
}

func TestNormalizeStartupReadinessPolicyRejectsInvalidPolicy(t *testing.T) {
	cfg := StartupReadinessPolicyConfig{
		TimeoutSec:        5,
		GraceSec:          8,
		ProgressWindowSec: 3,
	}
	if err := NormalizeStartupReadinessPolicy(&cfg); err == nil {
		t.Fatal("NormalizeStartupReadinessPolicy() error = nil, want invalid grace/timeout policy error")
	}

	cfg = StartupReadinessPolicyConfig{
		TimeoutSec:        35,
		GraceSec:          8,
		ProgressWindowSec: 3,
		RestartLimit:      -1,
	}
	if err := NormalizeStartupReadinessPolicy(&cfg); err == nil {
		t.Fatal("NormalizeStartupReadinessPolicy() error = nil, want invalid restart limit error")
	}
}

func TestBuildTaskRuntimeConfigAppliesExplorationOverrides(t *testing.T) {
	loader := NewLoader(filepath.Join("..", "..", "config.toml"))
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatal(err)
	}
	task, err := loader.LoadTask(project, "exploration")
	if err != nil {
		t.Fatal(err)
	}
	runtimeConfig, err := BuildTaskRuntimeConfig(project, task)
	if err != nil {
		t.Fatal(err)
	}
	if runtimeConfig.ExplorationGate.MinAcceptedGoals != 3 {
		t.Fatalf("min accepted goals = %d", runtimeConfig.ExplorationGate.MinAcceptedGoals)
	}
	if runtimeConfig.FCUController.TakeoffMinHeightM != 0.15 || runtimeConfig.FCUController.TakeoffMinHeightRatio != 0.35 {
		t.Fatalf("exploration takeoff readiness threshold = %v/%v", runtimeConfig.FCUController.TakeoffMinHeightM, runtimeConfig.FCUController.TakeoffMinHeightRatio)
	}
	if runtimeConfig.Landing.ExplorationPolicy != "return_home_then_land" {
		t.Fatalf("exploration landing policy = %q", runtimeConfig.Landing.ExplorationPolicy)
	}
}

func TestBuildTaskRuntimeConfigAppliesNavigationOverrides(t *testing.T) {
	loader := NewLoader(filepath.Join("..", "..", "config.toml"))
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatal(err)
	}
	task, err := loader.LoadTask(project, "navigation")
	if err != nil {
		t.Fatal(err)
	}
	runtimeConfig, err := BuildTaskRuntimeConfig(project, task)
	if err != nil {
		t.Fatal(err)
	}
	if runtimeConfig.Nav2.Profile != "indoor_2d" {
		t.Fatalf("nav2 profile = %q", runtimeConfig.Nav2.Profile)
	}
	if runtimeConfig.Nav2.Costmap.MaxCostmapAgeSec != 1.5 {
		t.Fatalf("max costmap age = %v", runtimeConfig.Nav2.Costmap.MaxCostmapAgeSec)
	}
	if runtimeConfig.NavigationAdapter.FixedAltitudeM != 0.8 {
		t.Fatalf("fixed altitude = %v", runtimeConfig.NavigationAdapter.FixedAltitudeM)
	}
	if runtimeConfig.NavigationMission.MinPathLengthM != 4.0 {
		t.Fatalf("min path length = %v", runtimeConfig.NavigationMission.MinPathLengthM)
	}
	if runtimeConfig.NavigationMission.GoalFrame != "map" || runtimeConfig.NavigationMission.ExitGoal.ID != "maze_exit" || len(runtimeConfig.NavigationMission.BoundedGoals) == 0 {
		t.Fatalf("navigation goals = %#v", runtimeConfig.NavigationMission)
	}
	if runtimeConfig.NavigationMission.CompletionPolicy != "land_in_place" {
		t.Fatalf("navigation completion policy = %q", runtimeConfig.NavigationMission.CompletionPolicy)
	}
	if runtimeConfig.Landing.NavigationPolicy != "land_in_place" {
		t.Fatalf("navigation landing policy = %q", runtimeConfig.Landing.NavigationPolicy)
	}
}

func TestBuildTaskRuntimeConfigAppliesScanRobustnessOverrides(t *testing.T) {
	loader := NewLoader(filepath.Join("..", "..", "config.toml"))
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatal(err)
	}
	task, err := loader.LoadTask(project, "scan-robustness")
	if err != nil {
		t.Fatal(err)
	}
	runtimeConfig, err := BuildTaskRuntimeConfig(project, task)
	if err != nil {
		t.Fatal(err)
	}
	if !runtimeConfig.ScanRobustness.Live {
		t.Fatalf("scan robustness live = false")
	}
	if runtimeConfig.AirframeDisturbance.Profile != "ideal" {
		t.Fatalf("airframe profile = %q", runtimeConfig.AirframeDisturbance.Profile)
	}
	if runtimeConfig.Landing.ScanRobustnessPolicy != "land_in_place" {
		t.Fatalf("scan landing policy = %q", runtimeConfig.Landing.ScanRobustnessPolicy)
	}
}
