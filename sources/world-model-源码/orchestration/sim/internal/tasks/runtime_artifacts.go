package tasks

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	simruntime "navlab/orchestration-sim/internal/runtime"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

const officialMazeSDFRelativePath = "../ardupilot_gz/ardupilot_gz_gazebo/worlds/maze.sdf"
const officialExternalNavParamRelativePath = "docker/profiles/navlab-sitl-external-nav.parm"
const cartographerConfigRelativePath = "navlab/common/slam/ros/localization/navlab_cartographer_adapter/config"

type GeneratedRuntimeArtifact struct {
	Type string `json:"type"`
	Path string `json:"path"`
}

func GenerateRuntimeArtifacts(
	project config.ProjectConfig,
	plan Plan,
	runtimeConfig config.TaskRuntimeConfig,
	artifactDir string,
) ([]GeneratedRuntimeArtifact, error) {
	var generated []GeneratedRuntimeArtifact
	if err := os.MkdirAll(artifactDir, 0o755); err != nil {
		return nil, err
	}
	if err := artifactlayout.Ensure(artifactDir); err != nil {
		return nil, err
	}
	if publishesOfficialMazeOverlayTask(plan.TaskID) {
		mazeSource, err := officialMazeSource(project)
		if err != nil {
			return nil, err
		}
		path := artifactlayout.RuntimeScript(artifactDir, "official_maze_overlay_runtime.py")
		mazeOverlaySpec := helpers.DefaultOfficialMazeOverlaySpec()
		if err := helpers.WriteOfficialMazeOverlayRuntimeScript(path, mazeSource, mazeOverlaySpec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "official_maze_overlay_script", Path: path})
	}
	if hasHelper(plan, "navlab-models") {
		bridge := artifactlayout.RuntimeConfig(artifactDir, "bridge_override.yaml")
		if err := helpers.WriteBridgeOverride(bridge); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "bridge_override", Path: bridge})
		vendor := artifactlayout.RuntimeConfig(artifactDir, "vendor_profile.yaml")
		if err := helpers.WriteVendorProfile(vendor, runtimeConfig.RangefinderIMU.X2VirtualSerialLink); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "vendor_profile", Path: vendor})
	}
	if hasHelper(plan, "sensors") {
		spec := sensorSpec(runtimeConfig)
		modelSource, err := officialOverlaySource(project, helpers.OfficialIrisWithLidarModel)
		if err != nil {
			return nil, err
		}
		modelOverlay := artifactlayout.RuntimeConfig(artifactDir, "model_overlay.sdf")
		if err := helpers.WriteModelOverlayFromSource(modelOverlay, modelSource, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "model_overlay", Path: modelOverlay})
		paramSource, err := officialOverlaySource(project, helpers.OfficialGazeboIrisParams)
		if err != nil {
			return nil, err
		}
		externalNavParamSource, err := officialExternalNavParamSource(project)
		if err != nil {
			return nil, err
		}
		paramSource = mergeExternalNavParamProfile(paramSource, externalNavParamSource)
		paramOverlay := artifactlayout.RuntimeConfig(artifactDir, "gazebo-iris-rangefinder.parm")
		if err := helpers.WriteParamOverlayFromSource(paramOverlay, paramSource, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "param_overlay", Path: paramOverlay})
		sensorConfig := artifactlayout.RuntimeConfig(artifactDir, "gazebo_sensor_runtime.toml")
		vendorProfile, err := runtimeContainerPath(project, artifactlayout.RuntimeConfig(artifactDir, "vendor_profile.yaml"))
		if err != nil {
			return nil, err
		}
		if err := helpers.WriteSensorRuntimeConfig(sensorConfig, vendorProfile, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "sensor_runtime_config", Path: sensorConfig})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "rangefinder_probe.py"), func() (string, error) {
			return helpers.RangefinderProbeScript(sensorSpec(runtimeConfig))
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "rangefinder_probe_script", Path: artifactlayout.Probe(artifactDir, "rangefinder_probe.py")})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "imu_probe.py"), func() (string, error) {
			return helpers.IMUProbeScript(sensorSpec(runtimeConfig))
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "imu_probe_script", Path: artifactlayout.Probe(artifactDir, "imu_probe.py")})
	}
	if hasHelper(plan, "slam") {
		spec := slamSpec(runtimeConfig)
		if isHoverSlamRuntimeTask(plan.TaskID) {
			spec.CartographerConfigurationBasename = hoverCartographerConfigBasename(runtimeConfig)
			spec.CartographerTFTopic = helpers.DefaultSlamRuntimeSpec().CartographerTFTopic
			spec.ExternalNavInputOdomTopic = hoverExternalNavInputOdomTopic(runtimeConfig)
			spec.IMUSourceTopic = "/imu"
			spec.IMUTopic = "/navlab/slam/imu"
			spec.PublishGlobalTF = false
			spec.RequireIMUForQuality = true
			spec.RequireScanForQuality = true
			spec.LowObservabilityMode = true
			configDir, err := runtimeContainerPath(project, filepath.Join(project.Paths.WorkspaceRoot, cartographerConfigRelativePath))
			if err != nil {
				return nil, err
			}
			spec.CartographerConfigurationDirectory = configDir
			source, err := resolveWorkspaceSource(project, filepath.Join(cartographerConfigRelativePath, spec.CartographerConfigurationBasename))
			if err != nil {
				return nil, err
			}
			content, err := os.ReadFile(source)
			if err != nil {
				return nil, err
			}
			hoverConfigPath := artifactlayout.RuntimeConfig(artifactDir, spec.CartographerConfigurationBasename)
			if err := os.WriteFile(hoverConfigPath, content, 0o644); err != nil {
				return nil, err
			}
			generated = append(generated, GeneratedRuntimeArtifact{Type: "hover_cartographer_config", Path: hoverConfigPath})
		}
		path := artifactlayout.RuntimeConfig(artifactDir, "slam_runtime.toml")
		if err := helpers.WriteSlamRuntimeConfig(path, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "slam_runtime_config", Path: path})
		externalNavBridgeParamsPath := artifactlayout.RuntimeConfig(artifactDir, "external_nav_bridge_params.yaml")
		externalNavSpec := spec
		if isHoverSlamRuntimeTask(plan.TaskID) {
			externalNavSpec.ExternalNavInputOdomTopic = hoverExternalNavInputOdomTopic(runtimeConfig)
		}
		if err := os.WriteFile(externalNavBridgeParamsPath, []byte(helpers.ExternalNavBridgeParamsOverride(externalNavSpec)), 0o644); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "external_nav_bridge_params_override", Path: externalNavBridgeParamsPath})
	}
	if hasHelper(plan, "fcu-controller") {
		path := artifactlayout.RuntimeConfig(artifactDir, "fcu_controller_runtime.toml")
		spec := fcuSpec(runtimeConfig)
		spec.LandingPolicy = landingPolicyForTask(runtimeConfig, plan.TaskID)
		spec.CompletionGraceSec = runtimeConfig.Landing.CompletionGraceSec
		if hasHelper(plan, "exploration-workflow") {
			exploration := explorationSpec(runtimeConfig)
			spec.MotionSpeedMPS = exploration.MotionSpeedMPS
			spec.MinAcceptedGoals = exploration.MinAcceptedGoals
			spec.MinPathLengthM = exploration.MinPathLengthM
			spec.TaskCompletionStatusTopic = exploration.ExplorationStatusTopic
		}
		if hasHelper(plan, "nav2-navigation-workflow") {
			navigation := nav2NavigationSpec(runtimeConfig)
			spec.MotionSpeedMPS = navigation.MaxXYSpeedMPS
			spec.MinAcceptedGoals = navigation.MinAcceptedGoals
			spec.MinPathLengthM = navigation.MinPathLengthM
			spec.TaskCompletionStatusTopic = navigation.NavigationStatusTopic
		}
		if hasHelper(plan, "scan-stabilization") || hasHelper(plan, "scan-robustness-workflow") {
			spec.IMUInputTopic = runtimeConfig.AirframeDisturbance.IMUInputTopic
			spec.IMUTopic = runtimeConfig.AirframeDisturbance.IMUOutputTopic
			spec.ScanInputTopic = runtimeConfig.ScanStabilization.InputScanTopic
			spec.ScanOutputTopic = runtimeConfig.ScanStabilization.OutputScanTopic
			spec.ScanStabilizationTopic = runtimeConfig.ScanStabilization.StatusTopic
			spec.DisturbanceStatusTopic = runtimeConfig.AirframeDisturbance.StatusTopic
			spec.DisturbanceProfile = runtimeConfig.AirframeDisturbance.Profile
			spec.RequiredProfiles = append([]string(nil), runtimeConfig.AirframeDisturbanceGate.RequiredProfiles...)
			spec.ESCLagMS = append([]float64(nil), runtimeConfig.AirframeDisturbance.ESCLagMS...)
			spec.MotorJitterHz = runtimeConfig.AirframeDisturbance.MotorJitterHz
			spec.ThrustNoiseStd = runtimeConfig.AirframeDisturbance.ThrustNoiseStd
			spec.IMUVibrationEnabled = runtimeConfig.AirframeDisturbance.IMUVibrationEnabled
			spec.IMUVibrationRollPitchAmpDeg = runtimeConfig.AirframeDisturbance.IMUVibrationRollPitchAmpDeg
		}
		if err := helpers.WriteFCUControllerRuntimeConfig(path, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "fcu_runtime_config", Path: path})
		if err := writeGeneratedScript(artifactlayout.RuntimeScript(artifactDir, "fcu_controller_runtime.py"), func() (string, error) {
			return helpers.FCUControllerRuntimeScript(spec, plan.DurationSec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "fcu_runtime_script", Path: artifactlayout.RuntimeScript(artifactDir, "fcu_controller_runtime.py")})
	}
	if hasHelper(plan, "frame-contract") {
		path := artifactlayout.RuntimeConfig(artifactDir, "frame_contract_runtime.toml")
		spec := frameSpec(runtimeConfig)
		if err := helpers.WriteFrameContractRuntimeConfig(path, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "frame_contract_runtime_config", Path: path})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "frame_contract_probe.py"), func() (string, error) {
			return helpers.FrameContractProbeScript(spec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "frame_contract_probe_script", Path: artifactlayout.Probe(artifactDir, "frame_contract_probe.py")})
	}
	if hasHelper(plan, "slam-hover") {
		path := artifactlayout.RuntimeConfig(artifactDir, "slam_hover_runtime.toml")
		spec := hoverSpec(runtimeConfig)
		if err := helpers.WriteHoverRuntimeConfig(path, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "slam_hover_runtime_config", Path: path})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "slam_hover_probe.py"), func() (string, error) {
			return helpers.HoverProbeScript(spec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "slam_hover_probe_script", Path: artifactlayout.Probe(artifactDir, "slam_hover_probe.py")})
		if err := writeGeneratedScript(artifactlayout.RuntimeScript(artifactDir, "scan_reference_drift_runtime.py"), func() (string, error) {
			return helpers.ScanReferenceDriftRuntimeScript(helpers.DefaultScanReferenceDriftSpec())
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "scan_reference_drift_runtime_script", Path: artifactlayout.RuntimeScript(artifactDir, "scan_reference_drift_runtime.py")})
		if err := writeGeneratedScript(artifactlayout.RuntimeScript(artifactDir, "scan_reference_cartographer_odom_runtime.py"), func() (string, error) {
			return helpers.ScanReferenceDriftRuntimeScript(helpers.DefaultCartographerScanReferenceOdometrySpec())
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "scan_reference_cartographer_odom_runtime_script", Path: artifactlayout.RuntimeScript(artifactDir, "scan_reference_cartographer_odom_runtime.py")})
		if err := writeGeneratedScript(artifactlayout.RuntimeScript(artifactDir, "scan_reference_correction_runtime.py"), func() (string, error) {
			return helpers.ScanReferenceCorrectionRuntimeScript(helpers.DefaultScanReferenceCorrectionSpec())
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "scan_reference_correction_runtime_script", Path: artifactlayout.RuntimeScript(artifactDir, "scan_reference_correction_runtime.py")})
		if err := writeGeneratedScript(artifactlayout.RuntimeScript(artifactDir, "external_nav_source_selector_runtime.py"), func() (string, error) {
			return helpers.ExternalNavSourceSelectorRuntimeScript(helpers.DefaultExternalNavSourceSelectorSpec())
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "external_nav_source_selector_runtime_script", Path: artifactlayout.RuntimeScript(artifactDir, "external_nav_source_selector_runtime.py")})
		if err := writeGeneratedScript(artifactlayout.RuntimeScript(artifactDir, "hover_mission_runtime.py"), func() (string, error) {
			return helpers.HoverMissionRuntimeScript(hoverMissionSpec(runtimeConfig), plan.DurationSec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "hover_mission_runtime_script", Path: artifactlayout.RuntimeScript(artifactDir, "hover_mission_runtime.py")})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "startup_readiness_probe.py"), func() (string, error) {
			return helpers.StartupReadinessProbeScript(hoverSpec(runtimeConfig))
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "startup_readiness_probe_script", Path: artifactlayout.Probe(artifactDir, "startup_readiness_probe.py")})
		notesPath := artifactlayout.Audit(artifactDir, "motion_foxglove_notes.md")
		if err := os.WriteFile(notesPath, []byte(helpers.MotionFoxgloveNotes(helpers.DefaultMotionGateSpec())), 0o644); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "foxglove_notes", Path: notesPath})
	}
	if hasHelper(plan, "slam-only") {
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "slam_only_probe.py"), func() (string, error) {
			return helpers.SlamOnlyProbeScript(helpers.DefaultSlamOnlySpec(), plan.DurationSec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "slam_only_probe_script", Path: artifactlayout.Probe(artifactDir, "slam_only_probe.py")})
	}
	if hasHelper(plan, "exploration-workflow") {
		path := artifactlayout.RuntimeConfig(artifactDir, "exploration_runtime.toml")
		spec := explorationSpec(runtimeConfig)
		if err := helpers.WriteExplorationRuntimeConfig(path, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "exploration_runtime_config", Path: path})
		if err := writeGeneratedScript(artifactlayout.RuntimeScript(artifactDir, "exploration_workflow_runtime.py"), func() (string, error) {
			return helpers.ExplorationWorkflowRuntimeScript(spec, plan.DurationSec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "exploration_runtime_script", Path: artifactlayout.RuntimeScript(artifactDir, "exploration_workflow_runtime.py")})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "exploration_probe.py"), func() (string, error) {
			return helpers.ExplorationProbeScript(spec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "exploration_probe_script", Path: artifactlayout.Probe(artifactDir, "exploration_probe.py")})
	}
	if hasHelper(plan, "nav2-navigation-workflow") {
		spec := nav2NavigationSpec(runtimeConfig)
		paramsPath := artifactlayout.RuntimeConfig(artifactDir, "nav2_params.yaml")
		if err := helpers.WriteNav2ParamsYAML(paramsPath, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "nav2_params", Path: paramsPath})
		adapterPath := artifactlayout.RuntimeConfig(artifactDir, "navigation_adapter_runtime.toml")
		if err := helpers.WriteNavigationAdapterRuntimeConfig(adapterPath, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "navigation_adapter_runtime_config", Path: adapterPath})
		foxglovePath := artifactlayout.RuntimeConfig(artifactDir, "navigation_foxglove_lite_profile.json")
		if err := helpers.WriteNavigationFoxgloveLiteProfile(foxglovePath, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "navigation_foxglove_lite_profile", Path: foxglovePath})
		if err := writeGeneratedScript(artifactlayout.RuntimeScript(artifactDir, "navigation_adapter_runtime.py"), func() (string, error) {
			return helpers.NavigationAdapterRuntimeScript(spec, plan.DurationSec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "navigation_adapter_runtime_script", Path: artifactlayout.RuntimeScript(artifactDir, "navigation_adapter_runtime.py")})
		if err := writeGeneratedScript(artifactlayout.RuntimeScript(artifactDir, "navigation_mission_runtime.py"), func() (string, error) {
			return helpers.NavigationMissionRuntimeScript(spec, plan.DurationSec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "navigation_mission_runtime_script", Path: artifactlayout.RuntimeScript(artifactDir, "navigation_mission_runtime.py")})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "nav2_lifecycle_probe.py"), func() (string, error) {
			return helpers.Nav2LifecycleProbeScript(spec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "nav2_lifecycle_probe_script", Path: artifactlayout.Probe(artifactDir, "nav2_lifecycle_probe.py")})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "costmap_health_probe.py"), func() (string, error) {
			return helpers.CostmapHealthProbeScript(spec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "costmap_health_probe_script", Path: artifactlayout.Probe(artifactDir, "costmap_health_probe.py")})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "navigation_status_probe.py"), func() (string, error) {
			return helpers.NavigationStatusProbeScript(spec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "navigation_status_probe_script", Path: artifactlayout.Probe(artifactDir, "navigation_status_probe.py")})
	}
	if hasHelper(plan, "scan-stabilization") {
		path := artifactlayout.RuntimeConfig(artifactDir, "scan_stabilization_runtime.toml")
		spec := scanStabilizationSpec(runtimeConfig)
		if err := helpers.WriteScanStabilizationRuntimeConfig(path, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "scan_stabilization_runtime_config", Path: path})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "stabilization_status_probe.py"), func() (string, error) {
			return helpers.StabilizationStatusProbeScript(spec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "stabilization_status_probe_script", Path: artifactlayout.Probe(artifactDir, "stabilization_status_probe.py")})
	}
	if hasHelper(plan, "scan-robustness-workflow") {
		path := artifactlayout.RuntimeConfig(artifactDir, "scan_robustness_runtime.toml")
		spec := scanRobustnessSpec(runtimeConfig)
		if err := helpers.WriteScanRobustnessRuntimeConfig(path, spec); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "scan_robustness_runtime_config", Path: path})
		bridge := artifactlayout.RuntimeConfig(artifactDir, "scan_robustness_bridge_override.yaml")
		if err := helpers.WriteScanRobustnessBridgeOverride(bridge, runtimeConfig.AirframeDisturbance.IMUInputTopic); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "scan_robustness_bridge_override", Path: bridge})
		if err := writeGeneratedScript(artifactlayout.Probe(artifactDir, "airframe_disturbance_probe.py"), func() (string, error) {
			return helpers.AirframeDisturbanceProbeScript(spec)
		}); err != nil {
			return nil, err
		}
		generated = append(generated, GeneratedRuntimeArtifact{Type: "airframe_disturbance_probe_script", Path: artifactlayout.Probe(artifactDir, "airframe_disturbance_probe.py")})
	}
	return generated, nil
}

