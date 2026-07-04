package tasks

import (
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/pelletier/go-toml/v2"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func TestGenerateRuntimeArtifactsFromConfiguredTasks(t *testing.T) {
	t.Setenv("NAVLAB_SIM_OVERLAY_SOURCE_MODE", "fixture")
	tests := []struct {
		name      string
		taskID    string
		wantFiles []string
	}{
		{
			name:   "hover",
			taskID: "hover",
			wantFiles: []string{
				"official_maze_overlay_runtime.py",
				"bridge_override.yaml",
				"vendor_profile.yaml",
				"model_overlay.sdf",
				"gazebo-iris-rangefinder.parm",
				"gazebo_sensor_runtime.toml",
				"rangefinder_probe.py",
				"imu_probe.py",
				"slam_runtime.toml",
				helpers.HoverNoOdomPriorConfigBasename,
				"external_nav_bridge_params.yaml",
				"frame_contract_runtime.toml",
				"frame_contract_probe.py",
				"slam_hover_runtime.toml",
				"scan_reference_drift_runtime.py",
				"scan_reference_cartographer_odom_runtime.py",
				"scan_reference_correction_runtime.py",
				"external_nav_source_selector_runtime.py",
				"hover_mission_runtime.py",
				"startup_readiness_probe.py",
				"slam_hover_probe.py",
			},
		},
		{
			name:   "hover-slam-only",
			taskID: "hover-slam-only",
			wantFiles: []string{
				"bridge_override.yaml",
				"vendor_profile.yaml",
				"model_overlay.sdf",
				"gazebo-iris-rangefinder.parm",
				"gazebo_sensor_runtime.toml",
				"rangefinder_probe.py",
				"imu_probe.py",
				"slam_runtime.toml",
				helpers.HoverCartographerConfigBasename,
				"external_nav_bridge_params.yaml",
				"slam_only_probe.py",
			},
		},
		{
			name:   "exploration",
			taskID: "exploration",
			wantFiles: []string{
				"official_maze_overlay_runtime.py",
				"exploration_runtime.toml",
				"exploration_workflow_runtime.py",
				"exploration_probe.py",
			},
		},
		{
			name:   "navigation",
			taskID: "navigation",
			wantFiles: []string{
				"official_maze_overlay_runtime.py",
				"nav2_params.yaml",
				"navigation_adapter_runtime.toml",
				"navigation_foxglove_lite_profile.json",
				"navigation_adapter_runtime.py",
				"navigation_mission_runtime.py",
				"nav2_lifecycle_probe.py",
				"costmap_health_probe.py",
				"navigation_status_probe.py",
			},
		},
		{
			name:   "scan-robustness",
			taskID: "scan-robustness",
			wantFiles: []string{
				"official_maze_overlay_runtime.py",
				"scan_stabilization_runtime.toml",
				"stabilization_status_probe.py",
				"scan_robustness_runtime.toml",
				"scan_robustness_bridge_override.yaml",
				"airframe_disturbance_probe.py",
			},
		},
	}

	loader := config.NewLoader("../../config.toml")
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}
	registry := DefaultRegistry()
	helperRegistry := helpers.DefaultRegistry()

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			taskConfig, err := loader.LoadTask(project, tt.taskID)
			if err != nil {
				t.Fatalf("LoadTask(%q) error = %v", tt.taskID, err)
			}
			runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
			if err != nil {
				t.Fatalf("BuildTaskRuntimeConfig(%q) error = %v", tt.taskID, err)
			}
			task, err := registry.ConfigureOne(taskConfig)
			if err != nil {
				t.Fatalf("ConfigureOne(%q) error = %v", tt.taskID, err)
			}
			plan, err := task.Plan(PlanOptions{}, helperRegistry)
			if err != nil {
				t.Fatalf("Plan(%q) error = %v", tt.taskID, err)
			}
			runtimeConfig, err = ApplySimulationProfile(runtimeConfig, plan)
			if err != nil {
				t.Fatalf("ApplySimulationProfile(%q) error = %v", tt.taskID, err)
			}

			artifactDir := t.TempDir()
			generated, err := GenerateRuntimeArtifacts(project, plan, runtimeConfig, artifactDir)
			if err != nil {
				t.Fatalf("GenerateRuntimeArtifacts(%q) error = %v", tt.taskID, err)
			}
			if len(generated) == 0 {
				t.Fatalf("GenerateRuntimeArtifacts(%q) generated no artifacts", tt.taskID)
			}
			generatedByBase := map[string]string{}
			for _, artifact := range generated {
				generatedByBase[filepath.Base(artifact.Path)] = artifact.Path
			}
			for _, name := range tt.wantFiles {
				path, ok := generatedByBase[filepath.Base(name)]
				if !ok {
					t.Fatalf("generated artifact %s missing from %#v", name, generated)
				}
				assertFileExists(t, path)
			}
			if tt.taskID == "hover" {
				assertModelOverlayUsesNavLabRangefinderModel(t, artifactlayout.RuntimeConfig(artifactDir, "model_overlay.sdf"))
				assertParamOverlayContainsExternalNavAndRangefinder(t, artifactlayout.RuntimeConfig(artifactDir, "gazebo-iris-rangefinder.parm"))
				assertSensorRuntimeUsesBenewakeSerial(t, artifactlayout.RuntimeConfig(artifactDir, "gazebo_sensor_runtime.toml"))
				assertSlamRuntimeExternalNavInput(t, artifactlayout.RuntimeConfig(artifactDir, "slam_runtime.toml"), "/slam/odom")
				assertSlamRuntimeCartographerConfig(t, artifactlayout.RuntimeConfig(artifactDir, "slam_runtime.toml"), helpers.HoverNoOdomPriorConfigBasename)
				assertExternalNavBridgeInput(t, artifactlayout.RuntimeConfig(artifactDir, "external_nav_bridge_params.yaml"), "/slam/odom")
				assertCartographerConfigUsesOdometry(t, artifactlayout.RuntimeConfig(artifactDir, helpers.HoverNoOdomPriorConfigBasename), false)
				assertScanReferenceCartographerOdomRuntime(t, artifactlayout.RuntimeScript(artifactDir, "scan_reference_cartographer_odom_runtime.py"))
				assertHoverOfficialMazeOverlayAvoidsMapAlias(t, artifactlayout.RuntimeScript(artifactDir, "official_maze_overlay_runtime.py"))
				assertFileMissing(t, filepath.Join(artifactDir, "hover_cartographer_odom_prior.py"))
				assertProbeScriptRetriesTopicEcho(t, artifactlayout.Probe(artifactDir, "frame_contract_probe.py"))
				assertProbeScriptRetriesTopicEcho(t, artifactlayout.Probe(artifactDir, "slam_hover_probe.py"))
				assertHoverProbeKeepsLandingStatusOptional(t, artifactlayout.Probe(artifactDir, "slam_hover_probe.py"))
				assertHoverMissionRuntimeUsesAPLandPolicy(t, artifactlayout.RuntimeScript(artifactDir, "hover_mission_runtime.py"))
				assertStartupReadinessPolicyEchoed(t, artifactlayout.RuntimeConfig(artifactDir, "slam_hover_runtime.toml"), artifactlayout.RuntimeScript(artifactDir, "hover_mission_runtime.py"))
			}
			if tt.taskID == "hover-slam-only" {
				assertModelOverlayUsesNavLabRangefinderModel(t, artifactlayout.RuntimeConfig(artifactDir, "model_overlay.sdf"))
				assertHoverSlamRuntimeUsesCartographerAdapter(t, artifactlayout.RuntimeConfig(artifactDir, "slam_runtime.toml"))
				assertHoverExternalNavUsesCartographerAdapter(t, artifactlayout.RuntimeConfig(artifactDir, "external_nav_bridge_params.yaml"))
				assertCopiedHoverCartographerConfig(t, artifactlayout.RuntimeConfig(artifactDir, helpers.HoverCartographerConfigBasename))
				assertFileExists(t, artifactlayout.Probe(artifactDir, "slam_only_probe.py"))
				assertFileMissing(t, filepath.Join(artifactDir, "hover_cartographer_odom_prior.py"))
				assertFileMissing(t, artifactlayout.RuntimeScript(artifactDir, "official_maze_overlay_runtime.py"))
			}
		})
	}
}

