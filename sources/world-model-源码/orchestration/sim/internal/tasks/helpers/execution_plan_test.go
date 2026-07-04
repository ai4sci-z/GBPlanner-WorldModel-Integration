package helpers

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
)

func TestBuildExecutionPlanIncludesDeepRuntimeHelpers(t *testing.T) {
	task := config.TaskConfig{
		ID:          "scan-robustness",
		Family:      "sim",
		Description: "scan robustness",
		Task: config.TaskParameters{
			DurationSec:       240,
			SimulationProfile: "ideal",
		},
		Sections: map[string]any{
			"scan_robustness": map[string]any{"live": true},
		},
	}
	definitions, err := DefaultRegistry().Resolve([]string{
		"sensors",
		"slam",
		"fcu-controller",
		"frame-contract",
		"slam-hover",
		"scan-stabilization",
		"scan-robustness-workflow",
	})
	if err != nil {
		t.Fatal(err)
	}

	plan, err := BuildExecutionPlan(task, 240, "ideal", definitions)
	if err != nil {
		t.Fatal(err)
	}

	assertHasService(t, plan, "fcu_controller")
	assertServiceEnvContains(t, plan, "slam_backend", "ROS_DOMAIN_ID", "from config.toml")
	assertServiceEnvContains(t, plan, "slam_backend", "RMW_IMPLEMENTATION", "from config.toml")
	assertHasProbe(t, plan, "rangefinder_probe")
	assertHasProbe(t, plan, "frame_contract_probe")
	assertHasProbe(t, plan, "slam_hover_probe")
	assertHasProbe(t, plan, "stabilization_status_probe")
	assertHasRosbag(t, plan, "scan_stabilization_rosbag")
	assertHasRosbag(t, plan, "scan_robustness_rosbag")
	assertHasGate(t, plan, "airframe_disturbance_gate")
}

func TestBuildExecutionPlanIncludesNav2NavigationWorkflow(t *testing.T) {
	task := config.TaskConfig{
		ID:          "navigation",
		Family:      "sim",
		Description: "navigation",
		Task: config.TaskParameters{
			DurationSec:       180,
			SimulationProfile: "ideal",
		},
		Sections: map[string]any{
			"navigation_mission": map[string]any{"navigation_window_sec": 120},
		},
	}
	definitions, err := DefaultRegistry().Resolve([]string{
		"sensors",
		"slam",
		"fcu-controller",
		"frame-contract",
		"slam-hover",
		"scan-stabilization",
		"nav2-navigation-workflow",
	})
	if err != nil {
		t.Fatal(err)
	}

	plan, err := BuildExecutionPlan(task, 180, "ideal", definitions)
	if err != nil {
		t.Fatal(err)
	}

	assertHasService(t, plan, "nav2_navigation")
	assertHasService(t, plan, "navigation_adapter")
	assertHasService(t, plan, "navigation_mission")
	assertServiceCommandContains(t, plan, "slam_backend", "/opt/ros/${ROS_DISTRO:-humble}/setup.bash")
	assertServiceCommandContains(t, plan, "slam_backend", "/opt/navlab_ws/install/setup.bash")
	assertServiceCommandContains(t, plan, "slam_backend", "slam_backend.runtime.log")
	assertHasProbe(t, plan, "nav2_lifecycle_probe")
	assertHasProbe(t, plan, "costmap_health_probe")
	assertHasProbe(t, plan, "navigation_status_probe")
	assertHasRosbag(t, plan, "navigation_rosbag")
	assertRosbagHasTopics(t, plan, "navigation_rosbag", MatureWorldSLAMReviewTopics())
	assertRosbagHasTopics(t, plan, "navigation_rosbag", []string{"/cmd_vel_nav", "/navlab/navigation/status", "/global_costmap/costmap", "/local_costmap/costmap"})
	assertRosbagHasRequiredTopics(t, plan, "navigation_rosbag", NavigationTaskRequiredTopics(DefaultNav2NavigationSpec()))
	assertRosbagMissingTopics(t, plan, "navigation_rosbag", []string{"/navlab/navigation/cmd_vel", "/navlab/landing/intent"})
	assertHasGate(t, plan, "navigation_acceptance")
}