func publishesOfficialMazeOverlayTask(taskID string) bool {
	switch taskID {
	case "hover", "exploration", "navigation", "scan-robustness":
		return true
	default:
		return false
	}
}

func isHoverSlamRuntimeTask(taskID string) bool {
	switch taskID {
	case "hover", "hover-slam-only":
		return true
	default:
		return false
	}
}

func hoverExternalNavInputOdomTopic(runtimeConfig config.TaskRuntimeConfig) string {
	if topic := strings.TrimSpace(runtimeConfig.SlamHover.ExternalNavInputOdomTopic); topic != "" {
		return topic
	}
	return helpers.DefaultExternalNavSourceSelectorSpec().OutputOdomTopic
}

func hoverCartographerConfigBasename(runtimeConfig config.TaskRuntimeConfig) string {
	if runtimeConfig.SlamBackend.CartographerConfigurationBasename == helpers.HoverNoOdomPriorConfigBasename {
		return helpers.HoverNoOdomPriorConfigBasename
	}
	return helpers.HoverCartographerConfigBasename
}

func officialMazeSource(project config.ProjectConfig) (string, error) {
	if strings.EqualFold(os.Getenv("NAVLAB_SIM_OVERLAY_SOURCE_MODE"), "fixture") || runningGoTest() {
		return officialMazeFixture()
	}
	workspaceRoot := project.Paths.WorkspaceRoot
	if workspaceRoot == "" {
		workspaceRoot = "."
	}
	path := filepath.Join(workspaceRoot, officialMazeSDFRelativePath)
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read official maze SDF %s: %w", path, err)
	}
	return string(data), nil
}

