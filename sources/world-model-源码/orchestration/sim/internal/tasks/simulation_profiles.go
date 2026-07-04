package tasks

import (
	"fmt"
	"sort"
	"strings"

	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

const (
	ProfileIdeal                   = "ideal"
	ProfileRealistic               = "realistic"
	ProfileSlamDirect              = "slam-direct"
	ProfileSlamDirectNoOdomPrior   = "slam-direct-no-odom-prior"
	ProfilePurposeLegacyDebug      = "legacy-debug"
	ProfilePurposeDiagnostic       = "diagnostic"
	ProfilePurposeMainline         = "mainline"
	ExternalNavInputDefault        = "default-selector-candidate"
	ExternalNavInputDirectSlamOdom = "direct-slam-odom"
)

type HoverSimulationProfile struct {
	Name                       string
	Purpose                    string
	AllowTasks                 []string
	ExternalNavInputOdomMode   string
	CartographerConfigBasename string
	Mainline                   bool
}

func HoverSimulationProfiles() []HoverSimulationProfile {
	profiles := []HoverSimulationProfile{
		{
			Name:                       ProfileIdeal,
			Purpose:                    ProfilePurposeLegacyDebug,
			AllowTasks:                 []string{"hover", "hover-slam-only"},
			ExternalNavInputOdomMode:   ExternalNavInputDefault,
			CartographerConfigBasename: helpers.HoverCartographerConfigBasename,
		},
		{
			Name:                       ProfileSlamDirect,
			Purpose:                    ProfilePurposeDiagnostic,
			AllowTasks:                 []string{"hover", "hover-slam-only"},
			ExternalNavInputOdomMode:   ExternalNavInputDirectSlamOdom,
			CartographerConfigBasename: helpers.HoverCartographerConfigBasename,
		},
		{
			Name:                       ProfileSlamDirectNoOdomPrior,
			Purpose:                    ProfilePurposeMainline,
			AllowTasks:                 []string{"hover", "hover-slam-only"},
			ExternalNavInputOdomMode:   ExternalNavInputDirectSlamOdom,
			CartographerConfigBasename: helpers.HoverNoOdomPriorConfigBasename,
			Mainline:                   true,
		},
	}
	sort.Slice(profiles, func(i, j int) bool { return profiles[i].Name < profiles[j].Name })
	return profiles
}

func hoverSimulationProfileForTask(taskID string, profileName string) (HoverSimulationProfile, bool) {
	for _, profile := range HoverSimulationProfiles() {
		if profile.Name == profileName && stringInSlice(taskID, profile.AllowTasks) {
			return profile, true
		}
	}
	return HoverSimulationProfile{}, false
}

func AllowedProfilesForTask(taskID string) []string {
	allowed := []string{}
	for _, profile := range HoverSimulationProfiles() {
		if stringInSlice(taskID, profile.AllowTasks) {
			allowed = append(allowed, profile.Name)
		}
	}
	sort.Strings(allowed)
	return allowed
}

func applyHoverSimulationProfile(runtimeConfig config.TaskRuntimeConfig, profile HoverSimulationProfile) config.TaskRuntimeConfig {
	switch profile.ExternalNavInputOdomMode {
	case ExternalNavInputDirectSlamOdom:
		runtimeConfig.SlamHover.ExternalNavInputOdomTopic = runtimeConfig.SlamHover.SlamOdomTopic
	}
	if profile.CartographerConfigBasename != "" {
		runtimeConfig.SlamBackend.CartographerConfigurationBasename = profile.CartographerConfigBasename
	}
	return runtimeConfig
}

func ApplySimulationProfile(runtimeConfig config.TaskRuntimeConfig, plan Plan) (config.TaskRuntimeConfig, error) {
	if isHoverSLAMProfileTask(plan.TaskID) {
		if plan.SimulationProfile == "" {
			return runtimeConfig, nil
		}
		profile, ok := hoverSimulationProfileForTask(plan.TaskID, plan.SimulationProfile)
		if !ok {
			return runtimeConfig, invalidSimulationProfileError(plan.TaskID, plan.SimulationProfile, AllowedProfilesForTask(plan.TaskID))
		}
		return applyHoverSimulationProfile(runtimeConfig, profile), nil
	}
	if plan.TaskID != "scan-robustness" || plan.SimulationProfile == "" {
		return runtimeConfig, nil
	}
	if !stringInSlice(plan.SimulationProfile, runtimeConfig.AirframeDisturbanceGate.ProfileSet) {
		return runtimeConfig, invalidSimulationProfileError(plan.TaskID, plan.SimulationProfile, runtimeConfig.AirframeDisturbanceGate.ProfileSet)
	}
	runtimeConfig.AirframeDisturbance.Profile = plan.SimulationProfile
	return runtimeConfig, nil
}

func invalidSimulationProfileError(taskID string, profileName string, allowed []string) error {
	choices := append([]string(nil), allowed...)
	sort.Strings(choices)
	return fmt.Errorf("simulation profile %q is not valid for task %q; allowed profiles: %s", profileName, taskID, strings.Join(choices, ", "))
}

func isHoverSLAMProfileTask(taskID string) bool {
	switch taskID {
	case "hover", "hover-slam-only":
		return true
	default:
		return false
	}
}

func stringInSlice(value string, values []string) bool {
	for _, candidate := range values {
		if candidate == value {
			return true
		}
	}
	return false
}