func TestBuildExecutionPlanHoverKeepsMatureSLAMRosbagTopics(t *testing.T) {
	task := config.TaskConfig{
		ID:     "hover",
		Family: "sim",
		Task: config.TaskParameters{
			DurationSec:       90,
			SimulationProfile: "ideal",
		},
	}
	definitions, err := DefaultRegistry().Resolve([]string{
		"sensors",
		"slam",
		"frame-contract",
		"slam-hover",
	})
	if err != nil {
		t.Fatal(err)
	}

	plan, err := BuildExecutionPlan(task, 90, "ideal", definitions)
	if err != nil {
		t.Fatal(err)
	}

	assertHasRosbag(t, plan, "hover_rosbag")
	assertHasService(t, plan, "hover_mission")
	assertHasService(t, plan, "scan_reference_cartographer_odom")
	assertHasService(t, plan, "external_nav_source_selector")
	assertServiceBefore(t, plan, "external_nav_source_selector", "slam_backend")
	assertHasArtifact(t, plan, artifactlayout.RuntimeScriptRel("external_nav_source_selector_runtime.py"))
	assertMissingService(t, plan, "fcu_controller")
	assertServiceCommandContains(t, plan, "hover_mission", "hover_mission_runtime.py")
	assertServiceCommandContains(t, plan, "scan_reference_cartographer_odom", "scan_reference_cartographer_odom_runtime.py")
	assertServiceCommandContains(t, plan, "external_nav_source_selector", "external_nav_source_selector_runtime.py")
	assertProbeHasTopics(t, plan, "slam_hover_probe", []string{"/external_nav/odom_candidate", "/external_nav/source_selector/status"})
	assertRosbagHasTopics(t, plan, "hover_rosbag", MatureWorldSLAMReviewTopics())
	assertRosbagHasTopics(t, plan, "hover_rosbag", []string{DiagnosticGazeboModelOdometryTopic, DiagnosticGazeboTFTopic, DiagnosticGazeboTFStaticTopic, CartographerOdometryInputTopic, CartographerTFTopic, "/navlab/scan_reference_cartographer_odom/status", "/external_nav/odom_candidate", "/external_nav/source_selector/status"})
	assertRosbagHasRequiredTopics(t, plan, "hover_rosbag", append(HoverTaskRequiredTopics(DefaultSlamHoverSpec()), CartographerOdometryInputTopic, "/navlab/scan_reference_cartographer_odom/status"))
	assertRosbagRequiredMissingTopics(t, plan, "hover_rosbag", []string{DiagnosticGazeboModelOdometryTopic, DiagnosticGazeboTFTopic, DiagnosticGazeboTFStaticTopic, CartographerTFTopic})
	assertGateHasInputs(t, plan, "slam_hover_acceptance", []string{"mission_summary.json"})
	assertGateMissingInputs(t, plan, "slam_hover_acceptance", []string{"controller_summary.json"})
}

func TestBuildExecutionPlanHoverSlamOnlyDoesNotStartMissionOrExternalNav(t *testing.T) {
	task := config.TaskConfig{
		ID:     "hover-slam-only",
		Family: "sim",
		Task: config.TaskParameters{
			DurationSec:       45,
			SimulationProfile: "ideal",
		},
	}
	definitions, err := DefaultRegistry().Resolve([]string{
		"sensors",
		"slam",
		"slam-only",
	})
	if err != nil {
		t.Fatal(err)
	}

	plan, err := BuildExecutionPlan(task, 45, "ideal", definitions)
	if err != nil {
		t.Fatal(err)
	}

	assertHasService(t, plan, "slam_backend")
	assertHasService(t, plan, "gazebo_sensor")
	assertMissingService(t, plan, "hover_mission")
	assertMissingService(t, plan, "fcu_controller")
	assertMissingService(t, plan, "hover_scan_map_localizer")
	assertHasProbe(t, plan, "slam_only_probe")
	assertMissingProbe(t, plan, "rangefinder_probe")
	assertMissingProbe(t, plan, "imu_probe")
	assertMissingProbe(t, plan, "frame_contract_probe")
	assertHasRosbag(t, plan, "slam_only_rosbag")
	assertRosbagHasRequiredTopics(t, plan, "slam_only_rosbag", DefaultSlamOnlySpec().RequiredTopics())
	assertGateHasInputs(t, plan, "slam_only_acceptance", []string{"slam_only_probe.json"})
}