func officialExternalNavParamSource(project config.ProjectConfig) (string, error) {
	if strings.EqualFold(os.Getenv("NAVLAB_SIM_OVERLAY_SOURCE_MODE"), "fixture") || runningGoTest() {
		return officialExternalNavParamFixture()
	}
	workspaceRoot := project.Paths.WorkspaceRoot
	if workspaceRoot == "" {
		workspaceRoot = "."
	}
	path := filepath.Join(workspaceRoot, officialExternalNavParamRelativePath)
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read official ExternalNav SITL param profile %s: %w", path, err)
	}
	return string(data), nil
}

func mergeExternalNavParamProfile(base string, externalNav string) string {
	owned := paramKeys(externalNav)
	// The official Gazebo iris defaults configure a generic SITL sonar. NavLab's
	// ExternalNav profile owns the FCU-facing rangefinder backend instead.
	owned["SIM_SONAR_SCALE"] = true

	lines := make([]string, 0, len(strings.Split(base, "\n")))
	for _, line := range strings.Split(strings.TrimRight(base, "\n"), "\n") {
		key, ok := paramLineKey(line)
		if ok && (owned[key] || strings.HasPrefix(key, "RNGFND1_")) {
			continue
		}
		lines = append(lines, line)
	}
	return strings.TrimRight(strings.Join(lines, "\n"), "\n") + "\n\n# NavLab SITL ExternalNav profile.\n" + strings.TrimSpace(externalNav) + "\n"
}