func TestGenerateRuntimeArtifactsKeepsHoverRootReadable(t *testing.T) {
	t.Setenv("NAVLAB_SIM_OVERLAY_SOURCE_MODE", "fixture")
	loader := config.NewLoader("../../config.toml")
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}
	taskConfig, err := loader.LoadTask(project, "hover")
	if err != nil {
		t.Fatalf("LoadTask(hover) error = %v", err)
	}
	runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		t.Fatalf("BuildTaskRuntimeConfig(hover) error = %v", err)
	}
	task, err := DefaultRegistry().ConfigureOne(taskConfig)
	if err != nil {
		t.Fatalf("ConfigureOne(hover) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(hover) error = %v", err)
	}
	runtimeConfig, err = ApplySimulationProfile(runtimeConfig, plan)
	if err != nil {
		t.Fatalf("ApplySimulationProfile(hover) error = %v", err)
	}

	artifactDir := t.TempDir()
	if _, err := GenerateRuntimeArtifacts(project, plan, runtimeConfig, artifactDir); err != nil {
		t.Fatalf("GenerateRuntimeArtifacts(hover) error = %v", err)
	}
	entries, err := os.ReadDir(artifactDir)
	if err != nil {
		t.Fatal(err)
	}
	allowedDirs := map[string]bool{
		"audits": true, "dag": true, "probes": true, "runtime": true, "profiles": true, "rosbag": true, "sitl": true,
	}
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() {
			if !allowedDirs[name] {
				t.Fatalf("unexpected root directory %q", name)
			}
			continue
		}
		if !artifactlayout.RootEntries[name] {
			t.Fatalf("unexpected root file %q; generated runtime/probe/audit files must be nested", name)
		}
	}
	assertFileExists(t, artifactlayout.RuntimeScript(artifactDir, "hover_mission_runtime.py"))
	assertFileExists(t, artifactlayout.RuntimeConfig(artifactDir, "slam_runtime.toml"))
	assertFileExists(t, artifactlayout.Probe(artifactDir, "slam_hover_probe.py"))
	assertFileExists(t, artifactlayout.Audit(artifactDir, "motion_foxglove_notes.md"))
}