func TestBuildExecutionPlanExplorationKeepsMatureSLAMRosbagTopics(t *testing.T) {
	task := config.TaskConfig{
		ID:     "exploration",
		Family: "sim",
		Task: config.TaskParameters{
			DurationSec:       120,
			SimulationProfile: "ideal",
		},
		Sections: map[string]any{
			"exploration_gate": map[string]any{"exploration_window_sec": 40},
		},
	}
	definitions, err := DefaultRegistry().Resolve([]string{
		"sensors",
		"slam",
		"fcu-controller",
		"frame-contract",
		"exploration-workflow",
	})
	if err != nil {
		t.Fatal(err)
	}

	plan, err := BuildExecutionPlan(task, 120, "ideal", definitions)
	if err != nil {
		t.Fatal(err)
	}

	assertHasRosbag(t, plan, "exploration_rosbag")
	assertHasService(t, plan, "exploration_workflow")
	assertHasProbe(t, plan, "exploration_probe")
	assertMissingProbe(t, plan, "slam_hover_probe")
	assertProbeHasTopics(t, plan, "exploration_probe", []string{"/navlab/fcu/setpoint/output", "/navlab/exploration/status", "/slam/odom", "/navlab/landing/status"})
	assertServiceCommandContains(t, plan, "exploration_workflow", "exploration_workflow_runtime.py")
	assertServiceEnvContains(t, plan, "exploration_workflow", "ROS_DOMAIN_ID", "from config.toml")
	assertRosbagHasTopics(t, plan, "exploration_rosbag", MatureWorldSLAMReviewTopics())
	assertRosbagHasRequiredTopics(t, plan, "exploration_rosbag", ExplorationTaskRequiredTopics(DefaultExplorationWorkflowSpec()))
	assertRosbagRequiredMissingTopics(t, plan, "exploration_rosbag", []string{"/navlab/x2/scan_normalized"})
}

func TestTaskRequiredTopicsExcludeDiagnosticTruthInputs(t *testing.T) {
	banned := []string{
		"/odometry",
		"/navlab/official_maze/map",
		"/navlab/navigation/seed_map",
	}
	requiredSets := map[string][]string{
		"hover":       HoverTaskRequiredTopics(DefaultSlamHoverSpec()),
		"exploration": ExplorationTaskRequiredTopics(DefaultExplorationWorkflowSpec()),
		"navigation":  NavigationTaskRequiredTopics(DefaultNav2NavigationSpec()),
	}
	for name, topics := range requiredSets {
		for _, topic := range banned {
			if contains(topics, topic) {
				t.Fatalf("%s required topics include diagnostic-only %q: %#v", name, topic, topics)
			}
		}
	}
}

func TestHoverRequiredTopicsStayReplayLiteCompatible(t *testing.T) {
	required := HoverTaskRequiredTopics(DefaultSlamHoverSpec())
	for _, topic := range []string{
		"/tf",
		"/tf_static",
		"/map",
		"/lidar",
		"/scan",
		"/sim/x2/status",
		"/slam/odom",
		"/external_nav/odom",
		"/navlab/slam/imu",
		"/navlab/hover/status",
		"/navlab/landing/status",
		"/rangefinder/down/range",
	} {
		if !contains(required, topic) {
			t.Fatalf("hover required topics missing lite replay evidence %q: %#v", topic, required)
		}
	}
	for _, topic := range []string{
		"/imu",
		"/ap/v1/status",
		"/rangefinder/down/status",
	} {
		if contains(required, topic) {
			t.Fatalf("hover required topics should not require diagnostic/heavy topic %q: %#v", topic, required)
		}
	}
}

func TestMatureReviewTopicsExcludeHeavyDiagnosticTopics(t *testing.T) {
	reviewTopics := MatureWorldSLAMReviewTopics()
	for _, topic := range []string{
		"/imu",
		"/ap/v1/cmd_vel",
		DiagnosticGazeboTFTopic,
		DiagnosticGazeboTFStaticTopic,
		DiagnosticTruthOdometryTopic,
		DiagnosticGazeboModelOdometryTopic,
		"/navlab/x2/scan_normalized",
	} {
		if contains(reviewTopics, topic) {
			t.Fatalf("review topics should exclude heavy or diagnostic-only topic %q: %#v", topic, reviewTopics)
		}
	}
	for name, topics := range map[string][]string{
		"hover":       HoverTaskRequiredTopics(DefaultSlamHoverSpec()),
		"exploration": ExplorationTaskRequiredTopics(DefaultExplorationWorkflowSpec()),
		"navigation":  NavigationTaskRequiredTopics(DefaultNav2NavigationSpec()),
	} {
		if contains(topics, DiagnosticTruthOdometryTopic) {
			t.Fatalf("%s required topics include diagnostic truth odometry: %#v", name, topics)
		}
	}
}