func paramKeys(source string) map[string]bool {
	keys := map[string]bool{}
	for _, line := range strings.Split(source, "\n") {
		key, ok := paramLineKey(line)
		if ok {
			keys[key] = true
		}
	}
	return keys
}

func paramLineKey(line string) (string, bool) {
	fields := strings.Fields(line)
	if len(fields) == 0 || strings.HasPrefix(fields[0], "#") {
		return "", false
	}
	return fields[0], true
}

func officialMazeFixture() (string, error) {
	return helpers.RenderStaticHelperTemplate("sdf/fixtures/official_maze.sdf.tmpl")
}

func officialExternalNavParamFixture() (string, error) {
	return helpers.RenderStaticHelperTemplate("parm/official_external_nav.parm.tmpl")
}

func runtimeContainerPath(project config.ProjectConfig, hostPath string) (string, error) {
	workspaceRoot := project.Paths.WorkspaceRoot
	if workspaceRoot == "" {
		workspaceRoot = "."
	}
	absoluteWorkspaceRoot, err := filepath.Abs(workspaceRoot)
	if err != nil {
		return "", err
	}
	containerWorkspace := project.Orchestration.Runtime.Docker.WorkspaceContainerPath
	if containerWorkspace == "" {
		containerWorkspace = "/workspace"
	}
	return containerPath(absoluteWorkspaceRoot, containerWorkspace, hostPath)
}