func assertHoverMissionRuntimeUsesAPLandPolicy(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated hover mission runtime script: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		`\"landing_policy\":\"ap_land_mode_after_hover\"`,
		`\"force_disarm_grace_sec\":3`,
		`\"hover_settle_sec\":8`,
		`\"max_horizontal_drift_m\":0.1`,
		`\"hover_span_target_m\":0.1`,
		`\"hover_span_hard_cap_m\":0.15`,
		`\"max_landing_descent_rate_mps\":0.6`,
		`\"max_wait_ready_sec\":35`,
		`"landing-policy"`,
		`"max-landing-descent-rate-mps"`,
		`"force-disarm-grace-sec"`,
		`"max-wait-ready-sec"`,
		`"hover-span-target-m"`,
		`"hover-span-hard-cap-m"`,
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("hover mission runtime missing %q:\n%s", want, text)
		}
	}
}

func TestGenerateRuntimeArtifactsHoverSlamDirectUsesRawSlamOdomInput(t *testing.T) {
	loader := config.NewLoader("../../config.toml")
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}
	taskConfig, err := loader.LoadTask(project, "hover")
	if err != nil {
		t.Fatalf("LoadTask(hover) error = %v", err)
	}
	runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		t.Fatalf("BuildTaskRuntimeConfig(hover) error = %v", err)
	}
	task, err := DefaultRegistry().ConfigureOne(taskConfig)
	if err != nil {
		t.Fatalf("ConfigureOne(hover) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{SimulationProfile: ProfileSlamDirect}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(hover slam-direct) error = %v", err)
	}
	runtimeConfig, err = ApplySimulationProfile(runtimeConfig, plan)
	if err != nil {
		t.Fatalf("ApplySimulationProfile(hover slam-direct) error = %v", err)
	}

	artifactDir := t.TempDir()
	if _, err := GenerateRuntimeArtifacts(project, plan, runtimeConfig, artifactDir); err != nil {
		t.Fatalf("GenerateRuntimeArtifacts(hover slam-direct) error = %v", err)
	}
	assertSlamRuntimeExternalNavInput(t, artifactlayout.RuntimeConfig(artifactDir, "slam_runtime.toml"), "/slam/odom")
	assertExternalNavBridgeInput(t, artifactlayout.RuntimeConfig(artifactDir, "external_nav_bridge_params.yaml"), "/slam/odom")
}

func TestGenerateRuntimeArtifactsHoverSlamDirectNoOdomPriorUsesNoOdomConfig(t *testing.T) {
	loader := config.NewLoader("../../config.toml")
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}
	taskConfig, err := loader.LoadTask(project, "hover")
	if err != nil {
		t.Fatalf("LoadTask(hover) error = %v", err)
	}
	runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		t.Fatalf("BuildTaskRuntimeConfig(hover) error = %v", err)
	}
	task, err := DefaultRegistry().ConfigureOne(taskConfig)
	if err != nil {
		t.Fatalf("ConfigureOne(hover) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{SimulationProfile: ProfileSlamDirectNoOdomPrior}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(hover slam-direct-no-odom-prior) error = %v", err)
	}
	runtimeConfig, err = ApplySimulationProfile(runtimeConfig, plan)
	if err != nil {
		t.Fatalf("ApplySimulationProfile(hover slam-direct-no-odom-prior) error = %v", err)
	}

	artifactDir := t.TempDir()
	if _, err := GenerateRuntimeArtifacts(project, plan, runtimeConfig, artifactDir); err != nil {
		t.Fatalf("GenerateRuntimeArtifacts(hover slam-direct-no-odom-prior) error = %v", err)
	}
	slamRuntimePath := artifactlayout.RuntimeConfig(artifactDir, "slam_runtime.toml")
	assertSlamRuntimeExternalNavInput(t, slamRuntimePath, "/slam/odom")
	assertSlamRuntimeCartographerConfig(t, slamRuntimePath, helpers.HoverNoOdomPriorConfigBasename)
	assertExternalNavBridgeInput(t, artifactlayout.RuntimeConfig(artifactDir, "external_nav_bridge_params.yaml"), "/slam/odom")
	assertCartographerConfigUsesOdometry(t, artifactlayout.RuntimeConfig(artifactDir, helpers.HoverNoOdomPriorConfigBasename), false)
	assertFileDoesNotContain(t, slamRuntimePath, "cartographer_configuration_basename = 'navlab_cartographer_2d_real.lua'")
	assertFileDoesNotContain(t, slamRuntimePath, "external_nav_input_odom_topic = '/odometry'")
}