func TestHoverFCUControlEvidenceTopicsAreReviewCapturedNotRequired(t *testing.T) {
	reviewTopics := MatureWorldSLAMReviewTopics()
	requiredTopics := HoverTaskRequiredTopics(DefaultSlamHoverSpec())
	for _, topic := range []string{
		"/navlab/fcu/controller/status",
		"/navlab/fcu/setpoint/intent",
		"/navlab/fcu/setpoint/output",
	} {
		if !contains(reviewTopics, topic) {
			t.Fatalf("hover review topics should capture FCU evidence topic %q: %#v", topic, reviewTopics)
		}
		if contains(requiredTopics, topic) {
			t.Fatalf("hover required topics should keep FCU evidence optional/review-only %q: %#v", topic, requiredTopics)
		}
	}
}

func TestRuntimeSpecsGenerateScriptsAndConfigs(t *testing.T) {
	dir := t.TempDir()
	if err := WriteSensorRuntimeConfig(filepath.Join(dir, "sensor.toml"), "vendor.yaml", DefaultSensorRuntimeSpec()); err != nil {
		t.Fatal(err)
	}
	if err := WriteFCUControllerRuntimeConfig(filepath.Join(dir, "fcu.toml"), DefaultFCUControllerSpec()); err != nil {
		t.Fatal(err)
	}
	fcuConfig, err := os.ReadFile(filepath.Join(dir, "fcu.toml"))
	if err != nil {
		t.Fatal(err)
	}
	fcuConfigText := string(fcuConfig)
	if !strings.Contains(fcuConfigText, "DisableArmingChecks = true") ||
		!strings.Contains(fcuConfigText, "ForceArm = true") {
		t.Fatalf("FCU runtime config missing sim arming controls:\n%s", fcuConfigText)
	}
	if err := WriteScanStabilizationRuntimeConfig(filepath.Join(dir, "scan_stabilization.toml"), DefaultScanStabilizationSpec()); err != nil {
		t.Fatal(err)
	}
	if err := WriteNav2ParamsYAML(filepath.Join(dir, "nav2_params.yaml"), DefaultNav2NavigationSpec()); err != nil {
		t.Fatal(err)
	}
	nav2Params, err := os.ReadFile(filepath.Join(dir, "nav2_params.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	nav2ParamsText := string(nav2Params)
	if !strings.Contains(nav2ParamsText, "planner_server:\n  ros__parameters:") ||
		!strings.Contains(nav2ParamsText, "controller_server:\n  ros__parameters:") ||
		!strings.Contains(nav2ParamsText, "bt_navigator:\n  ros__parameters:") {
		t.Fatalf("nav2 params are not ROS parameter YAML:\n%s", nav2ParamsText)
	}
	if strings.Contains(nav2ParamsText, "nav2:\n  profile:") {
		t.Fatalf("nav2 params contain non-ROS summary structure:\n%s", nav2ParamsText)
	}
	if !strings.Contains(nav2ParamsText, "map_topic: /navlab/navigation/seed_map") {
		t.Fatalf("nav2 params should isolate static layer seed map from /map:\n%s", nav2ParamsText)
	}
	if err := WriteNavigationAdapterRuntimeConfig(filepath.Join(dir, "navigation_adapter.toml"), DefaultNav2NavigationSpec()); err != nil {
		t.Fatal(err)
	}
	script, err := FCUControllerRuntimeScript(DefaultFCUControllerSpec(), 90)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(script, "navlab_fcu_controller") || !strings.Contains(script, "controller_status_topic") {
		t.Fatalf("controller script missing expected content:\n%s", script)
	}
	if !strings.Contains(script, `b"ARMING_CHECK"`) ||
		!strings.Contains(script, `21196 if bool(SPEC.get("force_arm", False)) else 0`) {
		t.Fatalf("controller script missing sim force-arm controls:\n%s", script)
	}
	if !strings.Contains(script, "takeoff_ack_accepted = takeoff_ack_accepted or bool(takeoff_ack.get(\"accepted\"))") ||
		!strings.Contains(script, "def publish_hold_cmd_vel()") {
		t.Fatalf("controller script missing stable hover completion controls:\n%s", script)
	}
	if !strings.Contains(script, "def send_mavlink_local_position_setpoint(payload: dict) -> None:") ||
		!strings.Contains(script, "master.mav.set_position_target_local_ned_send") ||
		!strings.Contains(script, "mavutil.mavlink.MAV_FRAME_LOCAL_NED") ||
		!strings.Contains(script, "mavlink_setpoint_count") ||
		!strings.Contains(script, "refresh_mavlink_local_position(master)") ||
		!strings.Contains(script, "setpoint_lookahead_sec") {
		t.Fatalf("controller script missing MAVLink local-position setpoint controls:\n%s", script)
	}
	if !strings.Contains(script, `takeoff_min_height_m`) ||
		!strings.Contains(script, `takeoff_min_height_ratio`) ||
		!strings.Contains(script, `target_min = max(min_height_m, altitude_m * min_height_ratio)`) ||
		strings.Contains(script, `target_min = max(0.2, altitude_m * 0.45)`) {
		t.Fatalf("controller script has incorrect MAVLink takeoff readiness threshold:\n%s", script)
	}
	probe, err := FrameContractProbeScript(DefaultFrameContractSpec())
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(probe, "/tf_static") {
		t.Fatalf("frame probe script missing tf_static topic:\n%s", probe)
	}
	if !strings.Contains(probe, "/navlab/slam/status") ||
		!strings.Contains(probe, "slam_status_has_odom_evidence") {
		t.Fatalf("frame probe script missing SLAM odom evidence fallback:\n%s", probe)
	}
	navProbe, err := NavigationStatusProbeScript(DefaultNav2NavigationSpec())
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(navProbe, "/navlab/navigation/status") {
		t.Fatalf("navigation probe script missing navigation status topic:\n%s", navProbe)
	}
	lifecycleProbe, err := Nav2LifecycleProbeScript(DefaultNav2NavigationSpec())
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(lifecycleProbe, "nav2_lifecycle_inactive") ||
		!strings.Contains(lifecycleProbe, "nav2_action_unavailable") ||
		!strings.Contains(lifecycleProbe, "tf2_echo") {
		t.Fatalf("nav2 lifecycle probe missing lifecycle/action/tf checks:\n%s", lifecycleProbe)
	}
	costmapProbe, err := CostmapHealthProbeScript(DefaultNav2NavigationSpec())
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(costmapProbe, "nav2_costmap_stale") ||
		!strings.Contains(costmapProbe, "navigation_costmap_unknown_ratio_too_high") {
		t.Fatalf("costmap probe missing stale/unknown ratio checks:\n%s", costmapProbe)
	}
	adapterScript, err := NavigationAdapterRuntimeScript(DefaultNav2NavigationSpec(), 10)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(adapterScript, "create_subscription") ||
		!strings.Contains(adapterScript, "clamp_count") ||
		!strings.Contains(adapterScript, "stale_costmap") ||
		!strings.Contains(adapterScript, "MaxAccelMPS2") ||
		!strings.Contains(adapterScript, "OccupancyGrid") ||
		!strings.Contains(adapterScript, `SPEC["SeedMapTopic"]`) ||
		!strings.Contains(adapterScript, "CostmapHealthTopic") {
		t.Fatalf("navigation adapter script missing subscriber/clamp behavior:\n%s", adapterScript)
	}
	controllerScript, err := FCUControllerRuntimeScript(DefaultFCUControllerSpec(), 10)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(controllerScript, `\"cartographer_odometry_topic\":\"\"`) {
		t.Fatalf("controller script should default Cartographer odometry relay off:\n%s", controllerScript)
	}
	if strings.Contains(controllerScript, `"cartographer_odometry_topic\":\"/odometry\"`) {
		t.Fatalf("controller script must not relay to diagnostic truth /odometry:\n%s", controllerScript)
	}
	if !strings.Contains(controllerScript, "cartographer_odom_pub = optional_publisher") {
		t.Fatalf("controller script missing optional Cartographer odometry relay hook:\n%s", controllerScript)
	}
	if strings.Contains(controllerScript, `map_to_odom = TransformStamped()`) {
		t.Fatalf("controller script must not publish fake map->odom when Cartographer owns /map:\n%s", controllerScript)
	}
	if strings.Contains(controllerScript, "StaticTransformBroadcaster") {
		t.Fatalf("controller script must not publish repeated static TF owned by SLAM backend:\n%s", controllerScript)
	}
	if strings.Contains(controllerScript, "TransformBroadcaster") ||
		strings.Contains(controllerScript, `create_publisher(Odometry, SPEC["slam_odom_topic"]`) ||
		strings.Contains(controllerScript, `create_publisher(String, SPEC["slam_status_topic"]`) {
		t.Fatalf("controller script must not publish SLAM-owned TF, odometry, or status:\n%s", controllerScript)
	}
	missionScript, err := NavigationMissionRuntimeScript(DefaultNav2NavigationSpec(), 10)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(missionScript, "NavigateToPose") ||
		!strings.Contains(missionScript, "nav2_action_unavailable") ||
		!strings.Contains(missionScript, "send_goal_async") {
		t.Fatalf("navigation mission script missing action behavior:\n%s", missionScript)
	}
	for _, name := range []string{"sensor.toml", "fcu.toml", "scan_stabilization.toml", "nav2_params.yaml", "navigation_adapter.toml"} {
		if _, err := os.Stat(filepath.Join(dir, name)); err != nil {
			t.Fatalf("expected generated %s: %v", name, err)
		}
	}
}

func TestHelperDefaultsMatchPythonRuntimeParityBoundary(t *testing.T) {
	sensor := DefaultSensorRuntimeSpec()
	if sensor.X2ScanInputTopic != "/lidar" ||
		sensor.X2ScanTopic != "/scan" ||
		sensor.X2StatusTopic != "/sim/x2/status" {
		t.Fatalf("sensor X2 topics drifted from Python runtime parity: %#v", sensor)
	}
	if sensor.RangefinderFrameID != "rangefinder_down_frame" ||
		sensor.RangefinderRangeTopic != "/rangefinder/down/range" ||
		sensor.RangefinderStatusTopic != "/rangefinder/down/status" {
		t.Fatalf("rangefinder contract drifted from Python runtime parity: %#v", sensor)
	}

	slam := DefaultSlamRuntimeSpec()
	if slam.LaserFrameID != "base_scan" ||
		slam.SlamOdomTopic != "/slam/odom" ||
		slam.OdometryTopic != "/cartographer/odometry_input" ||
		slam.CartographerTFTopic != "/navlab/slam/tf" ||
		slam.OdomSourceMode != "slam_tf" ||
		slam.MapFrameID != "map" ||
		slam.CartographerConfigurationBasename != "navlab_cartographer_2d_real.lua" {
		t.Fatalf("SLAM contract drifted from Python runtime parity: %#v", slam)
	}

	fcu := DefaultFCUControllerSpec()
	if fcu.CmdVelTopic != "/ap/v1/cmd_vel" ||
		fcu.PoseTopic != "/ap/v1/pose/filtered" ||
		fcu.RangefinderRangeTopic != "/rangefinder/down/range" ||
		fcu.LaserFrameID != "base_scan" ||
		fcu.TakeoffMinHeightM != 0.15 ||
		fcu.TakeoffMinHeightRatio != 0.35 ||
		!fcu.DisableArmingChecks ||
		!fcu.ForceArm {
		t.Fatalf("FCU contract drifted from Python runtime parity: %#v", fcu)
	}

	frame := DefaultFrameContractSpec()
	if frame.LaserFrameID != "base_scan" ||
		frame.RangefinderFrameID != "rangefinder_down_frame" ||
		frame.TruthDiagnosticTopic != "/odometry" {
		t.Fatalf("frame contract drifted from Python runtime parity: %#v", frame)
	}

	hover := DefaultSlamHoverSpec()
	if hover.TruthDiagnosticTopic != "/odometry" ||
		hover.RangefinderRangeTopic != "/rangefinder/down/range" ||
		hover.ProbeTimeoutSec < 120 {
		t.Fatalf("hover contract drifted from Python runtime parity: %#v", hover)
	}

	motion := DefaultMotionGateSpec()
	if motion.CmdVelTopic != "/ap/v1/cmd_vel" ||
		motion.SetpointOutputTopic != "/navlab/fcu/setpoint/output" ||
		motion.TruthDiagnosticTopic != "/odometry" {
		t.Fatalf("motion contract drifted from Python runtime parity: %#v", motion)
	}
}

func TestExplorationWorkflowStartsGoalTimingAfterControllerReady(t *testing.T) {
	script, err := ExplorationWorkflowRuntimeScript(DefaultExplorationWorkflowSpec(), 90)
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		`"ready_since": 0.0`,
		`if state["controller_ready"] and not was_ready:`,
		`state["ready_since"] = time.monotonic()`,
		`state["path_length_m"] = 0.0`,
		`ready_elapsed = time.monotonic() - float(state.get("ready_since", 0.0) or 0.0)`,
		`goal_index = min(int(ready_elapsed / segment_sec), min_goals - 1)`,
	} {
		if !strings.Contains(script, expected) {
			t.Fatalf("exploration workflow missing %q:\n%s", expected, script)
		}
	}
	if strings.Contains(script, `goal_index = min(int(elapsed / segment_sec), min_goals - 1)`) {
		t.Fatalf("exploration workflow still advances goals from task start:\n%s", script)
	}
}

func TestValidateScanStabilizationConfigFindsOrderedThresholdAndTruthBlockers(t *testing.T) {
	spec := DefaultScanStabilizationSpec()
	spec.InputScanTopic = "/scan"
	spec.OutputScanTopic = "/scan"
	spec.CompensationTiltDeg = 1
	spec.UsesGazeboTruthAsInput = true

	blockers := ValidateScanStabilizationConfig(spec)
	for _, expected := range []string{
		"scan_stabilization_config_invalid: input and output topics must differ",
		"scan_stabilization_config_invalid: tilt thresholds must be ordered",
		"scan_stabilization must not use Gazebo truth as input",
	} {
		if !contains(blockers, expected) {
			t.Fatalf("expected blocker %q in %#v", expected, blockers)
		}
	}
}

func TestWriteScanRobustnessBridgeOverrideRewritesIMUTopic(t *testing.T) {
	path := filepath.Join(t.TempDir(), "bridge.yaml")
	if err := WriteScanRobustnessBridgeOverride(path, "/imu/raw"); err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	text := string(content)
	if !strings.Contains(text, `ros_topic_name: "imu/raw"`) {
		t.Fatalf("bridge override did not rewrite imu topic:\n%s", text)
	}
	if strings.Count(text, `ros_topic_name: "imu"`) != 0 {
		t.Fatalf("bridge override still contains original imu topic:\n%s", text)
	}
}

func TestDeepRuntimeHelpersMarkedPortedPartial(t *testing.T) {
	registry := DefaultRegistry()
	for _, id := range []string{
		"sensors",
		"fcu-controller",
		"frame-contract",
		"slam-hover",
		"scan-stabilization",
		"exploration-workflow",
		"nav2-navigation-workflow",
		"scan-robustness-workflow",
	} {
		definition, err := registry.Get(id)
		if err != nil {
			t.Fatal(err)
		}
		if definition.MigrationStatus != "ported_partial" {
			t.Fatalf("%s migration status = %q, want ported_partial", id, definition.MigrationStatus)
		}
	}
}

func assertHasService(t *testing.T, plan ExecutionPlan, name string) {
	t.Helper()
	for _, service := range plan.RuntimeServices {
		if service.ServiceName == name {
			return
		}
	}
	t.Fatalf("execution plan missing service %q", name)
}

func assertHasArtifact(t *testing.T, plan ExecutionPlan, path string) {
	t.Helper()
	for _, artifact := range plan.GeneratedArtifacts {
		if artifact.Path == path {
			return
		}
	}
	t.Fatalf("execution plan missing artifact %q", path)
}

func assertMissingService(t *testing.T, plan ExecutionPlan, name string) {
	t.Helper()
	for _, service := range plan.RuntimeServices {
		if service.ServiceName == name {
			t.Fatalf("execution plan unexpectedly includes service %q", name)
		}
	}
}

func assertServiceCommandContains(t *testing.T, plan ExecutionPlan, name string, want string) {
	t.Helper()
	for _, service := range plan.RuntimeServices {
		if service.ServiceName == name {
			command := strings.Join(service.Command, " ")
			if !strings.Contains(command, want) {
				t.Fatalf("service %q command missing %q: %s", name, want, command)
			}
			return
		}
	}
	t.Fatalf("execution plan missing service %q", name)
}

func assertServiceEnvContains(t *testing.T, plan ExecutionPlan, name string, key string, want string) {
	t.Helper()
	for _, service := range plan.RuntimeServices {
		if service.ServiceName == name {
			if got := service.Env[key]; got != want {
				t.Fatalf("service %q env %s = %q, want %q; env=%#v", name, key, got, want, service.Env)
			}
			return
		}
	}
	t.Fatalf("execution plan missing service %q", name)
}

func assertServiceBefore(t *testing.T, plan ExecutionPlan, left string, right string) {
	t.Helper()
	leftIndex := -1
	rightIndex := -1
	for idx, service := range plan.RuntimeServices {
		if service.ServiceName == left {
			leftIndex = idx
		}
		if service.ServiceName == right {
			rightIndex = idx
		}
	}
	if leftIndex < 0 || rightIndex < 0 || leftIndex >= rightIndex {
		t.Fatalf("service order invalid: %q index=%d, %q index=%d, services=%#v", left, leftIndex, right, rightIndex, plan.RuntimeServices)
	}
}

func assertHasProbe(t *testing.T, plan ExecutionPlan, name string) {
	t.Helper()
	for _, probe := range plan.ROSProbes {
		if probe.Name == name {
			return
		}
	}
	t.Fatalf("execution plan missing probe %q", name)
}

func assertMissingProbe(t *testing.T, plan ExecutionPlan, name string) {
	t.Helper()
	for _, probe := range plan.ROSProbes {
		if probe.Name == name {
			t.Fatalf("execution plan unexpectedly has probe %q", name)
		}
	}
}

func assertProbeHasTopics(t *testing.T, plan ExecutionPlan, name string, topics []string) {
	t.Helper()
	for _, probe := range plan.ROSProbes {
		if probe.Name != name {
			continue
		}
		for _, topic := range topics {
			if !contains(probe.Topics, topic) {
				t.Fatalf("probe %q missing topic %q in %#v", name, topic, probe.Topics)
			}
		}
		return
	}
	t.Fatalf("execution plan missing probe %q", name)
}

func assertHasRosbag(t *testing.T, plan ExecutionPlan, name string) {
	t.Helper()
	for _, rosbag := range plan.RosbagRecords {
		if rosbag.Name == name {
			return
		}
	}
	t.Fatalf("execution plan missing rosbag %q", name)
}

func assertRosbagHasTopics(t *testing.T, plan ExecutionPlan, name string, topics []string) {
	t.Helper()
	for _, rosbag := range plan.RosbagRecords {
		if rosbag.Name != name {
			continue
		}
		for _, topic := range topics {
			if !contains(rosbag.Topics, topic) {
				t.Fatalf("rosbag %q missing topic %q in %#v", name, topic, rosbag.Topics)
			}
		}
		return
	}
	t.Fatalf("execution plan missing rosbag %q", name)
}

func assertRosbagMissingTopics(t *testing.T, plan ExecutionPlan, name string, topics []string) {
	t.Helper()
	for _, rosbag := range plan.RosbagRecords {
		if rosbag.Name != name {
			continue
		}
		for _, topic := range topics {
			if contains(rosbag.Topics, topic) {
				t.Fatalf("rosbag %q unexpectedly includes topic %q in %#v", name, topic, rosbag.Topics)
			}
		}
		return
	}
	t.Fatalf("execution plan missing rosbag %q", name)
}

func assertRosbagHasRequiredTopics(t *testing.T, plan ExecutionPlan, name string, topics []string) {
	t.Helper()
	for _, rosbag := range plan.RosbagRecords {
		if rosbag.Name != name {
			continue
		}
		for _, topic := range topics {
			if !contains(rosbag.RequiredTopics, topic) {
				t.Fatalf("rosbag %q missing required topic %q in %#v", name, topic, rosbag.RequiredTopics)
			}
		}
		for _, topic := range []string{"/navlab/navigation/path", "/navlab/navigation/recovery", "/odometry", "/navlab/official_maze/map", "/navlab/navigation/seed_map"} {
			if contains(rosbag.RequiredTopics, topic) {
				t.Fatalf("rosbag %q should record %q as review-only, not required: %#v", name, topic, rosbag.RequiredTopics)
			}
		}
		return
	}
	t.Fatalf("execution plan missing rosbag %q", name)
}

func assertRosbagRequiredMissingTopics(t *testing.T, plan ExecutionPlan, name string, topics []string) {
	t.Helper()
	for _, rosbag := range plan.RosbagRecords {
		if rosbag.Name != name {
			continue
		}
		for _, topic := range topics {
			if contains(rosbag.RequiredTopics, topic) {
				t.Fatalf("rosbag %q unexpectedly requires topic %q in %#v", name, topic, rosbag.RequiredTopics)
			}
		}
		return
	}
	t.Fatalf("execution plan missing rosbag %q", name)
}

func assertHasGate(t *testing.T, plan ExecutionPlan, name string) {
	t.Helper()
	for _, gate := range plan.ResultGates {
		if gate.Name == name {
			return
		}
	}
	t.Fatalf("execution plan missing gate %q", name)
}

func assertGateHasInputs(t *testing.T, plan ExecutionPlan, name string, inputs []string) {
	t.Helper()
	for _, gate := range plan.ResultGates {
		if gate.Name != name {
			continue
		}
		for _, input := range inputs {
			if !contains(gate.Inputs, input) {
				t.Fatalf("gate %q missing input %q in %#v", name, input, gate.Inputs)
			}
		}
		return
	}
	t.Fatalf("execution plan missing gate %q", name)
}

func assertGateMissingInputs(t *testing.T, plan ExecutionPlan, name string, inputs []string) {
	t.Helper()
	for _, gate := range plan.ResultGates {
		if gate.Name != name {
			continue
		}
		for _, input := range inputs {
			if contains(gate.Inputs, input) {
				t.Fatalf("gate %q unexpectedly includes input %q in %#v", name, input, gate.Inputs)
			}
		}
		return
	}
	t.Fatalf("execution plan missing gate %q", name)
}

func contains(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}