func officialOverlaySource(project config.ProjectConfig, sourcePath string) (string, error) {
	if strings.EqualFold(os.Getenv("NAVLAB_SIM_OVERLAY_SOURCE_MODE"), "fixture") || runningGoTest() {
		return officialOverlayFixture(sourcePath)
	}
	image, err := resolveImageRef(project, "images.official_baseline")
	if err != nil {
		return "", err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	_ = ctx
	probe, err := simruntime.NewDockerBackend(nil).RunProbe(simruntime.ProbeSpec{
		Name:       "official_overlay_source",
		Image:      image,
		Command:    []string{"cat", sourcePath},
		TimeoutSec: 30,
		Required:   true,
	})
	if err != nil {
		return "", fmt.Errorf("read official overlay source %s from %s: %w: %s", sourcePath, image, err, strings.TrimSpace(probe.Stderr))
	}
	if !probe.OK() {
		return "", fmt.Errorf("read official overlay source %s from %s: return code %d: %s", sourcePath, image, probe.ReturnCode, strings.TrimSpace(probe.Stderr))
	}
	return probe.Stdout, nil
}

func runningGoTest() bool {
	return strings.HasSuffix(os.Args[0], ".test")
}

func officialOverlayFixture(sourcePath string) (string, error) {
	switch sourcePath {
	case helpers.OfficialGazeboIrisParams:
		return helpers.RenderStaticHelperTemplate("parm/official_gazebo_iris.parm.tmpl")
	default:
		return helpers.RenderStaticHelperTemplate("sdf/fixtures/official_iris_with_lidar.sdf.tmpl")
	}
}

func writeGeneratedScript(path string, generate func() (string, error)) error {
	content, err := generate()
	if err != nil {
		return err
	}
	return os.WriteFile(path, []byte(content), 0o755)
}

func hasHelper(plan Plan, id string) bool {
	for _, helper := range plan.Helpers {
		if helper.ID == id {
			return true
		}
	}
	return false
}

func resolveWorkspaceSource(project config.ProjectConfig, relativePath string) (string, error) {
	candidates := []string{}
	if project.Paths.WorkspaceRoot != "" {
		candidates = append(candidates, filepath.Join(project.Paths.WorkspaceRoot, relativePath))
	}
	candidates = append(candidates, relativePath)
	if cwd, err := os.Getwd(); err == nil {
		for dir := cwd; ; dir = filepath.Dir(dir) {
			candidates = append(candidates, filepath.Join(dir, relativePath))
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
		}
	}
	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("workspace source %q not found", relativePath)
}

func sensorSpec(runtimeConfig config.TaskRuntimeConfig) helpers.SensorRuntimeSpec {
	spec := helpers.DefaultSensorRuntimeSpec()
	sensor := runtimeConfig.RangefinderIMU
	spec.X2VirtualSerialLink = sensor.X2VirtualSerialLink
	spec.X2ScanInputTopic = sensor.X2ScanInputTopic
	spec.X2ScanTopic = sensor.X2ScanTopic
	spec.X2StatusTopic = sensor.X2StatusTopic
	spec.RangefinderFrameID = sensor.RangefinderFrameID
	spec.RangefinderScanIdealTopic = sensor.RangefinderScanIdealTopic
	spec.RangefinderRangeTopic = sensor.RangefinderRangeTopic
	spec.RangefinderStatusTopic = sensor.RangefinderStatusTopic
	spec.RangefinderVirtualSerial = sensor.RangefinderVirtualSerialLink
	spec.RangefinderSerialBaud = sensor.RangefinderSerialBaud
	spec.RangefinderRateHz = sensor.RangefinderRateHz
	spec.RangefinderMinDistanceM = sensor.RangefinderMinDistanceM
	spec.RangefinderMaxDistanceM = sensor.RangefinderMaxDistanceM
	spec.RangefinderModelPose = sensor.RangefinderModelPose
	spec.RangefinderModelUpdateHz = sensor.RangefinderModelUpdateRateHz
	if count, err := strconv.Atoi(sensor.RangefinderModelRayCount); err == nil {
		spec.RangefinderModelRayCount = count
	}
	spec.IMUOutputTopic = sensor.IMUOutputTopic
	spec.IMUSourceRoute = sensor.IMUSourceRoute
	spec.IMUSourceTopic = sensor.IMUSourceTopic
	spec.SyntheticFallbackEnabled = sensor.SyntheticFallbackEnabled
	return spec
}

func slamSpec(runtimeConfig config.TaskRuntimeConfig) helpers.SlamRuntimeSpec {
	spec := helpers.DefaultSlamRuntimeSpec()
	slam := runtimeConfig.SlamBackend
	spec.Backend = slam.Backend
	spec.LaunchPackage = slam.LaunchPackage
	spec.LaunchFile = slam.LaunchFile
	spec.CartographerConfigurationBasename = slam.CartographerConfigurationBasename
	spec.ScanTopic = slam.ScanTopic
	spec.IMUTopic = slam.IMUTopic
	spec.OdometryTopic = slam.OdometryTopic
	spec.CartographerTFTopic = slam.CartographerTFTopic
	spec.OdomSourceMode = slam.OdomSourceMode
	spec.SlamOdomTopic = slam.SlamOdomTopic
	spec.SlamStatusTopic = slam.SlamStatusTopic
	spec.ExternalNavStatusTopic = slam.ExternalNavStatusTopic
	spec.MapFrameID = slam.MapFrameID
	spec.OdomFrameID = slam.OdomFrameID
	spec.BaseFrameID = slam.BaseFrameID
	spec.IMUFrameID = slam.IMUFrameID
	spec.LaserFrameID = slam.LaserFrameID
	return spec
}

func fcuSpec(runtimeConfig config.TaskRuntimeConfig) helpers.FCUControllerSpec {
	spec := helpers.DefaultFCUControllerSpec()
	fcu := runtimeConfig.FCUController
	spec.ControlRoute = fcu.ControlRoute
	spec.MAVLinkBootstrap = fcu.MAVLinkBootstrapEndpoint
	spec.MAVLinkBootstrapSourceSystem = fcu.MAVLinkBootstrapSourceSystem
	spec.MAVLinkBootstrapSourceComponent = fcu.MAVLinkBootstrapSourceComponent
	spec.OwnerName = fcu.OwnerName
	spec.OwnerID = fcu.OwnerID
	spec.FCUStateTopic = fcu.FCUStateTopic
	spec.ControllerStatusTopic = fcu.ControllerStatusTopic
	spec.SetpointIntentTopic = fcu.SetpointIntentTopic
	spec.SetpointOutputTopic = fcu.SetpointOutputTopic
	spec.OwnerStatusTopic = fcu.OwnerStatusTopic
	spec.TimeTopic = fcu.TimeTopic
	spec.PrearmService = fcu.PrearmService
	spec.ModeSwitchService = fcu.ModeSwitchService
	spec.ArmService = fcu.ArmService
	spec.TakeoffService = fcu.TakeoffService
	spec.CmdVelTopic = fcu.CmdVelTopic
	spec.PoseTopic = fcu.PoseTopic
	spec.TwistTopic = fcu.TwistTopic
	spec.StatusTopic = fcu.StatusTopic
	spec.RangefinderRangeTopic = fcu.RangefinderRangeTopic
	spec.RangefinderStatusTopic = fcu.RangefinderStatusTopic
	spec.IMUTopic = fcu.IMUTopic
	spec.SlamOdomTopic = fcu.SlamOdomTopic
	spec.SlamStatusTopic = fcu.SlamStatusTopic
	if runtimeConfig.FrameContract.MapFrameID != "" {
		spec.MapFrameID = runtimeConfig.FrameContract.MapFrameID
	}
	if runtimeConfig.FrameContract.OdomFrameID != "" {
		spec.OdomFrameID = runtimeConfig.FrameContract.OdomFrameID
	}
	if runtimeConfig.FrameContract.BaseFrameID != "" {
		spec.BaseFrameID = runtimeConfig.FrameContract.BaseFrameID
	}
	if runtimeConfig.FrameContract.LaserFrameID != "" {
		spec.LaserFrameID = runtimeConfig.FrameContract.LaserFrameID
	}
	spec.TakeoffAltM = fcu.TakeoffAltM
	spec.TakeoffMinHeightM = fcu.TakeoffMinHeightM
	spec.TakeoffMinHeightRatio = fcu.TakeoffMinHeightRatio
	spec.ReadinessTimeoutSec = fcu.ReadinessTimeoutSec
	spec.HoldAfterReadySec = fcu.HoldAfterReadySec
	spec.RequireSlamBackend = fcu.RequireSlamBackend
	return spec
}

func landingPolicyForTask(runtimeConfig config.TaskRuntimeConfig, taskID string) string {
	policy := ""
	switch taskID {
	case "hover":
		policy = runtimeConfig.Landing.HoverPolicy
	case "exploration":
		policy = runtimeConfig.Landing.ExplorationPolicy
	case "navigation":
		policy = runtimeConfig.Landing.NavigationPolicy
	case "scan-robustness":
		policy = runtimeConfig.Landing.ScanRobustnessPolicy
	}
	if policy == "" {
		policy = runtimeConfig.Landing.DefaultPolicy
	}
	if policy == "" {
		policy = helpers.PolicyLandInPlace
	}
	return policy
}

func frameSpec(runtimeConfig config.TaskRuntimeConfig) helpers.FrameContractSpec {
	spec := helpers.DefaultFrameContractSpec()
	frame := runtimeConfig.FrameContract
	spec.RequiredFrames = frame.RequiredFrames
	spec.MapFrameID = frame.MapFrameID
	spec.OdomFrameID = frame.OdomFrameID
	spec.BaseFrameID = frame.BaseFrameID
	spec.IMUFrameID = frame.IMUFrameID
	spec.LaserFrameID = frame.LaserFrameID
	spec.RangefinderFrameID = frame.RangefinderFrameID
	spec.ScanTopic = frame.ScanTopic
	spec.IMUTopic = frame.IMUTopic
	spec.RangefinderRangeTopic = frame.RangefinderRangeTopic
	spec.RangefinderStatusTopic = frame.RangefinderStatusTopic
	spec.FCUPoseTopic = frame.FCUPoseTopic
	spec.FCUTwistTopic = frame.FCUTwistTopic
	spec.FCUStatusTopic = frame.FCUStatusTopic
	spec.CmdVelTopic = frame.CmdVelTopic
	spec.SlamOdomTopic = frame.SlamOdomTopic
	spec.SlamStatusTopic = frame.SlamStatusTopic
	spec.TruthDiagnosticTopic = frame.TruthDiagnosticTopic
	spec.ControllerStatusTopic = frame.ControllerStatusTopic
	spec.SetpointOutputTopic = frame.SetpointOutputTopic
	spec.OwnerStatusTopic = frame.OwnerStatusTopic
	spec.StatusTopic = frame.StatusTopic
	spec.MaxDynamicTFAgeSec = frame.MaxDynamicTFAgeSec
	spec.MinScanValidRatio = frame.MinScanValidRatio
	spec.MaxRangefinderHeightErr = frame.MaxRangefinderHeightErrorM
	spec.MaxDirectionErrorRad = frame.MaxDirectionErrorRad
	spec.ProbeDurationSec = frame.ProbeDurationSec
	return spec
}

func hoverSpec(runtimeConfig config.TaskRuntimeConfig) helpers.SlamHoverSpec {
	spec := helpers.DefaultSlamHoverSpec()
	hover := runtimeConfig.SlamHover
	spec.SlamOdomTopic = hover.SlamOdomTopic
	spec.SlamStatusTopic = hover.SlamStatusTopic
	spec.ExternalNavStatusTopic = hover.ExternalNavStatusTopic
	spec.FCUPoseTopic = hover.FCUPoseTopic
	spec.FCUTwistTopic = hover.FCUTwistTopic
	spec.FCUStatusTopic = hover.FCUStatusTopic
	spec.CmdVelTopic = hover.CmdVelTopic
	spec.RangefinderRangeTopic = hover.RangefinderRangeTopic
	spec.RangefinderStatusTopic = hover.RangefinderStatusTopic
	spec.IMUTopic = hover.IMUTopic
	spec.TruthDiagnosticTopic = hover.TruthDiagnosticTopic
	spec.ControllerStatusTopic = hover.ControllerStatusTopic
	spec.SetpointIntentTopic = hover.SetpointIntentTopic
	spec.SetpointOutputTopic = hover.SetpointOutputTopic
	spec.OwnerStatusTopic = hover.OwnerStatusTopic
	spec.HoverStatusTopic = hover.HoverStatusTopic
	spec.VehicleMarkerTopic = hover.VehicleMarkerTopic
	spec.VehicleMarkerPoseTopic = hover.VehicleMarkerPoseTopic
	spec.VehicleMarkerFrameID = hover.VehicleMarkerFrameID
	spec.VehicleMarkerRateHz = hover.VehicleMarkerRateHz
	spec.SettleWindowSec = hover.SettleWindowSec
	spec.HoverWindowSec = hover.HoverWindowSec
	spec.FinalHoldWindowSec = hover.FinalHoldWindowSec
	spec.MaxHoverHorizontalDrift = hover.MaxHoverHorizontalDriftM
	spec.HoverSpanTargetM = hover.HoverSpanTargetM
	spec.HoverSpanHardCapM = hover.HoverSpanHardCapM
	spec.MaxHoverAltitudeError = hover.MaxHoverAltitudeErrorM
	spec.MaxHoverYawDriftRad = hover.MaxHoverYawDriftRad
	spec.MaxStopDriftM = hover.MaxStopDriftM
	spec.StartupReadinessTimeoutSec = hover.StartupReadinessPolicy.TimeoutSec
	spec.StartupReadinessGraceSec = hover.StartupReadinessPolicy.GraceSec
	spec.StartupReadinessProgressWindowSec = hover.StartupReadinessPolicy.ProgressWindowSec
	spec.StartupReadinessRestartLimit = hover.StartupReadinessPolicy.RestartLimit
	return spec
}

func hoverMissionSpec(runtimeConfig config.TaskRuntimeConfig) helpers.HoverMissionRuntimeSpec {
	spec := helpers.DefaultHoverMissionRuntimeSpec()
	fcu := runtimeConfig.FCUController
	hover := runtimeConfig.SlamHover
	landing := runtimeConfig.Landing
	spec.Endpoint = fcu.MAVLinkBootstrapEndpoint
	spec.SourceSystem = fcu.MAVLinkBootstrapSourceSystem
	spec.SourceComponent = fcu.MAVLinkBootstrapSourceComponent
	spec.Mode = "GUIDED"
	if fcu.GuidedMode != 0 {
		spec.Mode = "GUIDED"
	}
	spec.TakeoffAltM = fcu.TakeoffAltM
	spec.HoverSettleSec = hover.SettleWindowSec
	spec.HoverHoldSec = hover.HoverWindowSec
	spec.HoverHealthMinObservationSec = hover.HoverHealthMinObservationSec
	spec.HoverHealthStableRequiredSec = hover.HoverHealthStableRequiredSec
	spec.HoverHealthMaxWaitSec = hover.HoverHealthMaxWaitSec
	spec.StartupReadinessTimeoutSec = hover.StartupReadinessPolicy.TimeoutSec
	spec.StartupReadinessGraceSec = hover.StartupReadinessPolicy.GraceSec
	spec.StartupReadinessProgressWindowSec = hover.StartupReadinessPolicy.ProgressWindowSec
	spec.StartupReadinessRestartLimit = hover.StartupReadinessPolicy.RestartLimit
	spec.OperatorConfirmRequired = hover.OperatorConfirmRequired
	spec.OperatorConfirmTimeoutSec = hover.OperatorConfirmTimeoutSec
	spec.MaxHorizontalDriftM = hover.MaxHoverHorizontalDriftM
	spec.HoverSpanTargetM = hover.HoverSpanTargetM
	spec.HoverSpanHardCapM = hover.HoverSpanHardCapM
	spec.MaxAltitudeDriftM = hover.MaxHoverAltitudeErrorM
	if spec.StartupReadinessTimeoutSec > 0 {
		spec.MaxWaitReadySec = spec.StartupReadinessTimeoutSec
	}
	spec.StatusTopic = hover.HoverStatusTopic
	spec.LandingStatusTopic = landing.LandingStatusTopic
	spec.LandingIntentTopic = landing.LandingIntentTopic
	spec.LandingPolicy = landingPolicyForTask(runtimeConfig, "hover")
	spec.ExternalNavStatusTopic = hover.ExternalNavStatusTopic
	spec.PreLandHoldSec = landing.PreLandHoldSec
	if landing.CompletionGraceSec > 0 {
		spec.ForceDisarmGraceSec = landing.CompletionGraceSec
	}
	spec.MaxLandingDurationSec = landing.MaxLandingDurationSec
	if landing.SetpointLookaheadSec > 0 {
		spec.LandingSetpointLookaheadSec = landing.SetpointLookaheadSec
	}
	if landing.MaxDescentRateMPS > 0 {
		spec.MaxLandingDescentRateMPS = landing.MaxDescentRateMPS
	}
	spec.TouchdownAltitudeM = landing.TouchdownAltitudeM
	spec.TouchdownVerticalSpeedMPS = landing.TouchdownVerticalSpeedMPS
	spec.RequireDisarm = landing.RequireDisarm
	spec.RequireMotorsSafe = landing.RequireMotorsSafe
	return spec
}

func explorationSpec(runtimeConfig config.TaskRuntimeConfig) helpers.ExplorationWorkflowSpec {
	spec := helpers.DefaultExplorationWorkflowSpec()
	exploration := runtimeConfig.ExplorationGate
	spec.Strategy = exploration.Strategy
	spec.ExplorationWindowSec = exploration.ExplorationWindowSec
	spec.MotionSpeedMPS = exploration.MotionSpeedMPS
	spec.MinAcceptedGoals = exploration.MinAcceptedGoals
	spec.MinPathLengthM = exploration.MinPathLengthM
	spec.ControllerStatusTopic = exploration.ControllerStatusTopic
	spec.SetpointIntentTopic = exploration.SetpointIntentTopic
	spec.SetpointOutputTopic = exploration.SetpointOutputTopic
	spec.SlamOdomTopic = exploration.SlamOdomTopic
	spec.ExplorationStatusTopic = exploration.ExplorationStatusTopic
	return spec
}

func nav2NavigationSpec(runtimeConfig config.TaskRuntimeConfig) helpers.Nav2NavigationSpec {
	spec := helpers.DefaultNav2NavigationSpec()
	nav2 := runtimeConfig.Nav2
	costmap := runtimeConfig.Nav2.Costmap
	adapter := runtimeConfig.NavigationAdapter
	mission := runtimeConfig.NavigationMission
	spec.Profile = nav2.Profile
	spec.GlobalFrame = nav2.GlobalFrame
	spec.OdomFrame = nav2.OdomFrame
	spec.BaseFrame = nav2.BaseFrame
	spec.ScanTopic = nav2.ScanTopic
	spec.MapTopic = nav2.MapTopic
	spec.CmdVelTopic = nav2.CmdVelTopic
	spec.BTXML = nav2.BTXML
	spec.PlannerPlugin = nav2.PlannerPlugin
	spec.ControllerPlugin = nav2.ControllerPlugin
	spec.UseSimTime = nav2.UseSimTime
	spec.GlobalCostmapTopic = costmap.GlobalCostmapTopic
	spec.LocalCostmapTopic = costmap.LocalCostmapTopic
	spec.RequiredCostmapLayers = append([]string(nil), costmap.RequiredLayers...)
	spec.MaxCostmapAgeSec = costmap.MaxCostmapAgeSec
	spec.MinObstacleCells = costmap.MinObstacleCells
	spec.MaxUnknownRatio = costmap.MaxUnknownRatio
	spec.InflationRadiusM = costmap.InflationRadiusM
	spec.FootprintRadiusM = costmap.FootprintRadiusM
	spec.CostmapHealthTopic = costmap.HealthTopic
	spec.SetpointIntentTopic = adapter.SetpointIntentTopic
	spec.AdapterStatusTopic = adapter.StatusTopic
	spec.MaxXYSpeedMPS = adapter.MaxXYSpeedMPS
	spec.MaxYawRateDPS = adapter.MaxYawRateDPS
	spec.MaxAccelMPS2 = adapter.MaxAccelMPS2
	spec.FixedAltitudeM = adapter.FixedAltitudeM
	spec.StopOnStaleCostmap = adapter.StopOnStaleCostmap
	spec.StopOnStaleSlam = adapter.StopOnStaleSlam
	spec.NavigationStatusTopic = mission.StatusTopic
	spec.NavigationEventsTopic = mission.EventsTopic
	spec.NavigationGoalTopic = mission.GoalTopic
	spec.NavigationPathTopic = mission.PathTopic
	spec.NavigationRecoveryTopic = mission.RecoveryTopic
	spec.Strategy = mission.Strategy
	spec.CompletionPolicy = navigationCompletionPolicy(runtimeConfig)
	spec.GoalFrame = mission.GoalFrame
	spec.NavigationWindowSec = mission.NavigationWindowSec
	spec.MaxGoalRadiusM = mission.MaxGoalRadiusM
	spec.MinClearanceM = mission.MinClearanceM
	spec.MinCoverageGrowth = mission.MinCoverageGrowth
	spec.MinPathLengthM = mission.MinPathLengthM
	spec.MinAcceptedGoals = mission.MinAcceptedGoals
	spec.MaxRecoveryCount = mission.MaxRecoveryCount
	spec.ReturnHomePolicy = mission.ReturnHomePolicy
	spec.UsesGazeboTruthAsInput = mission.UsesGazeboTruthAsInput
	spec.ExitGoal = navigationGoalSpec(mission.ExitGoal)
	spec.BoundedGoals = navigationGoalSpecs(mission.BoundedGoals)
	spec.HomeGoal = navigationGoalSpec(mission.HomeGoal)
	spec.SlamOdomTopic = runtimeConfig.SlamBackend.SlamOdomTopic
	spec.SlamStatusTopic = runtimeConfig.SlamBackend.SlamStatusTopic
	spec.ControllerStatusTopic = runtimeConfig.FCUController.ControllerStatusTopic
	spec.OwnerStatusTopic = runtimeConfig.FCUController.OwnerStatusTopic
	spec.ScanStabilizationStatusTopic = runtimeConfig.ScanStabilization.StatusTopic
	spec.LandingStatusTopic = runtimeConfig.Landing.LandingStatusTopic
	return spec
}

func navigationGoalSpecs(goals []config.NavigationGoalConfig) []helpers.NavigationGoalSpec {
	out := make([]helpers.NavigationGoalSpec, 0, len(goals))
	for _, goal := range goals {
		out = append(out, navigationGoalSpec(goal))
	}
	return out
}

func navigationGoalSpec(goal config.NavigationGoalConfig) helpers.NavigationGoalSpec {
	return helpers.NavigationGoalSpec{
		ID:     goal.ID,
		XM:     goal.XM,
		YM:     goal.YM,
		YawRad: goal.YawRad,
	}
}

func navigationCompletionPolicy(runtimeConfig config.TaskRuntimeConfig) string {
	if runtimeConfig.NavigationMission.CompletionPolicy != "" {
		return runtimeConfig.NavigationMission.CompletionPolicy
	}
	if runtimeConfig.Landing.NavigationPolicy != "" {
		return runtimeConfig.Landing.NavigationPolicy
	}
	return runtimeConfig.Landing.ExplorationPolicy
}

func scanStabilizationSpec(runtimeConfig config.TaskRuntimeConfig) helpers.ScanStabilizationSpec {
	spec := helpers.DefaultScanStabilizationSpec()
	stabilization := runtimeConfig.ScanStabilization
	spec.Mode = stabilization.Mode
	spec.InputScanTopic = stabilization.InputScanTopic
	spec.OutputScanTopic = stabilization.OutputScanTopic
	spec.StatusTopic = stabilization.StatusTopic
	spec.AttitudeSourceTopic = stabilization.AttitudeSourceTopic
	spec.MaxRejectedBeamRatio = stabilization.MaxRejectedBeamRatio
	spec.MinRetainedBeamRatio = stabilization.MinRetainedBeamRatio
	spec.MaxFloorHitRiskBeamRatio = stabilization.MaxFloorHitRiskBeamRatio
	spec.MaxVerticalProjectionErrorM = stabilization.MaxVerticalProjectionErrorM
	spec.MaxAttitudeSourceAgeMS = stabilization.MaxAttitudeSourceAgeMS
	spec.PassthroughTiltDeg = stabilization.PassthroughTiltDeg
	spec.CompensationTiltDeg = stabilization.CompensationTiltDeg
	spec.HardDropTiltDeg = stabilization.HardDropTiltDeg
	spec.UsesGazeboTruthAsInput = stabilization.UsesGazeboTruthAsInput
	spec.ScanStabilizationClaim = stabilization.ScanStabilizationClaim
	spec.ReplayReadinessTimeoutSec = runtimeConfig.ScanStabilizationGate.ReplayReadinessTimeoutSec
	spec.ControllerSummaryTimeoutSec = runtimeConfig.ScanStabilizationGate.ControllerSummaryTimeoutSec
	return spec
}

func scanRobustnessSpec(runtimeConfig config.TaskRuntimeConfig) helpers.ScanRobustnessWorkflowSpec {
	spec := helpers.DefaultScanRobustnessWorkflowSpec()
	disturbance := runtimeConfig.AirframeDisturbance
	gate := runtimeConfig.AirframeDisturbanceGate
	spec.Profile = disturbance.Profile
	spec.RequiredProfiles = gate.RequiredProfiles
	spec.FCUStatusTopic = runtimeConfig.FCUController.ControllerStatusTopic
	if spec.FCUStatusTopic == "" {
		spec.FCUStatusTopic = gate.FCUStatusTopic
	}
	spec.StabilizedScanTopic = runtimeConfig.ScanStabilization.OutputScanTopic
	spec.DisturbanceStatusTopic = disturbance.StatusTopic
	spec.IMURawTopic = disturbance.IMUInputTopic
	spec.IMUOutputTopic = disturbance.IMUOutputTopic
	spec.LandingPolicy = runtimeConfig.Landing.ScanRobustnessPolicy
	return spec
}