func assertSlamRuntimeExternalNavInput(t *testing.T, path string, wantTopic string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated slam runtime config: %v", err)
	}
	want := fmt.Sprintf("external_nav_input_odom_topic = '%s'", wantTopic)
	if !strings.Contains(string(data), want) {
		t.Fatalf("slam runtime missing %q:\n%s", want, string(data))
	}
}

func assertSlamRuntimeCartographerConfig(t *testing.T, path string, wantBasename string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated slam runtime config: %v", err)
	}
	want := fmt.Sprintf("cartographer_configuration_basename = '%s'", wantBasename)
	if !strings.Contains(string(data), want) {
		t.Fatalf("slam runtime missing %q:\n%s", want, string(data))
	}
}

func assertCartographerConfigUsesOdometry(t *testing.T, path string, want bool) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated cartographer config: %v", err)
	}
	wantText := fmt.Sprintf("use_odometry = %v", want)
	if !strings.Contains(string(data), wantText) {
		t.Fatalf("cartographer config missing %q:\n%s", wantText, string(data))
	}
}

func assertFileDoesNotContain(t *testing.T, path string, forbidden string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated file: %v", err)
	}
	if strings.Contains(string(data), forbidden) {
		t.Fatalf("file %s must not contain %q:\n%s", path, forbidden, string(data))
	}
}

func assertExternalNavBridgeInput(t *testing.T, path string, wantTopic string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated external nav bridge params: %v", err)
	}
	want := fmt.Sprintf("input_odom_topic: %s", wantTopic)
	if !strings.Contains(string(data), want) {
		t.Fatalf("external nav params missing %q:\n%s", want, string(data))
	}
}

func assertHoverSlamRuntimeUsesCartographerAdapter(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated slam runtime config: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		`cartographer_configuration_directory = '/workspace/navlab/common/slam/ros/localization/navlab_cartographer_adapter/config'`,
		`cartographer_configuration_basename = 'navlab_cartographer_2d_hover.lua'`,
		`cartographer_odometry_topic = '/cartographer/odometry_input'`,
		`cartographer_tf_topic = '/navlab/slam/tf'`,
		`external_nav_input_odom_topic = '/external_nav/odom_candidate'`,
		`imu_source_topic = '/imu'`,
		`imu_topic = '/navlab/slam/imu'`,
		`launch_cartographer_backend = true`,
		`odom_topic = '/slam/odom'`,
		`slam_status_topic = '/navlab/slam/status'`,
		`publish_global_tf = false`,
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("hover slam runtime missing %q:\n%s", want, text)
		}
	}
	if strings.Contains(text, `cartographer_odometry_topic = '/odometry'`) {
		t.Fatalf("hover slam runtime must not use diagnostic truth /odometry:\n%s", text)
	}
	if strings.Contains(text, `external_nav_input_odom_topic = '/slam/cartographer_odom'`) {
		t.Fatalf("hover external nav launch arg must not consume Cartographer side-channel odom:\n%s", text)
	}
	if strings.Contains(text, `/navlab/cartographer/odom`) || strings.Contains(text, `/navlab/cartographer/status`) {
		t.Fatalf("hover runtime must not route Cartographer through diagnostic side-channel topics:\n%s", text)
	}
}

func assertHoverExternalNavUsesCartographerAdapter(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated external nav bridge params: %v", err)
	}
	text := string(data)
	if !strings.Contains(text, "input_odom_topic: /external_nav/odom_candidate") {
		t.Fatalf("hover external nav must consume fail-closed selector candidate /external_nav/odom_candidate:\n%s", text)
	}
	if strings.Contains(text, "input_odom_topic: /slam/odom\n") {
		t.Fatalf("hover external nav must not bypass correction gate with raw /slam/odom:\n%s", text)
	}
	for _, want := range []string{
		"slam_quality_gate_enabled: true",
		"require_imu_for_quality: true",
		"require_scan_for_quality: true",
		"low_observability_mode: true",
		"scan_topic: /scan",
		"min_scan_valid_ratio_for_quality: 0.50",
		"min_scan_hit_ratio_for_quality: 0.25",
		"min_scan_range_span_m_for_quality: 1.0",
		"min_scan_range_stddev_m_for_quality: 0.20",
		"min_scan_observed_quadrants_for_quality: 3",
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("hover external nav quality gate missing %q:\n%s", want, text)
		}
	}
	if strings.Contains(text, "input_odom_topic: /slam/cartographer_odom") {
		t.Fatalf("hover external nav must not consume Cartographer side-channel odom:\n%s", text)
	}
	if strings.Contains(text, "input_odom_topic: /navlab/cartographer/odom") {
		t.Fatalf("hover external nav must not consume diagnostic Cartographer side-channel odom:\n%s", text)
	}
}

