package tasks

import (
	"strings"
	"testing"

	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func TestApplySimulationProfileOverridesScanRobustnessRuntimeProfile(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		AirframeDisturbance: config.AirframeDisturbanceConfig{
			Profile: "ideal",
		},
		AirframeDisturbanceGate: config.AirframeDisturbanceGateConfig{
			ProfileSet: []string{"ideal", "realistic"},
		},
	}

	updated, err := ApplySimulationProfile(runtimeConfig, Plan{
		TaskID:            "scan-robustness",
		SimulationProfile: "realistic",
	})
	if err != nil {
		t.Fatalf("ApplySimulationProfile() error = %v", err)
	}
	if updated.AirframeDisturbance.Profile != "realistic" {
		t.Fatalf("airframe profile = %q", updated.AirframeDisturbance.Profile)
	}
}

func TestApplySimulationProfileRejectsUnknownScanRobustnessProfile(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		AirframeDisturbanceGate: config.AirframeDisturbanceGateConfig{
			ProfileSet: []string{"ideal", "realistic"},
		},
	}

	_, err := ApplySimulationProfile(runtimeConfig, Plan{
		TaskID:            "scan-robustness",
		SimulationProfile: "unsupported_profile",
	})
	if err == nil {
		t.Fatal("ApplySimulationProfile() error = nil, want unknown profile error")
	}
	if !strings.Contains(err.Error(), `simulation profile "unsupported_profile"`) {
		t.Fatalf("error = %v", err)
	}
	if !strings.Contains(err.Error(), `allowed profiles: ideal, realistic`) {
		t.Fatalf("error missing allowed profile list: %v", err)
	}
}

func TestApplySimulationProfileDoesNotChangeOtherTasks(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		AirframeDisturbance: config.AirframeDisturbanceConfig{
			Profile: "realistic",
		},
		AirframeDisturbanceGate: config.AirframeDisturbanceGateConfig{
			ProfileSet: []string{"ideal", "realistic"},
		},
	}

	updated, err := ApplySimulationProfile(runtimeConfig, Plan{
		TaskID:            "navigation",
		SimulationProfile: "realistic",
	})
	if err != nil {
		t.Fatalf("ApplySimulationProfile() error = %v", err)
	}
	if updated.AirframeDisturbance.Profile != "realistic" {
		t.Fatalf("airframe profile = %q", updated.AirframeDisturbance.Profile)
	}
}

func TestHoverSimulationProfileRegistryListsMainlineProfile(t *testing.T) {
	allowed := AllowedProfilesForTask("hover")
	want := []string{ProfileIdeal, ProfileSlamDirect, ProfileSlamDirectNoOdomPrior}
	if strings.Join(allowed, ",") != strings.Join(want, ",") {
		t.Fatalf("allowed hover profiles = %#v, want %#v", allowed, want)
	}
	profile, ok := hoverSimulationProfileForTask("hover", ProfileSlamDirectNoOdomPrior)
	if !ok {
		t.Fatalf("mainline hover profile %q missing", ProfileSlamDirectNoOdomPrior)
	}
	if !profile.Mainline || profile.Purpose != ProfilePurposeMainline {
		t.Fatalf("mainline profile metadata = %#v", profile)
	}
	if profile.ExternalNavInputOdomMode != ExternalNavInputDirectSlamOdom {
		t.Fatalf("external nav mode = %q", profile.ExternalNavInputOdomMode)
	}
	if profile.CartographerConfigBasename != helpers.HoverNoOdomPriorConfigBasename {
		t.Fatalf("cartographer config = %q", profile.CartographerConfigBasename)
	}
}

func TestApplySimulationProfileRejectsUnknownHoverProfile(t *testing.T) {
	_, err := ApplySimulationProfile(config.TaskRuntimeConfig{}, Plan{
		TaskID:            "hover",
		SimulationProfile: ProfileRealistic,
	})
	if err == nil {
		t.Fatal("ApplySimulationProfile() error = nil, want unknown hover profile error")
	}
	for _, want := range []string{
		`simulation profile "realistic" is not valid for task "hover"`,
		ProfileIdeal,
		ProfileSlamDirect,
		ProfileSlamDirectNoOdomPrior,
	} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error missing %q: %v", want, err)
		}
	}
}

func TestApplySimulationProfileHoverSlamDirectUsesRawSlamOdom(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		SlamHover: config.SlamHoverConfig{
			SlamOdomTopic: "/slam/odom",
		},
	}

	updated, err := ApplySimulationProfile(runtimeConfig, Plan{
		TaskID:            "hover",
		SimulationProfile: ProfileSlamDirect,
	})
	if err != nil {
		t.Fatalf("ApplySimulationProfile() error = %v", err)
	}
	if updated.SlamHover.ExternalNavInputOdomTopic != "/slam/odom" {
		t.Fatalf("external nav input = %q, want /slam/odom", updated.SlamHover.ExternalNavInputOdomTopic)
	}
}

func TestApplySimulationProfileHoverSlamDirectNoOdomPriorUsesRawSlamOdomAndNoOdomConfig(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		SlamHover: config.SlamHoverConfig{
			SlamOdomTopic: "/slam/odom",
		},
	}

	updated, err := ApplySimulationProfile(runtimeConfig, Plan{
		TaskID:            "hover",
		SimulationProfile: ProfileSlamDirectNoOdomPrior,
	})
	if err != nil {
		t.Fatalf("ApplySimulationProfile() error = %v", err)
	}
	if updated.SlamHover.ExternalNavInputOdomTopic != "/slam/odom" {
		t.Fatalf("external nav input = %q, want /slam/odom", updated.SlamHover.ExternalNavInputOdomTopic)
	}
	if updated.SlamBackend.CartographerConfigurationBasename != helpers.HoverNoOdomPriorConfigBasename {
		t.Fatalf("cartographer config = %q, want %q", updated.SlamBackend.CartographerConfigurationBasename, helpers.HoverNoOdomPriorConfigBasename)
	}
}

func TestApplySimulationProfileHoverSlamOnlyNoOdomPriorUsesNoOdomConfig(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		SlamHover: config.SlamHoverConfig{
			SlamOdomTopic: "/slam/odom",
		},
	}

	updated, err := ApplySimulationProfile(runtimeConfig, Plan{
		TaskID:            "hover-slam-only",
		SimulationProfile: ProfileSlamDirectNoOdomPrior,
	})
	if err != nil {
		t.Fatalf("ApplySimulationProfile() error = %v", err)
	}
	if updated.SlamHover.ExternalNavInputOdomTopic != "/slam/odom" {
		t.Fatalf("external nav input = %q, want /slam/odom", updated.SlamHover.ExternalNavInputOdomTopic)
	}
	if updated.SlamBackend.CartographerConfigurationBasename != helpers.HoverNoOdomPriorConfigBasename {
		t.Fatalf("cartographer config = %q, want %q", updated.SlamBackend.CartographerConfigurationBasename, helpers.HoverNoOdomPriorConfigBasename)
	}
}