func assertCopiedHoverCartographerConfig(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read copied hover Cartographer config: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		"Hover-only profile",
		"use_odometry = true",
		"scan-reference odometry prior derived only from /scan",
		"TRAJECTORY_BUILDER_2D.use_imu_data = true",
		"TRAJECTORY_BUILDER_2D.missing_data_ray_length = 0.1",
		"TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 1.",
		"TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.linear_search_window = 0.50",
		"POSE_GRAPH.optimization_problem.odometry_translation_weight = 1e4",
		"POSE_GRAPH.optimize_every_n_nodes = 30",
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("copied hover Cartographer config missing %q:\n%s", want, text)
		}
	}
}

func assertScanReferenceCartographerOdomRuntime(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read scan-reference Cartographer odom runtime: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		`\"odom_topic\":\"/cartographer/odometry_input\"`,
		`\"status_topic\":\"/navlab/scan_reference_cartographer_odom/status\"`,
		`\"frame_id\":\"odom\"`,
		`\"reset_on_hover_hold\":false`,
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("scan-reference Cartographer odom runtime missing %q:\n%s", want, text)
		}
	}
	if strings.Contains(text, `\"odom_topic\":\"/odometry\"`) {
		t.Fatalf("scan-reference Cartographer odom runtime must not use Gazebo truth /odometry:\n%s", text)
	}
}

func assertHoverOfficialMazeOverlayAvoidsMapAlias(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated official maze overlay script: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		`/navlab/official_maze/map`,
		`publishers = [node.create_publisher`,
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("hover official maze overlay script missing %q:\n%s", want, text)
		}
	}
	if strings.Contains(text, `"/map"`) {
		t.Fatalf("official maze overlay must not publish the Cartographer /map topic:\n%s", text)
	}
}

func assertModelOverlayUsesNavLabRangefinderModel(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated model overlay: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		`<uri>model://iris_with_standoffs</uri>`,
		`<uri>model://lidar_2d</uri>`,
		`<link name="rangefinder_down_link">`,
		`<pose relative_to="base_link">0 0 -0.08 0 0 0</pose>`,
		`<sensor name="rangefinder_down" type="gpu_lidar">`,
		`<gz_frame_id>rangefinder_down_frame</gz_frame_id>`,
		`<pose>0 0 -0.02 0 1.5707963267948966 0</pose>`,
		`<topic>/rangefinder/down/scan_ideal</topic>`,
		`<child>rangefinder_down_link</child>`,
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("generated model overlay missing %q:\n%s", want, text)
		}
	}
	for _, stale := range []string{
		`<link name="rangefinder_down_frame">`,
		`<sensor name="down_rangefinder_sensor"`,
		`<topic>rangefinder/down/scan_ideal</topic>`,
	} {
		if strings.Contains(text, stale) {
			t.Fatalf("generated model overlay retained stale generated shape %q:\n%s", stale, text)
		}
	}
}

func assertSensorRuntimeUsesBenewakeSerial(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated sensor runtime config: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		`virtual_serial_link = '/tmp/navlab_benewake_tfmini'`,
		"serial_baud = 115200",
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("generated sensor runtime config missing %q:\n%s", want, text)
		}
	}
	for _, stale := range []string{
		"endpoint =",
		"mavlink_orientation",
		"source_system",
		"source_component",
		"sensor_id",
		"covariance_cm",
	} {
		if strings.Contains(text, stale) {
			t.Fatalf("generated sensor runtime config retained MAVLink sender field %q:\n%s", stale, text)
		}
	}
}

func assertParamOverlayContainsExternalNavAndRangefinder(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated param overlay: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		"GPS1_TYPE 0",
		"SIM_GPS1_ENABLE 0",
		"SIM_GPS1_TYPE 0",
		"SIM_GPS2_ENABLE 0",
		"SIM_GPS3_ENABLE 0",
		"SIM_GPS4_ENABLE 0",
		"VISO_TYPE 1",
		"EK3_SRC1_POSXY 6",
		"EK3_SRC1_POSZ 2",
		"EK3_SRC1_VELXY 0",
		"EK3_SRC1_VELZ 0",
		"EK3_SRC1_YAW 1",
		"SERIAL7_PROTOCOL 9",
		"RNGFND1_PIN -1",
		"RNGFND1_SCALING 3",
		"RNGFND1_TYPE 20",
		"RNGFND1_MIN_CM 10",
		"RNGFND1_MAX_CM 1200",
		"RNGFND1_GNDCLEAR 15",
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("generated param overlay missing %q:\n%s", want, text)
		}
	}
	for _, stale := range []string{
		"RNGFND1_TYPE 1",
		"RNGFND1_TYPE 10",
		"RNGFND1_MIN_CM 5",
		"RNGFND1_MAX_CM 600",
		"RNGFND1_GNDCLEAR 10",
		"RNGFND1_SCALING 10",
		"RNGFND1_PIN 0",
		"RNGFND1_MAX 50.00",
		"SIM_SONAR_SCALE",
		"SIM_GPS1_ENABLE 1",
		"SIM_GPS1_TYPE 1",
	} {
		if strings.Contains(text, stale) {
			t.Fatalf("generated param overlay should not override ExternalNav profile with %q:\n%s", stale, text)
		}
	}
}

func assertProbeScriptRetriesTopicEcho(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated probe script: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		"while time.monotonic() < deadline:",
		"TOPIC_SAMPLE_TIMEOUT_SEC",
		"STRING_BATCH_TIMEOUT_SEC",
		"STRING_READY_TIMEOUT_SEC",
		"deadline = time.monotonic() + TOPIC_SAMPLE_TIMEOUT_SEC",
		"deadline = time.monotonic() + STRING_READY_TIMEOUT_SEC",
		"attempts += 1",
		`"does not appear to be published yet"`,
		`"Failed to find a free participant index"`,
		`"rmw_create_node"`,
		"retryable_probe_error",
		"ConnectionRefusedError",
		"Fall back to ros2 topic echo sampling",
		"sample_message_topic",
		"rclpy_subscription",
		"from rosidl_runtime_py.utilities import get_message",
		`getattr(msg, "data", None)`,
		"parse_json_payload(data)",
		`"attempts": attempts`,
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("generated probe script missing retry evidence %q:\n%s", want, text)
		}
	}
}

func assertHoverProbeKeepsLandingStatusOptional(t *testing.T, path string) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated hover probe script: %v", err)
	}
	text := string(data)
	for _, want := range []string{
		`TOPICS = json.loads("[\"/ap/v1/pose/filtered\",\"/slam/odom\",\"/navlab/slam/status\",\"/external_nav/status\",\"/external_nav/odom_candidate\",\"/external_nav/source_selector/status\",\"/navlab/scan_reference_drift/odom\",\"/navlab/scan_reference_drift/status\",\"/mavlink_external_nav/status\",\"/sim/x2/status\",\"/navlab/hover/status\",\"/navlab/landing/status\"]")`,
		`OPTIONAL_TOPICS = set(json.loads("[\"/navlab/landing/status\"]"))`,
		`"optional_topics": sorted(OPTIONAL_TOPICS)`,
		`"optional_blockers": optional_blockers`,
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("generated hover probe missing optional landing status evidence %q:\n%s", want, text)
		}
	}
}

func TestNavigationAdapterRuntimeScriptUsesIntentTopicNotDirectFCU(t *testing.T) {
	loader := config.NewLoader("../../config.toml")
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}
	taskConfig, err := loader.LoadTask(project, "navigation")
	if err != nil {
		t.Fatalf("LoadTask(navigation) error = %v", err)
	}
	runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		t.Fatalf("BuildTaskRuntimeConfig(navigation) error = %v", err)
	}
	task, err := DefaultRegistry().ConfigureOne(taskConfig)
	if err != nil {
		t.Fatalf("ConfigureOne(navigation) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(navigation) error = %v", err)
	}

	artifactDir := t.TempDir()
	if _, err := GenerateRuntimeArtifacts(project, plan, runtimeConfig, artifactDir); err != nil {
		t.Fatalf("GenerateRuntimeArtifacts(navigation) error = %v", err)
	}
	script, err := os.ReadFile(artifactlayout.RuntimeScript(artifactDir, "navigation_adapter_runtime.py"))
	if err != nil {
		t.Fatalf("ReadFile(navigation_adapter_runtime.py) error = %v", err)
	}
	text := string(script)
	if !strings.Contains(text, "SetpointIntentTopic") || !strings.Contains(text, "create_subscription") {
		t.Fatalf("navigation adapter script missing intent/subscription behavior:\n%s", text)
	}
	if strings.Contains(text, `"/ap/v1/cmd_vel"`) {
		t.Fatalf("navigation adapter script directly references FCU cmd_vel:\n%s", text)
	}
	missionScript, err := os.ReadFile(artifactlayout.RuntimeScript(artifactDir, "navigation_mission_runtime.py"))
	if err != nil {
		t.Fatalf("ReadFile(navigation_mission_runtime.py) error = %v", err)
	}
	missionText := string(missionScript)
	if !strings.Contains(missionText, "NavigateToPose") || !strings.Contains(missionText, "nav2_action_unavailable") {
		t.Fatalf("navigation mission script missing NavigateToPose readiness behavior:\n%s", missionText)
	}
	for _, expected := range []string{"mission_goals", "ExitGoal", "completion_policy", "frontier_candidate", "coverage_growth", "blacklisted_goals", "unreachable_blacklisted", "map_ready", "costmap_ready"} {
		if !strings.Contains(missionText, expected) {
			t.Fatalf("navigation mission script missing %q:\n%s", expected, missionText)
		}
	}
	profile, err := os.ReadFile(artifactlayout.RuntimeConfig(artifactDir, "navigation_foxglove_lite_profile.json"))
	if err != nil {
		t.Fatalf("ReadFile(navigation_foxglove_lite_profile.json) error = %v", err)
	}
	profileText := string(profile)
	for _, expected := range []string{"\"role\": \"map\"", "\"role\": \"path\"", "\"role\": \"global_costmap\"", "\"role\": \"scan\"", "\"role\": \"trajectory\"", "\"role\": \"goals\"", "\"role\": \"events\""} {
		if !strings.Contains(profileText, expected) {
			t.Fatalf("navigation Foxglove profile missing %q:\n%s", expected, profileText)
		}
	}
}

func TestFCUControllerRuntimeScriptKeepsSubscriptionsAlive(t *testing.T) {
	loader := config.NewLoader("../../config.toml")
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}
	taskConfig, err := loader.LoadTask(project, "exploration")
	if err != nil {
		t.Fatalf("LoadTask(exploration) error = %v", err)
	}
	runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		t.Fatalf("BuildTaskRuntimeConfig(exploration) error = %v", err)
	}
	task, err := DefaultRegistry().ConfigureOne(taskConfig)
	if err != nil {
		t.Fatalf("ConfigureOne(exploration) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(exploration) error = %v", err)
	}

	artifactDir := t.TempDir()
	if _, err := GenerateRuntimeArtifacts(project, plan, runtimeConfig, artifactDir); err != nil {
		t.Fatalf("GenerateRuntimeArtifacts(exploration) error = %v", err)
	}
	script, err := os.ReadFile(artifactlayout.RuntimeScript(artifactDir, "fcu_controller_runtime.py"))
	if err != nil {
		t.Fatalf("ReadFile(fcu_controller_runtime.py) error = %v", err)
	}
	text := string(script)
	for _, expected := range []string{
		"subscriptions = []",
		`subscriptions.append(node.create_subscription(PoseStamped, SPEC["pose_topic"], on_pose, qos_profile_sensor_data))`,
		`subscriptions.append(node.create_subscription(Odometry, SPEC["slam_odom_topic"], on_slam_odom, qos_profile_sensor_data))`,
		`subscriptions.append(node.create_subscription(String, SPEC["setpoint_intent_topic"], on_setpoint_intent, 10))`,
		"import threading",
		`state["pose_source"] = "slam_odom"`,
		`state.get("pose_source") != "slam_odom"`,
		"bootstrap_thread = threading.Thread(target=run_bootstrap, daemon=True)",
		"bootstrap_thread.start()",
		"def bootstrap_ready(state: dict) -> bool:",
		`and (bootstrap.get("takeoff") or {}).get("ok", False)`,
		`takeoff_min_height_m`,
		`takeoff_min_height_ratio`,
		`target_min = max(min_height_m, altitude_m * min_height_ratio)`,
		`def send_mavlink_local_position_setpoint(payload: dict) -> None:`,
		`master.mav.set_position_target_local_ned_send`,
		`mavutil.mavlink.MAV_FRAME_LOCAL_NED`,
		`mavlink_setpoint_count`,
		`refresh_mavlink_local_position(master)`,
		`setpoint_lookahead_sec`,
	} {
		if !strings.Contains(text, expected) {
			t.Fatalf("fcu controller script missing %q:\n%s", expected, text)
		}
	}
	if strings.Contains(text, `target_min = max(0.2, altitude_m * 0.45)`) {
		t.Fatalf("fcu controller script kept stale hard-coded takeoff threshold:\n%s", text)
	}
	if strings.Contains(text, `"state": "hover_hold" if ready`) {
		t.Fatalf("fcu controller must not alias controller readiness to hover_hold:\n%s", text)
	}
}

func TestHoverRuntimeScriptCallsPythonMissionRuntime(t *testing.T) {
	loader := config.NewLoader("../../config.toml")
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}
	taskConfig, err := loader.LoadTask(project, "hover")
	if err != nil {
		t.Fatalf("LoadTask(hover) error = %v", err)
	}
	runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		t.Fatalf("BuildTaskRuntimeConfig(hover) error = %v", err)
	}
	task, err := DefaultRegistry().ConfigureOne(taskConfig)
	if err != nil {
		t.Fatalf("ConfigureOne(hover) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(hover) error = %v", err)
	}

	artifactDir := t.TempDir()
	if _, err := GenerateRuntimeArtifacts(project, plan, runtimeConfig, artifactDir); err != nil {
		t.Fatalf("GenerateRuntimeArtifacts(hover) error = %v", err)
	}
	script, err := os.ReadFile(artifactlayout.RuntimeScript(artifactDir, "hover_mission_runtime.py"))
	if err != nil {
		t.Fatalf("ReadFile(hover_mission_runtime.py) error = %v", err)
	}
	text := string(script)
	for _, expected := range []string{
		"from navlab.sim.companion.nodes.hover_mission import run",
		"mission_summary.json",
		"takeoff-alt-m",
		"max-wait-ready-sec",
		"hover-hold-sec",
		"landing-status-topic",
		"require-external-nav",
	} {
		if !strings.Contains(text, expected) {
			t.Fatalf("hover mission wrapper missing %q:\n%s", expected, text)
		}
	}
}

func TestGenerateRuntimeArtifactsUsesSimulationProfileForScanRobustness(t *testing.T) {
	loader := config.NewLoader("../../config.toml")
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}
	taskConfig, err := loader.LoadTask(project, "scan-robustness")
	if err != nil {
		t.Fatalf("LoadTask(scan-robustness) error = %v", err)
	}
	runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		t.Fatalf("BuildTaskRuntimeConfig(scan-robustness) error = %v", err)
	}
	task, err := DefaultRegistry().ConfigureOne(taskConfig)
	if err != nil {
		t.Fatalf("ConfigureOne(scan-robustness) error = %v", err)
	}
	plan, err := task.Plan(PlanOptions{SimulationProfile: "realistic"}, helpers.DefaultRegistry())
	if err != nil {
		t.Fatalf("Plan(scan-robustness) error = %v", err)
	}
	runtimeConfig, err = ApplySimulationProfile(runtimeConfig, plan)
	if err != nil {
		t.Fatalf("ApplySimulationProfile(scan-robustness) error = %v", err)
	}

	artifactDir := t.TempDir()
	if _, err := GenerateRuntimeArtifacts(project, plan, runtimeConfig, artifactDir); err != nil {
		t.Fatalf("GenerateRuntimeArtifacts(scan-robustness) error = %v", err)
	}
	data, err := os.ReadFile(artifactlayout.RuntimeConfig(artifactDir, "scan_robustness_runtime.toml"))
	if err != nil {
		t.Fatalf("ReadFile(scan_robustness_runtime.toml) error = %v", err)
	}
	var generated struct {
		AirframeDisturbance struct {
			Runtime struct {
				Profile          string
				RequiredProfiles []string
			}
		} `toml:"airframe_disturbance"`
		AirframeDisturbanceGate struct {
			Runtime struct {
				RequiredProfiles []string `toml:"required_profiles"`
			}
		} `toml:"airframe_disturbance_gate"`
	}
	if err := toml.Unmarshal(data, &generated); err != nil {
		t.Fatalf("toml.Unmarshal(scan_robustness_runtime.toml) error = %v", err)
	}
	if generated.AirframeDisturbance.Runtime.Profile != "realistic" {
		t.Fatalf("runtime profile = %q", generated.AirframeDisturbance.Runtime.Profile)
	}
	wantProfiles := []string{"ideal", "realistic"}
	if !reflect.DeepEqual(generated.AirframeDisturbance.Runtime.RequiredProfiles, wantProfiles) {
		t.Fatalf("runtime required profiles = %#v, want %#v", generated.AirframeDisturbance.Runtime.RequiredProfiles, wantProfiles)
	}
	if !reflect.DeepEqual(generated.AirframeDisturbanceGate.Runtime.RequiredProfiles, wantProfiles) {
		t.Fatalf("gate required profiles = %#v, want %#v", generated.AirframeDisturbanceGate.Runtime.RequiredProfiles, wantProfiles)
	}
}

func assertStartupReadinessPolicyEchoed(t *testing.T, hoverConfigPath string, missionScriptPath string) {
	t.Helper()
	configData, err := os.ReadFile(hoverConfigPath)
	if err != nil {
		t.Fatalf("ReadFile(%s) error = %v", hoverConfigPath, err)
	}
	configText := string(configData)
	for _, expected := range []string{
		"StartupReadinessTimeoutSec = 35",
		"StartupReadinessGraceSec = 8",
		"StartupReadinessProgressWindowSec = 3",
		"StartupReadinessRestartLimit = 0",
	} {
		if !strings.Contains(configText, expected) {
			t.Fatalf("startup readiness policy missing %q in %s:\n%s", expected, hoverConfigPath, configText)
		}
	}
	scriptData, err := os.ReadFile(missionScriptPath)
	if err != nil {
		t.Fatalf("ReadFile(%s) error = %v", missionScriptPath, err)
	}
	scriptText := string(scriptData)
	for _, expected := range []string{
		"startup_readiness_policy",
		"go_runtime_config",
		"progress_window_sec",
		"restart_limit",
	} {
		if !strings.Contains(scriptText, expected) {
			t.Fatalf("startup readiness policy missing %q in %s", expected, missionScriptPath)
		}
	}
}

func assertFileExists(t *testing.T, path string) {
	t.Helper()
	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("expected file %s: %v", path, err)
	}
	if info.IsDir() {
		t.Fatalf("expected file %s, got directory", path)
	}
}

func assertFileMissing(t *testing.T, path string) {
	t.Helper()
	if _, err := os.Stat(path); err == nil {
		t.Fatalf("unexpected generated file %s", path)
	} else if !os.IsNotExist(err) {
		t.Fatalf("stat %s: %v", path, err)
	}
}
