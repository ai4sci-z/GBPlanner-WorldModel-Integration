package tasks

import (
	"encoding/binary"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/foxglove/mcap/go/mcap"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	simruntime "navlab/orchestration-sim/internal/runtime"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func copyAnyMap(input map[string]any) map[string]any {
	output := make(map[string]any, len(input))
	for key, value := range input {
		output[key] = value
	}
	return output
}

func TestEvaluateResultGatesReadsProbeAndRosbagArtifacts(t *testing.T) {
	artifactDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(artifactDir, "hover_probe.json"), []byte(`{"ok":true,"status":"live_probe"}`+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	rosbagDir := filepath.Join(artifactDir, "rosbag")
	if err := os.MkdirAll(rosbagDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(rosbagDir, "metadata.yaml"), []byte("topics_with_message_count:\n- topic_metadata:\n    name: /slam/odom\n  message_count: 3\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	evaluation := EvaluateResultGates(
		config.ProjectConfig{},
		config.TaskRuntimeConfig{
			Landing:       config.LandingConfig{HoverPolicy: "land_in_place", DefaultPolicy: "land_in_place"},
			FCUController: config.FCUControllerConfig{TakeoffAltM: 0.5},
			SlamHover:     config.SlamHoverConfig{HoverClaim: "evaluated"},
		},
		Plan{
			TaskID: "hover",
			Execution: helpers.ExecutionPlan{
				ROSProbes: []helpers.ROSProbePlan{{Name: "hover_probe", OutputPath: "hover_probe.json"}},
				RosbagRecords: []helpers.RosbagRecordPlan{
					{Name: "hover_rosbag", OutputDir: "rosbag", Topics: []string{"/slam/odom"}},
				},
			},
		},
		artifactDir,
		RuntimeSpecBundle{},
		RuntimeExecutionResult{},
		nil,
	)
	if evaluation.OK || !evaluation.Blocked {
		t.Fatalf("evaluation status = ok:%v blocked:%v", evaluation.OK, evaluation.Blocked)
	}
	if len(evaluation.ProbeOutputs) != 1 || !evaluation.ProbeOutputs[0].OK {
		t.Fatalf("probe outputs = %#v", evaluation.ProbeOutputs)
	}
	if len(evaluation.RosbagProfiles) != 1 || !evaluation.RosbagProfiles[0].OK {
		t.Fatalf("rosbag profiles = %#v", evaluation.RosbagProfiles)
	}
	if !blockersContainPrefix(evaluation.Blockers, helpers.LandingNotEvaluatedBlocker) {
		t.Fatalf("blockers = %#v", evaluation.Blockers)
	}
	if !stringSliceContains(evaluation.Blockers, "hover_mission_summary_missing") {
		t.Fatalf("blockers = %#v, want hover_mission_summary_missing", evaluation.Blockers)
	}
}

func TestEvaluateRosbagProfilesReadsMCAPWhenMetadataIsMissing(t *testing.T) {
	artifactDir := t.TempDir()
	rosbagDir := filepath.Join(artifactDir, "rosbag", "hover_rosbag")
	if err := os.MkdirAll(rosbagDir, 0o755); err != nil {
		t.Fatal(err)
	}
	writeTopicCountMCAP(t, filepath.Join(rosbagDir, "hover_rosbag_0.mcap"), "/slam/odom", 3)

	profiles := evaluateRosbagProfiles(Plan{
		Execution: helpers.ExecutionPlan{
			RosbagRecords: []helpers.RosbagRecordPlan{
				{Name: "hover_rosbag", OutputDir: filepath.Join("rosbag", "hover_rosbag"), Topics: []string{"/slam/odom"}},
			},
		},
	}, artifactDir)

	if len(profiles) != 1 {
		t.Fatalf("profiles = %#v", profiles)
	}
	if !profiles[0].OK || !profiles[0].Exists {
		t.Fatalf("profile = %#v, want ok existing MCAP fallback", profiles[0])
	}
	if profiles[0].MessageCounts["/slam/odom"] != 3 {
		t.Fatalf("message counts = %#v", profiles[0].MessageCounts)
	}
	if profiles[0].MessageCountsSource != "mcap_stream" {
		t.Fatalf("message counts source = %q", profiles[0].MessageCountsSource)
	}
	if len(profiles[0].MCAPPaths) != 1 || !strings.HasSuffix(profiles[0].MCAPPaths[0], "hover_rosbag_0.mcap") {
		t.Fatalf("mcap paths = %#v", profiles[0].MCAPPaths)
	}
}

func TestEvaluateProbeOutputsRetriesUntilJSONPayloadIsReadable(t *testing.T) {
	artifactDir := t.TempDir()
	probePath := filepath.Join(artifactDir, "slam_hover_probe.json")
	if err := os.WriteFile(probePath, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	go func() {
		time.Sleep(1200 * time.Millisecond)
		_ = os.WriteFile(probePath, []byte(`{"ok":false,"status":"sampled","samples":{"/external_nav/status":{"parsed":{"ready":false,"state":"low_rate","odom":{"input_topic":"/slam/odom","rate_ok":false}}}}}`), 0o644)
	}()

	outputs := evaluateProbeOutputs(Plan{
		Execution: helpers.ExecutionPlan{
			ROSProbes: []helpers.ROSProbePlan{{Name: "slam_hover_probe", OutputPath: "slam_hover_probe.json"}},
		},
	}, artifactDir)

	if len(outputs) != 1 || !outputs[0].Exists || outputs[0].OK || len(outputs[0].Payload) == 0 {
		t.Fatalf("probe outputs = %#v", outputs)
	}
	metrics := metricSummaryFromEvidence(outputs, nil)
	if metrics.ExternalNav["state"] != "low_rate" {
		t.Fatalf("external nav metrics = %#v", metrics.ExternalNav)
	}
}

func TestEvaluateResultGatesBlocksWhenRequiredSlamHoverProbeIsMissing(t *testing.T) {
	artifactDir := t.TempDir()

	evaluation := EvaluateResultGates(
		config.ProjectConfig{},
		config.TaskRuntimeConfig{
			Landing:       config.LandingConfig{HoverPolicy: helpers.PolicyAPLandModeAfterHover, DefaultPolicy: helpers.PolicyLandInPlace},
			FCUController: config.FCUControllerConfig{TakeoffAltM: 0.5},
			SlamHover:     config.SlamHoverConfig{HoverClaim: "evaluated"},
		},
		Plan{
			TaskID: "hover",
			Execution: helpers.ExecutionPlan{
				ROSProbes: []helpers.ROSProbePlan{{Name: "slam_hover_probe", OutputPath: "slam_hover_probe.json"}},
			},
		},
		artifactDir,
		RuntimeSpecBundle{},
		RuntimeExecutionResult{},
		nil,
	)

	if evaluation.OK || !evaluation.Blocked {
		t.Fatalf("evaluation status = ok:%v blocked:%v", evaluation.OK, evaluation.Blocked)
	}
	if !stringSliceContains(evaluation.Blockers, "probe_output_missing:slam_hover_probe") {
		t.Fatalf("blockers = %#v, want probe_output_missing:slam_hover_probe", evaluation.Blockers)
	}
}

func TestEvaluateResultGatesClassifiesKilledProbeWithEmptyOutput(t *testing.T) {
	artifactDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(artifactDir, "slam_hover_probe.json"), nil, 0o644); err != nil {
		t.Fatal(err)
	}

	evaluation := EvaluateResultGates(
		config.ProjectConfig{},
		config.TaskRuntimeConfig{
			Landing:       config.LandingConfig{HoverPolicy: helpers.PolicyAPLandModeAfterHover, DefaultPolicy: helpers.PolicyLandInPlace},
			FCUController: config.FCUControllerConfig{TakeoffAltM: 0.5},
			SlamHover:     config.SlamHoverConfig{HoverClaim: "evaluated"},
		},
		Plan{
			TaskID: "hover",
			Execution: helpers.ExecutionPlan{
				ROSProbes: []helpers.ROSProbePlan{{Name: "slam_hover_probe", OutputPath: "slam_hover_probe.json"}},
			},
		},
		artifactDir,
		RuntimeSpecBundle{},
		RuntimeExecutionResult{
			ProbeResults: []simruntime.ProbeResult{{Name: "slam_hover_probe", ReturnCode: -1}},
		},
		nil,
	)

	for _, want := range []string{
		"probe_failed:slam_hover_probe:rc=-1",
		"probe_killed:slam_hover_probe",
		"probe_output_empty:slam_hover_probe",
	} {
		if !stringSliceContains(evaluation.Blockers, want) {
			t.Fatalf("blockers = %#v, want %s", evaluation.Blockers, want)
		}
	}
	if len(evaluation.ProbeOutputs) != 1 || !evaluation.ProbeOutputs[0].Exists || !evaluation.ProbeOutputs[0].Empty {
		t.Fatalf("probe outputs = %#v, want existing empty output", evaluation.ProbeOutputs)
	}
}

func TestEvaluateResultGatesIgnoresDiagnosticSlamHoverProbeFailure(t *testing.T) {
	artifactDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(artifactDir, "slam_hover_probe.json"), nil, 0o644); err != nil {
		t.Fatal(err)
	}

	evaluation := EvaluateResultGates(
		config.ProjectConfig{},
		config.TaskRuntimeConfig{
			Landing:       config.LandingConfig{HoverPolicy: helpers.PolicyAPLandModeAfterHover, DefaultPolicy: helpers.PolicyLandInPlace},
			FCUController: config.FCUControllerConfig{TakeoffAltM: 0.5},
			SlamHover:     config.SlamHoverConfig{HoverClaim: "evaluated"},
		},
		Plan{
			TaskID: "hover",
			Execution: helpers.ExecutionPlan{
				ROSProbes: []helpers.ROSProbePlan{{Name: "slam_hover_probe", OutputPath: "slam_hover_probe.json"}},
			},
		},
		artifactDir,
		RuntimeSpecBundle{Probes: []simruntime.ProbeSpec{{Name: "slam_hover_probe", Required: false}}},
		RuntimeExecutionResult{
			ProbeResults: []simruntime.ProbeResult{{Name: "slam_hover_probe", ReturnCode: -1}},
		},
		nil,
	)

	for _, unwanted := range []string{
		"probe_failed:slam_hover_probe:rc=-1",
		"probe_killed:slam_hover_probe",
		"probe_output_empty:slam_hover_probe",
	} {
		if stringSliceContains(evaluation.Blockers, unwanted) {
			t.Fatalf("blockers = %#v, must not contain %s", evaluation.Blockers, unwanted)
		}
	}
	if len(evaluation.ProbeOutputs) != 1 || !evaluation.ProbeOutputs[0].Exists || !evaluation.ProbeOutputs[0].Empty {
		t.Fatalf("probe outputs = %#v, want existing empty diagnostic output", evaluation.ProbeOutputs)
	}
}

func writeTopicCountMCAP(t *testing.T, path string, topic string, count int) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteSchema(&mcap.Schema{ID: 1, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 1, SchemaID: 1, Topic: topic, MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < count; i++ {
		stamp := uint64(i+1) * 1_000_000
		if err := writer.WriteMessage(&mcap.Message{ChannelID: 1, LogTime: stamp, PublishTime: stamp, Data: []byte{0}}); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestHoverMissionBlockersRequirePythonMissionSummary(t *testing.T) {
	if blockers := hoverMissionBlockers(nil); !stringSliceContains(blockers, "hover_mission_summary_missing") {
		t.Fatalf("blockers = %#v, want hover_mission_summary_missing", blockers)
	}
	valid := map[string]any{
		"ok":                         true,
		"hover_body_ok":              true,
		"landing_ok":                 true,
		"phases_seen":                []any{"wait_ready", "guided", "arm", "takeoff", "hover_settle", "hover_hold", "landing", "complete"},
		"guided_seen":                true,
		"armed_seen":                 true,
		"takeoff_ack_ok":             false,
		"airborne_seen":              true,
		"local_position_count":       float64(12),
		"setpoints_sent_count":       float64(40),
		"target_alt_m":               float64(0.5),
		"takeoff_alt_m":              float64(0.5),
		"current_z_ned":              float64(-0.45),
		"altitude_error_m":           float64(0.05),
		"hover_altitude_tolerance_m": float64(0.18),
		"hover_altitude_crosscheck": map[string]any{
			"ok":           true,
			"sample_count": float64(20),
			"sources": map[string]any{
				"fcu_local_z_ned":               float64(-0.45),
				"fcu_local_height_m":            float64(0.5),
				"external_nav_height_m":         float64(0.49),
				"rangefinder_range_m":           float64(0.55),
				"rangefinder_relative_height_m": float64(0.5),
			},
			"diffs": map[string]any{
				"fcu_vs_external_abs_m":         float64(0.01),
				"fcu_vs_rangefinder_abs_m":      float64(0),
				"external_vs_rangefinder_abs_m": float64(0.01),
				"fcu_target_error_m":            float64(0),
				"external_target_error_m":       float64(0.01),
				"rangefinder_target_error_m":    float64(0),
			},
			"missing_sources": []any{},
			"over_tolerance":  []any{},
		},
		"hover_hold_sec": float64(18),
		"hover_drift": map[string]any{
			"sample_count":           float64(20),
			"duration_sec":           float64(17.9),
			"duration_tolerance_sec": float64(0.25),
			"horizontal_drift_m":     float64(0.05),
			"z_span_m":               float64(0.02),
			"max_horizontal_drift_m": float64(0.10),
			"max_altitude_drift_m":   float64(0.30),
			"quality":                "tight",
			"ok":                     true,
		},
		"landing": map[string]any{
			"land_command_accepted": true,
			"touchdown_confirmed":   true,
			"disarmed":              true,
			"motors_safe":           true,
		},
	}
	if blockers := hoverMissionBlockers(valid); len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none", blockers)
	}
	aborted := copyAnyMap(valid)
	aborted["ok"] = false
	aborted["hover_body_ok"] = false
	aborted["mission_phase_history"] = []any{
		map[string]any{"state": "S6 hover_hold", "reason": "holding_position"},
		map[string]any{"state": "S_abort", "guard": "abort", "reason": "slam_quality_lost_after_airborne", "blocker": "slam_quality_lost_after_airborne"},
	}
	aborted = subsetHoverMissionSummary(aborted)
	blockers := hoverMissionBlockers(aborted)
	if !stringSliceContains(blockers, "hover_mission_abort:slam_quality_lost_after_airborne") {
		t.Fatalf("blockers = %#v, want hover mission abort reason", blockers)
	}
	spanFailed := copyAnyMap(valid)
	spanFailed["ok"] = false
	spanFailed["hover_body_ok"] = false
	spanFailed["hover_drift"] = map[string]any{
		"sample_count":           float64(20),
		"duration_sec":           float64(17.9),
		"duration_tolerance_sec": float64(0.25),
		"horizontal_drift_m":     float64(0.02),
		"horizontal_span_m":      float64(0.21),
		"max_horizontal_drift_m": float64(0.10),
		"max_altitude_drift_m":   float64(0.30),
		"quality":                "tight",
		"horizontal_drift_ok":    true,
		"horizontal_span_ok":     false,
		"z_span_ok":              true,
		"duration_ok":            true,
		"ok":                     false,
	}
	blockers = hoverMissionBlockers(spanFailed)
	if !stringSliceContains(blockers, "hover_mission_drift_not_ok") ||
		!stringSliceContains(blockers, "hover_mission_horizontal_span_not_ok") {
		t.Fatalf("blockers = %#v, want generic and span-specific drift blockers", blockers)
	}
	spanYellow := copyAnyMap(valid)
	spanYellow["hover_drift"] = map[string]any{
		"sample_count":                 float64(20),
		"duration_sec":                 float64(17.9),
		"duration_tolerance_sec":       float64(0.25),
		"horizontal_drift_m":           float64(0.02),
		"horizontal_span_m":            float64(0.118),
		"max_horizontal_drift_m":       float64(0.10),
		"hover_span_target_m":          float64(0.10),
		"hover_span_hard_cap_m":        float64(0.15),
		"max_altitude_drift_m":         float64(0.30),
		"quality":                      "tight",
		"horizontal_drift_ok":          true,
		"horizontal_span_ok":           true,
		"horizontal_span_target_ok":    false,
		"horizontal_span_hard_cap_ok":  true,
		"horizontal_span_tier":         "yellow",
		"horizontal_drift_target_ok":   true,
		"horizontal_drift_hard_cap_ok": true,
		"horizontal_drift_tier":        "green",
		"z_span_ok":                    true,
		"duration_ok":                  true,
		"ok":                           true,
	}
	if blockers := hoverMissionBlockers(spanYellow); len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none for target exceed below hard cap", blockers)
	}
	jumpFailed := copyAnyMap(valid)
	jumpFailed["ok"] = false
	jumpFailed["hover_body_ok"] = false
	jumpFailed["hover_drift"] = map[string]any{
		"sample_count":                                float64(20),
		"duration_sec":                                float64(17.9),
		"duration_tolerance_sec":                      float64(0.25),
		"horizontal_drift_m":                          float64(0.02),
		"horizontal_span_m":                           float64(0.03),
		"quality":                                     "tight",
		"horizontal_drift_ok":                         true,
		"horizontal_span_ok":                          true,
		"z_span_ok":                                   true,
		"duration_ok":                                 true,
		"no_slam_quality_jump_in_hover_window":        false,
		"no_external_nav_loss_after_airborne":         false,
		"no_mavlink_external_nav_loss_after_airborne": true,
		"ok": true,
	}
	blockers = hoverMissionBlockers(jumpFailed)
	for _, want := range []string{
		"hover_mission_slam_quality_jump_in_hover_window",
		"hover_mission_external_nav_lost_after_airborne",
	} {
		if !stringSliceContains(blockers, want) {
			t.Fatalf("blockers = %#v, want %s", blockers, want)
		}
	}
	tooLow := map[string]any{
		"ok":                         false,
		"hover_body_ok":              false,
		"landing_ok":                 false,
		"phases_seen":                []any{"wait_ready", "guided", "arm", "takeoff", "hover_settle"},
		"guided_seen":                true,
		"armed_seen":                 true,
		"takeoff_ack_ok":             false,
		"airborne_seen":              true,
		"local_position_count":       float64(5),
		"setpoints_sent_count":       float64(10),
		"target_alt_m":               float64(0.5),
		"takeoff_alt_m":              float64(0.5),
		"current_z_ned":              float64(-0.19),
		"altitude_error_m":           float64(0.31),
		"hover_altitude_tolerance_m": float64(0.18),
		"hover_altitude_crosscheck": map[string]any{
			"ok":           false,
			"sample_count": float64(2),
			"over_tolerance": []any{
				"fcu_target_error_m",
				"external_target_error_m",
				"rangefinder_target_error_m",
			},
		},
		"hover_hold_sec": float64(18),
		"hover_drift": map[string]any{
			"sample_count":           float64(1),
			"duration_sec":           float64(2.0),
			"duration_tolerance_sec": float64(0.25),
			"quality":                "unusable",
			"ok":                     false,
		},
		"landing": map[string]any{
			"land_command_accepted": false,
			"touchdown_confirmed":   false,
			"disarmed":              false,
			"motors_safe":           false,
		},
	}
	blockers = hoverMissionBlockers(tooLow)
	for _, want := range []string{
		"hover_mission_not_ok",
		"hover_mission_hover_hold_missing",
		"hover_mission_takeoff_ack_missing",
		"hover_mission_target_altitude_not_reached",
		"hover_mission_altitude_crosscheck_failed",
		"hover_mission_hold_samples_missing",
		"hover_mission_hold_duration_short",
		"hover_mission_drift_not_ok",
		"hover_mission_drift_quality_unacceptable",
		"hover_mission_body_not_ok",
		"hover_mission_landing_not_ok",
		"hover_mission_landing_touchdown_confirmed_missing",
		"hover_mission_landing_disarmed_missing",
		"hover_mission_landing_motors_safe_missing",
	} {
		if !stringSliceContains(blockers, want) {
			t.Fatalf("blockers = %#v, want %s", blockers, want)
		}
	}
}

func TestHoverMissionBlockersRejectMissingAltitudeEvidence(t *testing.T) {
	mission := map[string]any{
		"ok":                   true,
		"hover_body_ok":        true,
		"landing_ok":           true,
		"phases_seen":          []any{"hover_hold"},
		"guided_seen":          true,
		"armed_seen":           true,
		"takeoff_ack_ok":       true,
		"airborne_seen":        true,
		"local_position_count": float64(1),
		"setpoints_sent_count": float64(1),
		"target_alt_m":         float64(0.5),
		"hover_hold_sec":       float64(18),
		"hover_drift": map[string]any{
			"sample_count":           float64(2),
			"duration_sec":           float64(18),
			"duration_tolerance_sec": float64(0.25),
			"ok":                     true,
		},
		"landing": map[string]any{
			"land_command_accepted": true,
			"touchdown_confirmed":   true,
			"disarmed":              true,
			"motors_safe":           true,
		},
	}
	blockers := hoverMissionBlockers(mission)
	if !stringSliceContains(blockers, "hover_mission_altitude_evidence_missing") {
		t.Fatalf("blockers = %#v, want hover_mission_altitude_evidence_missing", blockers)
	}
}

func TestHoverMissionBlockersAllowPostLandingExternalNavReadyDropWhenMissionCompleted(t *testing.T) {
	for _, fsmState := range []string{"S12 landing_complete", "S13 task_success"} {
		mission := map[string]any{
			"ok":                   true,
			"reason":               "hover_complete",
			"mission_phase_state":  fsmState,
			"require_external_nav": true,
			"external_nav_ready":   false,
			"phases_seen":          []any{"guided", "arm", "takeoff", "hover_hold", "complete"},
			"guided_seen":          true,
			"armed_seen":           true,
			"airborne_seen":        true,
			"local_position_count": float64(10),
			"setpoints_sent_count": float64(10),
			"target_alt_m":         float64(0.5),
			"current_z_ned":        float64(-0.45),
			"altitude_error_m":     float64(0.01),
			"hover_altitude_crosscheck": map[string]any{
				"sample_count": float64(3),
				"ok":           true,
			},
			"takeoff_ack_ok": true,
			"hover_hold_sec": float64(18),
			"hover_drift": map[string]any{
				"sample_count": float64(3),
				"duration_sec": float64(18),
				"ok":           true,
				"quality":      "tight",
			},
			"hover_body_ok": true,
			"landing_ok":    true,
			"landing": map[string]any{
				"ok":                    true,
				"land_command_accepted": true,
				"touchdown_confirmed":   true,
				"disarmed":              true,
				"motors_safe":           true,
			},
		}
		if blockers := hoverMissionBlockers(mission); len(blockers) != 0 {
			t.Fatalf("state=%q blockers = %#v, want none for completed mission with post-landing external_nav_ready=false", fsmState, blockers)
		}
	}
}

func TestExternalNavFeedbackBlockersRequireSlamBridgeAndFCUFeedback(t *testing.T) {
	externalNav := map[string]any{
		"ready": true,
		"odom":  map[string]any{"input_topic": "/slam/odom"},
	}
	mavlinkExternalNav := map[string]any{
		"state":                     "sending",
		"ready":                     true,
		"input_topic":               "/external_nav/odom",
		"sent_count":                float64(12),
		"local_position_count":      float64(5),
		"local_position_age_ms":     float64(50),
		"max_local_position_age_ms": float64(1000),
		"fcu_local_position_ready":  true,
	}
	if blockers := externalNavFeedbackBlockers(externalNav, mavlinkExternalNav, nil); len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none", blockers)
	}

	externalNav["odom"] = map[string]any{"input_topic": "/slam/odom_corrected"}
	if blockers := externalNavFeedbackBlockers(externalNav, mavlinkExternalNav, nil); len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none for fail-closed corrected SLAM odom", blockers)
	}

	mavlinkExternalNav["local_position_count"] = float64(0)
	mavlinkExternalNav["fcu_local_position_ready"] = false
	blockers := externalNavFeedbackBlockers(externalNav, mavlinkExternalNav, nil)
	if !stringSliceContains(blockers, "external_nav_not_seen_by_fcu") {
		t.Fatalf("blockers = %#v, want external_nav_not_seen_by_fcu", blockers)
	}
}

func TestLandingEvidenceFallsBackToHoverMissionSummary(t *testing.T) {
	landing := landingFromHoverMissionSummary(map[string]any{
		"landing_ok": true,
		"landing": map[string]any{
			"ok":                         true,
			"claim":                      "evaluated",
			"policy":                     "ap_land_mode_after_hover",
			"state":                      "landing_complete",
			"land_command_accepted":      true,
			"landed_confirmed":           true,
			"touchdown_confirmed":        true,
			"disarmed":                   true,
			"motors_safe":                true,
			"require_disarm":             true,
			"require_motors_safe":        true,
			"uses_gazebo_truth_as_input": false,
			"blockers":                   []any{},
			"return_home": map[string]any{
				"required": false,
				"ok":       true,
				"state":    "not_required",
			},
		},
	})
	if landing == nil || !landing.OK || landing.Claim != "evaluated" || landing.State != "landing_complete" {
		t.Fatalf("landing = %#v", landing)
	}
}

func TestExternalNavFeedbackBlockersRejectStaleFCULocalPosition(t *testing.T) {
	blockers := externalNavFeedbackBlockers(
		map[string]any{
			"ready": true,
			"odom":  map[string]any{"input_topic": "/slam/odom"},
		},
		map[string]any{
			"state":                     "sending",
			"ready":                     false,
			"input_topic":               "/external_nav/odom",
			"sent_count":                float64(12),
			"local_position_count":      float64(554),
			"local_position_age_ms":     float64(58650.282),
			"max_local_position_age_ms": float64(1000),
			"fcu_local_position_ready":  false,
		},
		nil,
	)
	for _, want := range []string{"mavlink_external_nav_not_ready", "external_nav_fcu_local_position_not_ready", "external_nav_fcu_local_position_stale"} {
		if !stringSliceContains(blockers, want) {
			t.Fatalf("blockers = %#v, want %s", blockers, want)
		}
	}
}

func TestExternalNavFeedbackBlockersRejectDiagnosticTruthInput(t *testing.T) {
	blockers := externalNavFeedbackBlockers(
		map[string]any{
			"ready": true,
			"odom":  map[string]any{"input_topic": "/odometry"},
		},
		map[string]any{
			"state":                    "sending",
			"ready":                    true,
			"input_topic":              "/external_nav/odom",
			"sent_count":               float64(12),
			"local_position_count":     float64(5),
			"local_position_age_ms":    float64(50),
			"fcu_local_position_ready": true,
		},
		nil,
	)
	for _, want := range []string{"external_nav_not_using_slam_odom", "external_nav_uses_diagnostic_truth_input"} {
		if !stringSliceContains(blockers, want) {
			t.Fatalf("blockers = %#v, want %s", blockers, want)
		}
	}
}

func TestExternalNavFeedbackBlockersAllowPostLandingFinalReadinessDropWhenMissionCompleted(t *testing.T) {
	blockers := externalNavFeedbackBlockers(
		map[string]any{
			"ready": false,
			"odom":  map[string]any{"input_topic": "/slam/odom_corrected"},
		},
		map[string]any{
			"state":                     "sending",
			"ready":                     false,
			"input_topic":               "/external_nav/odom",
			"sent_count":                float64(1066),
			"local_position_count":      float64(441),
			"local_position_age_ms":     float64(1795),
			"max_local_position_age_ms": float64(1000),
			"fcu_local_position_ready":  false,
		},
		map[string]any{
			"ok":                  true,
			"reason":              "hover_complete",
			"mission_phase_state": "S12 landing_complete",
		},
	)
	if len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none for post-landing final readiness drop after completed mission", blockers)
	}
}

func TestLandingEvidenceSupportsParsedProbeSample(t *testing.T) {
	landing := landingFromProbeOutputs([]ProbeOutputSummary{
		{
			Payload: map[string]any{
				"samples": map[string]any{
					"/navlab/landing/status": map[string]any{
						"parsed": map[string]any{
							"ok":       false,
							"claim":    helpers.ClaimNotEvaluated,
							"policy":   helpers.PolicyLandInPlace,
							"state":    "waiting_for_task_completion",
							"blockers": []any{"task_completion_required_before_landing"},
						},
					},
				},
			},
		},
		{
			Payload: map[string]any{
				"samples": map[string]any{
					"/navlab/landing/status": map[string]any{
						"parsed": map[string]any{
							"ok":                    true,
							"claim":                 helpers.ClaimEvaluated,
							"policy":                helpers.PolicyLandInPlace,
							"state":                 "landing_complete",
							"task_completed":        true,
							"land_command_accepted": true,
							"landed_confirmed":      true,
							"touchdown_confirmed":   true,
							"disarmed":              true,
							"motors_safe":           true,
							"blockers":              []any{},
						},
					},
				},
			},
		},
	})
	if landing == nil || !landing.OK || landing.Claim != helpers.ClaimEvaluated {
		t.Fatalf("landing = %#v", landing)
	}
}

func TestEvaluateResultGatesUsesLandingStatusFromNavigationProbe(t *testing.T) {
	artifactDir := t.TempDir()
	probe := `{
		"ok": true,
		"status": "sampled",
		"samples": {
			"/navlab/landing/status": {
				"parsed": {
					"ok": true,
					"claim": "evaluated",
					"policy": "land_in_place",
					"state": "landing_complete",
					"task_completed": true,
					"land_command_accepted": true,
					"landed_confirmed": true,
					"touchdown_confirmed": true,
					"disarmed": true,
					"motors_safe": true,
					"blockers": []
				}
			}
		}
	}`
	if err := os.WriteFile(filepath.Join(artifactDir, "navigation_status_probe.json"), []byte(probe+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	earlyProbe := `{
		"ok": true,
		"status": "sampled",
		"samples": {
			"/navlab/landing/status": {
				"parsed": {
					"ok": false,
					"claim": "not_evaluated",
					"policy": "land_in_place",
					"state": "waiting_for_task_completion",
					"blockers": ["task_completion_required_before_landing"]
				}
			}
		}
	}`
	if err := os.WriteFile(filepath.Join(artifactDir, "slam_hover_probe.json"), []byte(earlyProbe+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	evaluation := EvaluateResultGates(
		config.ProjectConfig{},
		config.TaskRuntimeConfig{
			Landing: config.LandingConfig{
				Enabled:       true,
				DefaultPolicy: helpers.PolicyLandInPlace,
			},
		},
		Plan{
			TaskID: "navigation",
			Execution: helpers.ExecutionPlan{
				ROSProbes: []helpers.ROSProbePlan{
					{Name: "slam_hover_probe", OutputPath: "slam_hover_probe.json"},
					{Name: "navigation_status_probe", OutputPath: "navigation_status_probe.json"},
				},
			},
		},
		artifactDir,
		RuntimeSpecBundle{},
		RuntimeExecutionResult{},
		nil,
	)
	if !evaluation.Landing.OK || evaluation.Landing.LandingClaim != helpers.ClaimEvaluated {
		t.Fatalf("landing acceptance = %#v", evaluation.Landing)
	}
	if blockersContainPrefix(evaluation.Blockers, "task_completion_required_before_landing") {
		t.Fatalf("blockers = %#v", evaluation.Blockers)
	}
}

func TestSummarizeGazeboModelOdomUsesHoverHoldWindow(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_rosbag_0.mcap")
	writeGazeboHoverWindowMCAP(t, path)

	summary, err := summarizeGazeboModelOdom(path)
	if err != nil {
		t.Fatal(err)
	}
	if summary["window_source"] != "hover_status_phase_hover_hold" {
		t.Fatalf("window_source = %#v", summary["window_source"])
	}
	if got := metricInt(summary, "sample_count"); got != 3 {
		t.Fatalf("sample_count = %d, want 3", got)
	}
	if got := metricFloat(summary, "max_horizontal_drift_m"); math.Abs(got-0.2) > 1e-9 {
		t.Fatalf("max_horizontal_drift_m = %v, want hover-window drift 0.2", got)
	}
	if got := metricFloat(summary, "x_span_m"); math.Abs(got-0.2) > 1e-9 {
		t.Fatalf("x_span_m = %v, want 0.2", got)
	}
}

func TestGazeboModelHoverDriftIsReviewOnlyAndDoesNotHardBlock(t *testing.T) {
	blockers := gazeboModelHoverDriftMetricBlockers(map[string]any{
		"sample_count":            float64(636),
		"max_horizontal_drift_m":  float64(0.33955787847100694),
		"source_topic":            helpers.DiagnosticGazeboModelOdometryTopic,
		"uses_gazebo_truth_input": false,
	}, 0.10)
	if len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none because Gazebo drift is review-only", blockers)
	}

	blockers = gazeboModelHoverDriftMetricBlockers(map[string]any{
		"sample_count":            float64(636),
		"max_horizontal_drift_m":  float64(0.095),
		"source_topic":            helpers.DiagnosticGazeboModelOdometryTopic,
		"uses_gazebo_truth_input": false,
	}, 0.10)
	if len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none below 0.10m", blockers)
	}
}

func TestSummarizeHoverXYAlignmentComparesFourSources(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_xy_alignment_rosbag_0.mcap")
	writeHoverXYAlignmentMCAP(t, path, false)

	summary, err := summarizeHoverXYAlignment(path)
	if err != nil {
		t.Fatal(err)
	}
	if ok, _ := summary["ok"].(bool); !ok {
		t.Fatalf("xy alignment = %#v, want ok", summary)
	}
	sources := mapFromAny(summary["sources"])
	for _, key := range []string{"gazebo_model_odometry", "fcu_local_position_pose", "external_nav_odom_candidate", "slam_odom_corrected", "external_nav_odom"} {
		source := mapFromAny(sources[key])
		if got := metricInt(source, "sample_count"); got != 3 {
			t.Fatalf("%s sample_count = %d, want 3: %#v", key, got, source)
		}
	}
	pairwise := mapFromAny(summary["pairwise"])
	pair := mapFromAny(pairwise["gazebo_model_odometry__external_nav_odom_candidate"])
	if got := metricFloat(pair, "direction_cosine"); math.Abs(got-1.0) > 1e-9 {
		t.Fatalf("direction cosine = %v, want 1: %#v", got, pair)
	}
	protocolPair := mapFromAny(pairwise["gazebo_model_odometry__external_nav_odom"])
	if got := metricFloat(protocolPair, "direction_cosine"); math.Abs(got-1.0) > 1e-9 {
		t.Fatalf("protocol direction cosine = %v, want 1 in ROS topic frame: %#v", got, protocolPair)
	}
	passThroughPair := mapFromAny(pairwise["external_nav_odom_candidate__slam_odom_corrected"])
	if got := metricFloat(passThroughPair, "direction_cosine"); math.Abs(got-1.0) > 1e-9 {
		t.Fatalf("candidate/corrected direction cosine = %v, want 1 in native ROS XY: %#v", got, passThroughPair)
	}
	if usedTruth, _ := summary["uses_gazebo_truth_input"].(bool); usedTruth {
		t.Fatalf("Gazebo must remain review-only, not runtime input: %#v", summary)
	}
}

func TestSummarizeHoverXYAlignmentIncludesGazeboModelEvidence(t *testing.T) {
	artifactDir := t.TempDir()
	bagDir := filepath.Join(artifactDir, "rosbag", "hover_rosbag")
	if err := os.MkdirAll(bagDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(artifactDir, "bridge_override.yaml"), []byte(`---
- ros_topic_name: "gazebo/model/odometry"
  gz_topic_name: "/model/{{ robot_name }}/odometry"
  ros_type_name: "nav_msgs/msg/Odometry"
  gz_type_name: "gz.msgs.Odometry"
  direction: GZ_TO_ROS
`), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(artifactDir, "model_overlay.sdf"), []byte(`<?xml version='1.0'?>
<sdf version="1.9">
  <model name="iris_with_lidar">
    <plugin filename="gz-sim-odometry-publisher-system" name="gz::sim::systems::OdometryPublisher">
      <odom_frame>odom</odom_frame>
      <robot_base_frame>base_link</robot_base_frame>
    </plugin>
    <plugin name="ArduPilotPlugin" filename="ArduPilotPlugin">
      <modelXYZToAirplaneXForwardZDown degrees="true">0 0 0 180 0 0</modelXYZToAirplaneXForwardZDown>
      <gazeboXYZToNED degrees="true">0 0 0 180 0 90</gazeboXYZToNED>
      <imuName>imu_link::imu_sensor</imuName>
    </plugin>
  </model>
</sdf>
`), 0o644); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(bagDir, "hover_rosbag_0.mcap")
	writeHoverXYAlignmentMCAP(t, path, false)

	summary, err := summarizeHoverXYAlignment(path)
	if err != nil {
		t.Fatal(err)
	}
	evidence := mapFromAny(summary["gazebo_model_odometry_evidence"])
	if ok, _ := evidence["ok"].(bool); !ok {
		t.Fatalf("gazebo evidence = %#v, want ok", evidence)
	}
	for key, want := range map[string]string{
		"bridge_gz_topic_name":          "/model/{{ robot_name }}/odometry",
		"expected_bridge_gz_topic_name": "/model/iris_with_lidar/odometry",
		"sdf_model_name":                "iris_with_lidar",
		"sdf_odom_frame":                "odom",
		"sdf_robot_base_frame":          "base_link",
		"message_frame_id":              "odom",
		"message_child_frame_id":        "base_link",
		"sdf_gazebo_xyz_to_ned":         "0 0 0 180 0 90",
		"sdf_model_xyz_to_airplane":     "0 0 0 180 0 0",
	} {
		if got, _ := evidence[key].(string); got != want {
			t.Fatalf("evidence[%s] = %#v, want %#v; full=%#v", key, got, want, evidence)
		}
	}
	projection := mapFromAny(evidence["gazebo_xyz_to_ned_projection"])
	if projection["formula"] != "projected_x=raw_y, projected_y=-raw_x" {
		t.Fatalf("projection = %#v", projection)
	}
	if preserved, _ := projection["magnitude_preserved"].(bool); !preserved {
		t.Fatalf("projection should preserve XY magnitude: %#v", projection)
	}
	if len(mapFromAny(projection["alignment_to_sources"])) != 3 {
		t.Fatalf("projection alignment = %#v", projection["alignment_to_sources"])
	}
}

func TestSummarizeHoverXYAlignmentFlagsDirectionMismatch(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_xy_alignment_bad_rosbag_0.mcap")
	writeHoverXYAlignmentMCAP(t, path, true)

	summary, err := summarizeHoverXYAlignment(path)
	if err != nil {
		t.Fatal(err)
	}
	if ok, _ := summary["ok"].(bool); ok {
		t.Fatalf("xy alignment = %#v, want mismatch", summary)
	}
	blockers := testStringSliceFromAny(summary["blockers"])
	if !stringSliceContains(blockers, "hover_xy_alignment_direction_mismatch:external_nav_odom_candidate__slam_odom_corrected") {
		t.Fatalf("blockers = %#v, want external nav candidate mismatch", blockers)
	}
}

func TestSummarizeHoverXYAlignmentKeepsGazeboOnlyMismatchReviewOnly(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_xy_alignment_gazebo_mismatch_rosbag_0.mcap")
	writeHoverXYAlignmentMCAPWithMode(t, path, "gazebo_only_mismatch")

	summary, err := summarizeHoverXYAlignment(path)
	if err != nil {
		t.Fatal(err)
	}
	if ok, _ := summary["ok"].(bool); !ok {
		t.Fatalf("xy alignment = %#v, want ok when only review-only Gazebo source disagrees", summary)
	}
	blockers := testStringSliceFromAny(summary["blockers"])
	if len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none for Gazebo-only disagreement", blockers)
	}
	auditBlockers := testStringSliceFromAny(summary["audit_blockers"])
	if !stringSliceContains(auditBlockers, "hover_xy_alignment_direction_mismatch:gazebo_model_odometry__slam_odom_corrected") {
		t.Fatalf("audit_blockers = %#v, want Gazebo mismatch retained for audit", auditBlockers)
	}
}

func TestHoverXYAlignmentBlockersPromoteEvidenceDisagreement(t *testing.T) {
	blockers := hoverXYAlignmentBlockers(map[string]any{
		"ok": false,
		"blockers": []any{
			"hover_xy_evidence_disagreement",
			"hover_xy_alignment_direction_mismatch:gazebo_model_odometry__external_nav_odom_candidate",
		},
	})

	for _, want := range []string{
		"hover_xy_evidence_disagreement",
		"hover_xy_alignment_direction_mismatch:gazebo_model_odometry__external_nav_odom_candidate",
	} {
		if !stringSliceContains(blockers, want) {
			t.Fatalf("blockers = %#v, want %s", blockers, want)
		}
	}
}

func TestSummarizeScanReferenceHoverDriftUsesOnlyScanWindow(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_scan_rosbag_0.mcap")
	writeScanReferenceHoverWindowMCAP(t, path)

	summary, err := summarizeScanReferenceHoverDrift(path)
	if err != nil {
		t.Fatal(err)
	}
	if summary["window_source"] != "hover_status_phase_hover_hold" {
		t.Fatalf("window_source = %#v", summary["window_source"])
	}
	if summary["source_topic"] != "/scan" {
		t.Fatalf("source_topic = %#v", summary["source_topic"])
	}
	if got := metricInt(summary, "sample_count"); got != 3 {
		t.Fatalf("sample_count = %d, want 3", got)
	}
	if usedTruth, _ := summary["uses_gazebo_truth_input"].(bool); usedTruth {
		t.Fatalf("scan reference estimator must not use Gazebo truth: %#v", summary)
	}
	if usedMap, _ := summary["uses_known_map_input"].(bool); usedMap {
		t.Fatalf("scan reference estimator must not use a known map: %#v", summary)
	}
	if got := metricFloat(summary, "final_x_m"); math.Abs(got-0.3) > 0.02 {
		t.Fatalf("final_x_m = %v, want about 0.3", got)
	}
	if got := metricFloat(summary, "final_y_m"); math.Abs(got+0.2) > 0.02 {
		t.Fatalf("final_y_m = %v, want about -0.2", got)
	}
	if got := metricFloat(summary, "max_horizontal_drift_m"); math.Abs(got-math.Hypot(0.3, -0.2)) > 0.03 {
		t.Fatalf("max_horizontal_drift_m = %v, want about %v", got, math.Hypot(0.3, -0.2))
	}
}

func TestSummarizeScanReferenceStatusHoverWindowChecksIntentConsistency(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_intent_rosbag_0.mcap")
	writeIntentConsistencyMCAP(t, path, false)

	summary, err := summarizeScanReferenceStatusHoverWindow(path)
	if err != nil {
		t.Fatal(err)
	}
	consistency := mapFromAny(summary["hover_window_correction_intent_consistency"])
	if ok, _ := consistency["ok"].(bool); !ok {
		t.Fatalf("intent consistency = %#v, want ok", consistency)
	}
	if usedTruth, _ := consistency["uses_gazebo_truth_input"].(bool); usedTruth {
		t.Fatalf("Gazebo must remain review-only, not runtime input: %#v", consistency)
	}
	if got := metricInt(summary, "hover_window_correction_intent_active_count"); got != 7 {
		t.Fatalf("active count = %d, want 7", got)
	}
	if got := metricFloat(consistency, "counter_drift_opposes_ratio"); math.Abs(got-1.0) > 1e-9 {
		t.Fatalf("counter_drift_opposes_ratio = %v, want 1", got)
	}
	if got := metricInt(consistency, "intent_x_sign_flips"); got != 0 {
		t.Fatalf("intent_x_sign_flips = %d, want 0", got)
	}
}

func TestSummarizeScanReferenceStatusHoverWindowBlocksWrongIntentDirection(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_bad_intent_rosbag_0.mcap")
	writeIntentConsistencyMCAP(t, path, true)

	summary, err := summarizeScanReferenceStatusHoverWindow(path)
	if err != nil {
		t.Fatal(err)
	}
	consistency := mapFromAny(summary["hover_window_correction_intent_consistency"])
	if ok, _ := consistency["ok"].(bool); ok {
		t.Fatalf("intent consistency = %#v, want blocked", consistency)
	}
	blockers := testStringSliceFromAny(consistency["blockers"])
	if !stringSliceContains(blockers, "intent_consistency_counter_drift_direction_low") {
		t.Fatalf("blockers = %#v, want direction blocker", blockers)
	}
}

func TestSummarizeScanReferenceCorrectionStatusHoverWindowIncludesAxisGateEvidence(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_correction_status_rosbag_0.mcap")
	writeCorrectionStatusMCAP(t, path)

	summary, err := summarizeScanReferenceCorrectionStatusHoverWindow(path)
	if err != nil {
		t.Fatal(err)
	}
	if got := metricInt(summary, "correction_status_sample_count"); got != 2 {
		t.Fatalf("correction_status_sample_count = %d, want 2; summary=%#v", got, summary)
	}
	if got := metricInt(summary, "raw_correction_status_sample_count"); got != 3 {
		t.Fatalf("raw_correction_status_sample_count = %d, want 3", got)
	}
	if got := metricInt(summary, "hover_window_correction_applied_count"); got != 0 {
		t.Fatalf("hover_window_correction_applied_count = %d, want 0", got)
	}
	if ok, _ := summary["phase4b_consistency_ok"].(bool); ok {
		t.Fatalf("phase4b_consistency_ok = true, want false; summary=%#v", summary)
	}
	blockedAxes := testStringSliceFromAny(summary["blocked_axes"])
	if !stringSliceContains(blockedAxes, "y") {
		t.Fatalf("blocked_axes = %#v, want y", blockedAxes)
	}
	axisBlockers := mapFromAny(summary["axis_blockers"])
	yBlockers := testStringSliceFromAny(axisBlockers["y"])
	if !stringSliceContains(yBlockers, "scan_reference_runtime_y_sign_flips") {
		t.Fatalf("axis_blockers = %#v, want y sign flip blocker", axisBlockers)
	}
}

func TestSummarizeIntentConsistencyFlagsSignFlipsAndSaturation(t *testing.T) {
	samples := []scanReferenceStatusSample{}
	gazebo := []timedGazeboOdomSample{}
	for idx := 0; idx < 8; idx++ {
		timestamp := float64(idx)
		gazebo = append(gazebo, timedGazeboOdomSample{
			gazeboOdomSample: gazeboOdomSample{X: 0.1 * float64(idx), Y: 0},
			LogTimeSec:       timestamp,
		})
		intentX := -0.25
		if idx%2 == 1 {
			intentX = 0.25
		}
		samples = append(samples, scanReferenceStatusSample{
			LogTimeSec:          timestamp,
			IntentActive:        true,
			IntentX:             intentX,
			IntentY:             0,
			IntentMagnitude:     0.25,
			IntentMaxCorrection: 0.25,
		})
	}

	consistency := summarizeIntentConsistency(samples, gazebo, 0, 7)

	if ok, _ := consistency["ok"].(bool); ok {
		t.Fatalf("intent consistency = %#v, want blocked", consistency)
	}
	blockers := testStringSliceFromAny(consistency["blockers"])
	for _, want := range []string{
		"intent_consistency_x_sign_flips",
		"intent_consistency_saturation_ratio_high",
		"intent_consistency_intent_direction_unstable",
	} {
		if !stringSliceContains(blockers, want) {
			t.Fatalf("blockers = %#v, want %s", blockers, want)
		}
	}
}

func testStringSliceFromAny(raw any) []string {
	switch typed := raw.(type) {
	case []string:
		return typed
	case []any:
		out := make([]string, 0, len(typed))
		for _, value := range typed {
			if text, ok := value.(string); ok {
				out = append(out, text)
			}
		}
		return out
	default:
		return nil
	}
}

func writeGazeboHoverWindowMCAP(t *testing.T, path string) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	odomSchema := &mcap.Schema{ID: 1, Name: "nav_msgs/msg/Odometry", Encoding: "ros2msg", Data: []byte("std_msgs/Header header\nstring child_frame_id\n")}
	stringSchema := &mcap.Schema{ID: 2, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}
	for _, schema := range []*mcap.Schema{odomSchema, stringSchema} {
		if err := writer.WriteSchema(schema); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 1, SchemaID: 1, Topic: "/gazebo/model/odometry", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 2, SchemaID: 2, Topic: "/navlab/hover/status", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	writeMsg := func(channel uint16, sec uint64, data []byte) {
		t.Helper()
		stamp := sec * 1_000_000_000
		if err := writer.WriteMessage(&mcap.Message{ChannelID: channel, LogTime: stamp, PublishTime: stamp, Data: data}); err != nil {
			t.Fatal(err)
		}
	}
	writeMsg(1, 1, gateTestOdometryCDR(0, 0, 0))
	writeMsg(1, 2, gateTestOdometryCDR(5, 0, 0))
	writeMsg(2, 10, gateTestStringCDR(`{"phase":"hover_hold"}`))
	writeMsg(1, 10, gateTestOdometryCDR(0, 0, 0))
	writeMsg(1, 11, gateTestOdometryCDR(0.1, 0, 0))
	writeMsg(1, 12, gateTestOdometryCDR(0.2, 0, 0))
	writeMsg(2, 12, gateTestStringCDR(`{"phase":"hover_hold"}`))
	writeMsg(1, 20, gateTestOdometryCDR(7, 0, 0))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeHoverXYAlignmentMCAP(t *testing.T, path string, mismatch bool) {
	t.Helper()
	mode := "aligned"
	if mismatch {
		mode = "estimate_mismatch"
	}
	writeHoverXYAlignmentMCAPWithMode(t, path, mode)
}

func writeHoverXYAlignmentMCAPWithMode(t *testing.T, path string, mode string) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	odomSchema := &mcap.Schema{ID: 1, Name: "nav_msgs/msg/Odometry", Encoding: "ros2msg", Data: []byte("std_msgs/Header header\nstring child_frame_id\n")}
	stringSchema := &mcap.Schema{ID: 2, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}
	poseSchema := &mcap.Schema{ID: 3, Name: "geometry_msgs/msg/PoseStamped", Encoding: "ros2msg", Data: []byte("std_msgs/Header header\ngeometry_msgs/Pose pose\n")}
	for _, schema := range []*mcap.Schema{odomSchema, stringSchema, poseSchema} {
		if err := writer.WriteSchema(schema); err != nil {
			t.Fatal(err)
		}
	}
	channels := []*mcap.Channel{
		{ID: 1, SchemaID: 1, Topic: "/gazebo/model/odometry", MessageEncoding: "cdr"},
		{ID: 2, SchemaID: 2, Topic: "/navlab/hover/status", MessageEncoding: "cdr"},
		{ID: 3, SchemaID: 3, Topic: "/navlab/fcu/local_position_pose", MessageEncoding: "cdr"},
		{ID: 4, SchemaID: 1, Topic: "/external_nav/odom", MessageEncoding: "cdr"},
		{ID: 5, SchemaID: 1, Topic: "/slam/odom_corrected", MessageEncoding: "cdr"},
		{ID: 6, SchemaID: 1, Topic: "/external_nav/odom_candidate", MessageEncoding: "cdr"},
	}
	for _, channel := range channels {
		if err := writer.WriteChannel(channel); err != nil {
			t.Fatal(err)
		}
	}
	writeMsg := func(channel uint16, sec uint64, data []byte) {
		t.Helper()
		stamp := sec * 1_000_000_000
		if err := writer.WriteMessage(&mcap.Message{ChannelID: channel, LogTime: stamp, PublishTime: stamp, Data: data}); err != nil {
			t.Fatal(err)
		}
	}
	writeMsg(2, 10, gateTestStringCDR(`{"phase":"hover_hold"}`))
	for idx := 10; idx <= 12; idx++ {
		dx := 0.1 * float64(idx-10)
		dy := 0.05 * float64(idx-10)
		gazeboX := dx
		gazeboY := dy
		externalX := dx
		externalY := dy
		switch mode {
		case "estimate_mismatch":
			externalX = -dx
			externalY = -dy
		case "gazebo_only_mismatch":
			gazeboX = -dx
			gazeboY = -dy
		}
		writeMsg(1, uint64(idx), gateTestOdometryCDR(gazeboX, gazeboY, 0))
		writeMsg(3, uint64(idx), gateTestPoseStampedCDR(dy*0.98, -dx*0.98, 0))
		writeMsg(4, uint64(idx), gateTestOdometryCDR(externalX, externalY, 0))
		writeMsg(5, uint64(idx), gateTestOdometryCDR(dx*1.02, dy*1.02, 0))
		writeMsg(6, uint64(idx), gateTestOdometryCDR(externalX, externalY, 0))
	}
	writeMsg(2, 12, gateTestStringCDR(`{"phase":"hover_hold"}`))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeIntentConsistencyMCAP(t *testing.T, path string, wrongDirection bool) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	odomSchema := &mcap.Schema{ID: 1, Name: "nav_msgs/msg/Odometry", Encoding: "ros2msg", Data: []byte("std_msgs/Header header\nstring child_frame_id\n")}
	stringSchema := &mcap.Schema{ID: 2, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}
	for _, schema := range []*mcap.Schema{odomSchema, stringSchema} {
		if err := writer.WriteSchema(schema); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 1, SchemaID: 1, Topic: "/gazebo/model/odometry", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 2, SchemaID: 2, Topic: "/navlab/hover/status", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 3, SchemaID: 2, Topic: "/navlab/scan_reference_drift/status", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	writeMsg := func(channel uint16, sec uint64, data []byte) {
		t.Helper()
		stamp := sec * 1_000_000_000
		if err := writer.WriteMessage(&mcap.Message{ChannelID: channel, LogTime: stamp, PublishTime: stamp, Data: data}); err != nil {
			t.Fatal(err)
		}
	}
	writeMsg(2, 10, gateTestStringCDR(`{"phase":"hover_hold"}`))
	for idx := 10; idx <= 16; idx++ {
		driftX := 0.1 * float64(idx-10)
		writeMsg(1, uint64(idx), gateTestOdometryCDR(driftX, 0, 0))
		intentX := -0.2
		if wrongDirection {
			intentX = 0.2
		}
		writeMsg(3, uint64(idx), gateTestStringCDR(intentStatusPayload(intentX, 0.0, true)))
	}
	writeMsg(2, 16, gateTestStringCDR(`{"phase":"hover_hold"}`))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeCorrectionStatusMCAP(t *testing.T, path string) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	stringSchema := &mcap.Schema{ID: 1, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}
	if err := writer.WriteSchema(stringSchema); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 1, SchemaID: 1, Topic: "/navlab/hover/status", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 2, SchemaID: 1, Topic: "/navlab/scan_reference_correction/status", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	writeMsg := func(channel uint16, sec uint64, data []byte) {
		t.Helper()
		stamp := sec * 1_000_000_000
		if err := writer.WriteMessage(&mcap.Message{ChannelID: channel, LogTime: stamp, PublishTime: stamp, Data: data}); err != nil {
			t.Fatal(err)
		}
	}
	writeMsg(2, 8, gateTestStringCDR(correctionStatusPayload(true)))
	writeMsg(1, 10, gateTestStringCDR(`{"phase":"hover_hold"}`))
	writeMsg(2, 10, gateTestStringCDR(correctionStatusPayload(false)))
	writeMsg(2, 11, gateTestStringCDR(correctionStatusPayload(false)))
	writeMsg(1, 12, gateTestStringCDR(`{"phase":"hover_hold"}`))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeLatestStatusMCAP(t *testing.T, path string, topic string, payloads []string) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	stringSchema := &mcap.Schema{ID: 1, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}
	if err := writer.WriteSchema(stringSchema); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 1, SchemaID: 1, Topic: topic, MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	for idx, payload := range payloads {
		stamp := uint64(idx+1) * 1_000_000_000
		if err := writer.WriteMessage(&mcap.Message{ChannelID: 1, LogTime: stamp, PublishTime: stamp, Data: gateTestStringCDR(payload)}); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func correctionStatusPayload(applied bool) string {
	payload := map[string]any{
		"ready":                            true,
		"state":                            "passthrough",
		"correction_enabled":               true,
		"correction_applied":               applied,
		"fail_closed":                      true,
		"blockers":                         []string{"scan_reference_runtime_phase4b_consistency_missing"},
		"hover_phase":                      "hover_hold",
		"input_odom_topic":                 "/slam/odom",
		"scan_reference_status_topic":      "/navlab/scan_reference_drift/status",
		"output_odom_topic":                "/slam/odom_corrected",
		"published_count":                  12,
		"corrected_count":                  0,
		"passthrough_count":                12,
		"runtime_consistency_ok":           true,
		"phase4b_consistency_ok":           false,
		"phase4b_consistency_source":       "missing_runtime_phase4b_consistency",
		"measurement_delta_x_m":            0.0,
		"measurement_delta_y_m":            0.0,
		"source_intent_x_m":                -0.18,
		"source_intent_y_m":                0.0,
		"axes":                             []string{"x"},
		"allowed_axes":                     []string{"x"},
		"blocked_axes":                     []string{"y"},
		"axis_blockers":                    map[string]any{"y": []string{"scan_reference_runtime_y_sign_flips"}},
		"uses_gazebo_truth_input":          false,
		"uses_known_map_input":             false,
		"writes_external_nav_odom":         false,
		"external_nav_input_topic":         "/slam/odom_corrected",
		"max_correction_m":                 0.25,
		"max_correction_step_m":            0.03,
		"runtime_consistency_sample_count": 5,
	}
	data, _ := json.Marshal(payload)
	return string(data)
}

func intentStatusPayload(x float64, y float64, active bool) string {
	payload := map[string]any{
		"quality_good":       true,
		"residual_rms_m":     0.05,
		"raw_residual_rms_m": 0.1,
		"inlier_ratio":       0.9,
		"blockers":           []string{},
		"correction_eligibility": map[string]any{
			"correction_allowed": true,
			"allowed_axes":       []string{"x"},
		},
		"correction_intent": map[string]any{
			"active":                 active,
			"axes":                   []string{"x"},
			"correction_x_m":         x,
			"correction_y_m":         y,
			"correction_magnitude_m": math.Hypot(x, y),
			"max_correction_m":       0.25,
			"blockers":               []string{},
		},
	}
	data, _ := json.Marshal(payload)
	return string(data)
}

func writeScanReferenceHoverWindowMCAP(t *testing.T, path string) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	scanSchema := &mcap.Schema{ID: 1, Name: "sensor_msgs/msg/LaserScan", Encoding: "ros2msg", Data: []byte("std_msgs/Header header\nfloat32[] ranges\n")}
	stringSchema := &mcap.Schema{ID: 2, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}
	for _, schema := range []*mcap.Schema{scanSchema, stringSchema} {
		if err := writer.WriteSchema(schema); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 1, SchemaID: 1, Topic: "/scan", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 2, SchemaID: 2, Topic: "/navlab/hover/status", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	writeMsg := func(channel uint16, sec uint64, data []byte) {
		t.Helper()
		stamp := sec * 1_000_000_000
		if err := writer.WriteMessage(&mcap.Message{ChannelID: channel, LogTime: stamp, PublishTime: stamp, Data: data}); err != nil {
			t.Fatal(err)
		}
	}
	writeMsg(1, 1, gateTestLaserScanCDR(1.5, 0.0, 0.0))
	writeMsg(2, 10, gateTestStringCDR(`{"phase":"hover_hold"}`))
	writeMsg(1, 10, gateTestLaserScanCDR(5.0, 0.0, 0.0))
	writeMsg(1, 11, gateTestLaserScanCDR(5.0, 0.1, -0.1))
	writeMsg(1, 12, gateTestLaserScanCDR(5.0, 0.3, -0.2))
	writeMsg(2, 12, gateTestStringCDR(`{"phase":"hover_hold"}`))
	writeMsg(1, 20, gateTestLaserScanCDR(2.0, 2.0, 0.0))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func gateTestOdometryCDR(x float64, y float64, z float64) []byte {
	builder := gateTestCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(1)
	builder.uint32(2)
	builder.string("odom")
	builder.string("base_link")
	builder.float64(x)
	builder.float64(y)
	builder.float64(z)
	return builder.data
}

func gateTestPoseStampedCDR(x float64, y float64, z float64) []byte {
	builder := gateTestCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(1)
	builder.uint32(2)
	builder.string("odom")
	builder.float64(x)
	builder.float64(y)
	builder.float64(z)
	return builder.data
}

func gateTestLaserScanCDR(referenceRange float64, tx float64, ty float64) []byte {
	builder := gateTestCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(1)
	builder.uint32(2)
	builder.string("base_scan")
	angleMin := 0.0
	angleIncrement := math.Pi / 2.0
	builder.float32(angleMin)
	builder.float32(math.Pi * 1.5)
	builder.float32(angleIncrement)
	builder.float32(0)
	builder.float32(0)
	builder.float32(0.05)
	builder.float32(10.0)
	builder.uint32(4)
	for idx := 0; idx < 4; idx++ {
		theta := angleMin + float64(idx)*angleIncrement
		rangeM := referenceRange - (math.Cos(theta)*tx + math.Sin(theta)*ty)
		builder.float32(rangeM)
	}
	builder.uint32(0)
	return builder.data
}

func gateTestStringCDR(value string) []byte {
	builder := gateTestCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.string(value)
	return builder.data
}

type gateTestCDRBuilder struct{ data []byte }

func (builder *gateTestCDRBuilder) align(size int) {
	if size <= 1 {
		return
	}
	remainder := (len(builder.data) - 4) % size
	if remainder != 0 {
		for i := 0; i < size-remainder; i++ {
			builder.data = append(builder.data, 0)
		}
	}
}

func (builder *gateTestCDRBuilder) uint32(value uint32) {
	builder.align(4)
	builder.data = binary.LittleEndian.AppendUint32(builder.data, value)
}

func (builder *gateTestCDRBuilder) int32(value int32) {
	builder.uint32(uint32(value))
}

func (builder *gateTestCDRBuilder) float64(value float64) {
	builder.align(8)
	builder.data = binary.LittleEndian.AppendUint64(builder.data, math.Float64bits(value))
}

func (builder *gateTestCDRBuilder) float32(value float64) {
	builder.align(4)
	builder.data = binary.LittleEndian.AppendUint32(builder.data, math.Float32bits(float32(value)))
}

func (builder *gateTestCDRBuilder) string(value string) {
	encoded := append([]byte(value), 0)
	builder.uint32(uint32(len(encoded)))
	builder.data = append(builder.data, encoded...)
	builder.align(4)
}

func TestX2ScanSourceBlockersRejectStaticFallback(t *testing.T) {
	blockers := x2ScanSourceBlockers(map[string]any{
		"source":                    "x2_serial_emulator",
		"scan_source":               "static_fallback",
		"latest_scan_ideal_age_sec": nil,
		"packet_count":              float64(10),
		"byte_count":                float64(100),
	})

	if !stringSliceContains(blockers, "x2_scan_source_not_gazebo_ideal") {
		t.Fatalf("blockers = %#v, want x2_scan_source_not_gazebo_ideal", blockers)
	}
}

func TestX2ScanSourceBlockersAcceptFreshGazeboIdeal(t *testing.T) {
	blockers := x2ScanSourceBlockers(map[string]any{
		"source":                    "x2_serial_emulator",
		"scan_source":               "gazebo_ideal",
		"latest_scan_ideal_age_sec": float64(0.05),
		"packet_count":              float64(10),
		"byte_count":                float64(100),
	})

	if len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none", blockers)
	}
}

func TestNavigationConfigBlockersCatchUnsafeRoutesAndMissingContracts(t *testing.T) {
	runtimeConfig := validNavigationRuntimeConfig()
	runtimeConfig.Nav2.GlobalFrame = ""
	runtimeConfig.Nav2.ScanTopic = "/navlab/x2/scan_raw"
	runtimeConfig.Nav2.CmdVelTopic = runtimeConfig.FCUController.CmdVelTopic
	runtimeConfig.Nav2.Costmap.RequiredLayers = []string{"static_layer"}
	runtimeConfig.Nav2.Costmap.UsesGazeboTruth = true
	runtimeConfig.Nav2.Costmap.GlobalCostmapTopic = ""
	runtimeConfig.Nav2.Costmap.MaxCostmapAgeSec = 0
	runtimeConfig.Nav2.Costmap.MaxUnknownRatio = 2
	runtimeConfig.NavigationAdapter.MaxXYSpeedMPS = 0
	runtimeConfig.NavigationAdapter.SetpointIntentTopic = runtimeConfig.FCUController.CmdVelTopic
	runtimeConfig.NavigationMission.MinCoverageGrowth = 2

	blockers := validateNavigationConfig(runtimeConfig)
	for _, expected := range []string{
		"nav2_tf_invalid:frame_missing",
		"navigation_scan_source_not_stabilized",
		"nav2_direct_fcu_cmd_vel_publisher",
		"navigation_adapter_direct_fcu_cmd_vel_publisher",
		"nav2_obstacle_layer_missing",
		"nav2_inflation_layer_missing",
		"navigation_costmap_topic_missing",
		"nav2_costmap_stale_threshold_invalid",
		"navigation_costmap_unknown_ratio_invalid",
		"navigation_uses_gazebo_truth_as_input",
		"navigation_adapter_limit_invalid",
		"navigation_coverage_threshold_invalid",
	} {
		if !containsString(blockers, expected) {
			t.Fatalf("expected blocker %q in %#v", expected, blockers)
		}
	}
}

func TestNavigationConfigRejectsCompetingCmdVelPublishers(t *testing.T) {
	runtimeConfig := validNavigationRuntimeConfig()
	runtimeConfig.Nav2.CmdVelTopic = "/ap/v1/cmd_vel"

	blockers := validateNavigationConfig(runtimeConfig)
	if !containsString(blockers, "nav2_direct_fcu_cmd_vel_publisher") {
		t.Fatalf("nav2 blockers = %#v", blockers)
	}

	runtimeConfig = validNavigationRuntimeConfig()
	runtimeConfig.NavigationAdapter.SetpointIntentTopic = "/ap/v1/cmd_vel"
	blockers = validateNavigationConfig(runtimeConfig)
	if !containsString(blockers, "navigation_adapter_direct_fcu_cmd_vel_publisher") {
		t.Fatalf("adapter blockers = %#v", blockers)
	}
}

func TestEvaluateResultGatesAddsNavigationCompletionPolicyBlockers(t *testing.T) {
	runtimeConfig := validNavigationRuntimeConfig()
	runtimeConfig.NavigationMission.CompletionPolicy = "hover_forever"

	evaluation := EvaluateResultGates(
		config.ProjectConfig{},
		runtimeConfig,
		Plan{TaskID: "navigation"},
		t.TempDir(),
		RuntimeSpecBundle{},
		RuntimeExecutionResult{},
		nil,
	)
	if !containsString(evaluation.Blockers, "navigation_completion_policy_invalid") {
		t.Fatalf("blockers = %#v", evaluation.Blockers)
	}
}

func TestEvaluateResultGatesAddsNavigationProbeBlockers(t *testing.T) {
	artifactDir := t.TempDir()
	if err := os.WriteFile(filepath.Join(artifactDir, "nav2_lifecycle_probe.json"), []byte(`{"ok":false,"status":"sampled","nav2_claim":"evaluated","nav2_lifecycle_active":false,"nav2_action_server_ready":false,"blockers":["nav2_lifecycle_inactive","nav2_action_unavailable"],"samples":{}}`), 0o644); err != nil {
		t.Fatal(err)
	}
	evaluation := EvaluateResultGates(
		config.ProjectConfig{},
		validNavigationRuntimeConfig(),
		Plan{
			TaskID: "navigation",
			Execution: helpers.ExecutionPlan{
				ROSProbes: []helpers.ROSProbePlan{{Name: "nav2_lifecycle_probe", OutputPath: "nav2_lifecycle_probe.json"}},
			},
		},
		artifactDir,
		RuntimeSpecBundle{},
		RuntimeExecutionResult{},
		nil,
	)
	for _, expected := range []string{"probe_output_not_ok:nav2_lifecycle_probe", "nav2_lifecycle_inactive", "nav2_action_unavailable"} {
		if !containsString(evaluation.Blockers, expected) {
			t.Fatalf("expected blocker %q in %#v", expected, evaluation.Blockers)
		}
	}
	if evaluation.Metrics.Nav2["nav2_lifecycle_active"] != false || evaluation.Metrics.Nav2["nav2_action_server_ready"] != false {
		t.Fatalf("nav2 metrics = %#v", evaluation.Metrics.Nav2)
	}
}

func TestMetricSummaryIncludesP12DeepMetrics(t *testing.T) {
	metrics := metricSummaryFromEvidence([]ProbeOutputSummary{
		{
			Name: "p12_probe",
			Payload: map[string]any{
				"samples": map[string]any{
					"/navlab/airframe_disturbance/status": map[string]any{
						"data": `{"claim":"evaluated","profile":"realistic","estimated_attitude_response_lag_ms":12.5,"attitude_overshoot_count":1,"attitude_noise_rms_deg":0.4,"false_drop_ratio":0.02,"compensation_jitter_score":0.1,"scan_integrity":{"scan_contract":"p11_stabilized_scan","false_drop_ratio":0.02}}`,
					},
					"/navlab/scan_integrity/status": map[string]any{
						"data": `{"claim":"evaluated","scan_contract":"p11_stabilized_scan","scan_samples":42,"drop_ratio":0.01,"false_drop_ratio":0.02,"compensated_ratio":0.3,"floor_hit_risk_beam_ratio":0.0,"max_scan_attitude_time_offset_ms":4.0}`,
					},
				},
			},
		},
	}, nil)
	if metrics.AirframeDisturbance["estimated_attitude_response_lag_ms"] == nil ||
		metrics.AirframeDisturbance["attitude_overshoot_count"] == nil ||
		metrics.AirframeDisturbance["attitude_noise_rms_deg"] == nil ||
		metrics.AirframeDisturbance["false_drop_ratio"] == nil ||
		metrics.AirframeDisturbance["compensation_jitter_score"] == nil ||
		metrics.AirframeDisturbance["scan_integrity"] == nil {
		t.Fatalf("airframe metrics = %#v", metrics.AirframeDisturbance)
	}
	if metrics.ScanIntegrity["scan_contract"] != "p11_stabilized_scan" || metrics.ScanIntegrity["false_drop_ratio"] == nil {
		t.Fatalf("scan integrity metrics = %#v", metrics.ScanIntegrity)
	}
}

func TestMetricSummaryIncludesP13NavigationMetrics(t *testing.T) {
	metrics := metricSummaryFromEvidence([]ProbeOutputSummary{
		{
			Name: "nav2_lifecycle_probe",
			Payload: map[string]any{
				"nav2_claim":               "evaluated",
				"nav2_lifecycle_active":    true,
				"nav2_action_server_ready": true,
				"tf":                       map[string]any{"map_to_odom": map[string]any{"valid": true}},
			},
		},
		{
			Name: "navigation_probe",
			Payload: map[string]any{
				"samples": map[string]any{
					"/navlab/navigation/status": map[string]any{
						"data": `{"claim":"evaluated","navigation_claim":"evaluated","frontier_claim":"evaluated","strategy":"bounded_frontier","frontier_candidates":[{"id":"p13_probe_1","source":"bounded_goal_slam_map_costmap"}],"accepted_frontiers":[{"id":"p13_probe_1"}],"rejected_frontiers":[{"id":"unreachable_probe","reason":"unreachable_blacklisted"}],"blacklisted_goals":["unreachable_probe"],"accepted_goals":3,"min_accepted_goals":3,"path_length_m":4.2,"min_path_length_m":4.0,"recovery_count":1,"return_home_policy":"return_home_then_land","goal_success_ratio":0.75,"coverage_growth":0.5,"min_coverage_growth":0.5,"uses_gazebo_truth_as_input":false}`,
					},
					"/navlab/navigation/adapter/status": map[string]any{
						"data": `{"claim":"evaluated","adapter_claim":"evaluated","active":true,"max_xy_speed_mps":0.25,"fixed_altitude_m":0.8,"stop_on_stale_costmap":true,"stop_on_stale_slam":true,"clamp_count":2,"hold_count":1,"intent_count":5,"hold_reason":""}`,
					},
					"/navlab/navigation/costmap_health": map[string]any{
						"data": `{"claim":"evaluated","costmap_claim":"evaluated","global_costmap_age_sec":0.2,"local_costmap_age_sec":0.1,"local_costmap_update_frequency_hz":5.0,"unknown_ratio":0.12,"obstacle_cells":8,"required_layers":["static_layer","obstacle_layer","inflation_layer"]}`,
					},
				},
			},
		},
	}, nil)
	if metrics.Navigation["accepted_goals"] == nil || metrics.Navigation["return_home_policy"] != "return_home_then_land" {
		t.Fatalf("navigation metrics = %#v", metrics.Navigation)
	}
	if metrics.Navigation["navigation_claim"] != "evaluated" {
		t.Fatalf("navigation claim metrics = %#v", metrics.Navigation)
	}
	if metrics.Navigation["frontier_claim"] != "evaluated" ||
		metrics.Navigation["frontier_candidates"] == nil ||
		metrics.Navigation["accepted_frontiers"] == nil ||
		metrics.Navigation["rejected_frontiers"] == nil ||
		metrics.Navigation["blacklisted_goals"] == nil ||
		metrics.Navigation["coverage_growth"] == nil ||
		metrics.Navigation["min_coverage_growth"] == nil {
		t.Fatalf("navigation frontier metrics = %#v", metrics.Navigation)
	}
	if metrics.Nav2["nav2_lifecycle_active"] != true || metrics.Nav2["nav2_action_server_ready"] != true {
		t.Fatalf("nav2 metrics = %#v", metrics.Nav2)
	}
	if metrics.NavigationAdapter["max_xy_speed_mps"] == nil || metrics.NavigationAdapter["clamp_count"] == nil {
		t.Fatalf("adapter metrics = %#v", metrics.NavigationAdapter)
	}
	if metrics.CostmapHealth["unknown_ratio"] == nil || metrics.CostmapHealth["required_layers"] == nil || metrics.CostmapHealth["local_costmap_update_frequency_hz"] == nil {
		t.Fatalf("costmap metrics = %#v", metrics.CostmapHealth)
	}
	if metrics.NavigationAdapter["adapter_claim"] != "evaluated" || metrics.CostmapHealth["costmap_claim"] != "evaluated" {
		t.Fatalf("claim metrics adapter=%#v costmap=%#v", metrics.NavigationAdapter, metrics.CostmapHealth)
	}
}

func TestMetricSummaryIncludesSLAMStabilityMetrics(t *testing.T) {
	artifactDir := t.TempDir()
	log := strings.Join([]string{
		"W0615 Dropped earlier points from trajectory",
		"W0615 rejected odom TF stamp=1.000000000 x=99.000 y=0.000 z=0.000 rejected=1",
		"terminate called after throwing an instance of 'std::length_error'",
	}, "\n")
	if err := artifactlayout.Ensure(artifactDir); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(artifactlayout.RuntimeLog(artifactDir, "slam_backend.runtime.log"), []byte(log), 0o644); err != nil {
		t.Fatal(err)
	}
	metrics := metricSummaryFromEvidence([]ProbeOutputSummary{
		{
			Name: "frame_contract_probe",
			Payload: map[string]any{
				"samples": map[string]any{
					"/navlab/slam/status": map[string]any{
						"data": `{"state":"publishing_cached_slam_tf_odom","ready":true,"mode":"slam_tf","tf":{"count":12,"received_count":15,"rejected_count":3,"rejection_ratio":0.2,"max_observed_jump_m":2.5,"max_accepted_jump_m":0.4,"max_rejected_jump_m":2.5,"max_allowed_jump_m":2.0},"output":{"odom_topic":"/slam/odom","odom_count":12}}`,
					},
				},
			},
		},
	}, nil, artifactDir)
	tf, ok := metrics.SLAM["tf"].(map[string]any)
	if !ok || tf["rejected_count"] != float64(3) || tf["max_rejected_jump_m"] != 2.5 {
		t.Fatalf("slam tf metrics = %#v", metrics.SLAM)
	}
	if metrics.SLAMRuntimeLog["dropped_earlier_points_count"] != 1 ||
		metrics.SLAMRuntimeLog["rejected_odom_tf_log_count"] != 1 ||
		metrics.SLAMRuntimeLog["std_length_error_count"] != 1 ||
		metrics.SLAMRuntimeLog["warning_count"] != 2 ||
		metrics.SLAMRuntimeLog["quality"] != "unhealthy" ||
		metrics.SLAMRuntimeLog["ok"] != false {
		t.Fatalf("slam runtime log metrics = %#v", metrics.SLAMRuntimeLog)
	}
	if metrics.MetricEvidenceSources["slam_runtime_log"] != artifactlayout.RuntimeLogRel("slam_backend.runtime.log") {
		t.Fatalf("metric evidence sources = %#v", metrics.MetricEvidenceSources)
	}
}

func TestMetricSummaryClassifiesPreflightReadinessAndRangefinderEvidence(t *testing.T) {
	artifactDir := t.TempDir()
	missionSummary := map[string]any{
		"ok":                    false,
		"reason":                "preflight_timeout",
		"mission_phase_state":   "S1 wait_nav_ready",
		"mission_phase_blocker": "waiting_for_external_nav_and_imu",
		"phases_seen":           []any{"wait_nav_ready"},
		"airborne_seen":         false,
	}
	data, err := json.Marshal(missionSummary)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(artifactDir, "mission_summary.json"), data, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := artifactlayout.Ensure(artifactDir); err != nil {
		t.Fatal(err)
	}
	serialLog := `2026-06-25 INFO benewake_tfmini_serial: Benewake TFmini status {"byte_count":0,"frame_count":0,"latest_distance_m":null,"latest_input_age_sec":null,"state":"open","virtual_serial_link":"/tmp/navlab_benewake_tfmini"}`
	if err := os.WriteFile(artifactlayout.RuntimeLog(artifactDir, "benewake_tfmini_serial.runtime.log"), []byte(serialLog), 0o644); err != nil {
		t.Fatal(err)
	}
	probes := []ProbeOutputSummary{
		{
			Name:   "rangefinder_probe",
			Exists: true,
			OK:     false,
			Payload: map[string]any{"samples": map[string]any{
				"/rangefinder/down/range": map[string]any{
					"ok":            false,
					"return_code":   float64(124),
					"sample_method": "rclpy_subscription",
					"failure_kind":  "topic_sample_missing",
				},
				"/rangefinder/down/status": map[string]any{
					"ok": true,
					"parsed": map[string]any{
						"ready":                false,
						"state":                "waiting",
						"input_count":          float64(0),
						"latest_distance_m":    nil,
						"latest_input_age_sec": nil,
						"virtual_serial_link":  "/tmp/navlab_benewake_tfmini",
						"range_topic":          "/rangefinder/down/range",
						"scan_ideal_topic":     "/rangefinder/down/scan_ideal",
					},
				},
			}},
		},
		{
			Name:   "slam_hover_probe",
			Exists: true,
			OK:     true,
			Payload: map[string]any{"samples": map[string]any{
				"/external_nav/status": map[string]any{
					"ok": true,
					"parsed": map[string]any{
						"state": "waiting_for_height",
						"ready": false,
						"height": map[string]any{
							"ready": false,
						},
					},
				},
			}},
		},
	}
	rosbags := []RosbagGateSummary{{
		Name: "hover_rosbag",
		MessageCounts: map[string]int{
			"/rangefinder/down/range":         0,
			"/rangefinder/down/status":        5,
			"/height/estimate":                0,
			"/height/status":                  5,
			"/external_nav/odom":              0,
			"/navlab/fcu/local_position_pose": 0,
		},
	}}

	metrics := metricSummaryFromEvidence(probes, rosbags, artifactDir)
	readiness := metrics.StartupReadiness
	if readiness["classification"] != "startup_readiness_failure" ||
		readiness["preflight_invalid"] != true ||
		readiness["valid_hover_body_sample"] != false ||
		readiness["not_hover_span_slo"] != true {
		t.Fatalf("startup readiness classification = %#v", readiness)
	}
	for _, reason := range []string{
		"wait_nav_ready",
		"external_nav_waiting",
		"airborne_not_seen",
		"hover_hold_not_seen",
		"rangefinder_not_ready",
		"rangefinder_input_missing",
		"rangefinder_range_sample_missing",
		"external_nav_waiting_for_height",
		"height_estimate_missing",
	} {
		if !stringSliceContains(stringsFromAny(readiness["reason_codes"]), reason) {
			t.Fatalf("startup readiness missing reason %q: %#v", reason, readiness)
		}
	}
	rangefinder := mapFromAny(readiness["rangefinder"])
	if rangefinder["virtual_serial_link"] != "/tmp/navlab_benewake_tfmini" ||
		metricInt(rangefinder, "input_count") != 0 ||
		metricInt(rangefinder, "serial_byte_count") != 0 ||
		metricInt(rangefinder, "serial_frame_count") != 0 ||
		rangefinder["range_sample_failure_kind"] != "topic_sample_missing" {
		t.Fatalf("rangefinder readiness evidence = %#v", rangefinder)
	}
	height := mapFromAny(readiness["height"])
	if height["external_nav_height_ready"] != false || metricInt(height, "rosbag_height_estimate_count") != 0 {
		t.Fatalf("height readiness evidence = %#v", height)
	}
}

func TestStartupProbeSemanticsPreserveTFStaticStdoutTimeoutEvidence(t *testing.T) {
	probe := ProbeOutputSummary{
		Name:   "frame_contract_probe",
		Exists: true,
		OK:     true,
		Payload: map[string]any{"samples": map[string]any{
			"/tf_static": map[string]any{
				"ok":            true,
				"return_code":   float64(124),
				"sample_method": "ros2_topic_echo",
				"failure_kind":  "sample_stdout_present_timeout",
				"stdout":        "transforms: []",
			},
		}},
	}

	if blockers := probeBlockers(probe); len(blockers) != 0 {
		t.Fatalf("probe blockers = %#v, want none for stdout-backed tf_static evidence", blockers)
	}
	semantics := startupProbeSemantics([]ProbeOutputSummary{probe})
	samples := mapFromAny(semantics["samples"])
	tfStatic := mapFromAny(samples["frame_contract_probe:/tf_static"])
	if tfStatic["ok"] != true ||
		tfStatic["failure_kind"] != "sample_stdout_present_timeout" ||
		tfStatic["has_stdout"] != true {
		t.Fatalf("tf_static probe semantics = %#v", tfStatic)
	}
}

func TestSLAMRuntimeLogBlockersFailClosed(t *testing.T) {
	blockers := slamRuntimeLogBlockers(map[string]any{
		"ok":                     false,
		"std_length_error_count": 1,
		"fatal_count":            0,
		"error_count":            1,
	})

	for _, want := range []string{
		"slam_runtime_unhealthy",
		"slam_runtime_std_length_error",
		"slam_runtime_error",
	} {
		if !stringSliceContains(blockers, want) {
			t.Fatalf("blockers = %#v, want %s", blockers, want)
		}
	}
}

func TestSLAMRuntimeLogDetectsCartographerWaitingForIMUQueue(t *testing.T) {
	artifactDir := t.TempDir()
	lines := make([]string, 0, 24)
	for idx := 0; idx < 24; idx++ {
		lines = append(lines, "W0622 00:00:00.000000 Queue waiting for data: (0, imu)")
	}
	if err := os.WriteFile(filepath.Join(artifactDir, "slam_backend.runtime.log"), []byte(strings.Join(lines, "\n")), 0o644); err != nil {
		t.Fatal(err)
	}

	metrics := parseSLAMRuntimeLog(filepath.Join(artifactDir, "slam_backend.runtime.log"))
	if got := metricInt(metrics, "cartographer_waiting_for_imu_queue_count"); got != 24 {
		t.Fatalf("waiting_for_imu count = %d, want 24: %#v", got, metrics)
	}
	if ok, _ := metrics["ok"].(bool); ok {
		t.Fatalf("metrics = %#v, want fail-closed when Cartographer is stuck waiting for IMU", metrics)
	}
	blockers := slamRuntimeLogBlockers(metrics)
	if !stringSliceContains(blockers, "slam_cartographer_waiting_for_imu_queue") {
		t.Fatalf("blockers = %#v, want slam_cartographer_waiting_for_imu_queue", blockers)
	}
}

func TestSLAMPreflightBlockersDetectMissingOdomAndTFNotReady(t *testing.T) {
	blockers := slamPreflightBlockers(map[string]any{
		"state":        "waiting_for_cartographer_tf",
		"ready":        false,
		"odom_samples": float64(0),
		"output": map[string]any{
			"odom_topic": "/slam/odom",
			"odom_count": float64(0),
		},
	}, map[string]any{
		"cartographer_waiting_for_imu_queue_count":     21,
		"cartographer_waiting_for_imu_queue_threshold": 20,
	})

	for _, want := range []string{
		"slam_cartographer_tf_not_ready",
		"slam_odom_preflight_missing",
		"slam_cartographer_waiting_for_imu_queue",
	} {
		if !stringSliceContains(blockers, want) {
			t.Fatalf("blockers = %#v, want %s", blockers, want)
		}
	}

	if got := slamPreflightBlockers(map[string]any{
		"state":        "publishing_cached_slam_tf_odom",
		"ready":        true,
		"odom_samples": float64(5),
		"output": map[string]any{
			"odom_topic": "/slam/odom",
			"odom_count": float64(5),
		},
	}, nil); len(got) != 0 {
		t.Fatalf("blockers = %#v, want none", got)
	}
}

func TestMetricSummaryIncludesFCUSetpointEvidence(t *testing.T) {
	metrics := metricSummaryFromEvidence([]ProbeOutputSummary{
		{
			Name: "fcu_probe",
			Payload: map[string]any{
				"samples": map[string]any{
					"/navlab/fcu/controller/status": map[string]any{
						"data": `{"ready":true,"state":"hover_hold","pose_samples":12,"control_route":"mavlink_bootstrap_plus_dds_cmd_vel","takeoff_alt_m":0.5,"bootstrap_ready":true,"cmd_vel_publish_count":42,"mavlink_setpoint_count":21,"mavlink_setpoint_error":"","mavlink_local_position_count":9,"fcu_mode_window":{"ok":true},"bootstrap":{"takeoff":{"ok":true,"ack_accepted_seen":true,"height":{"height_m":0.32,"target_min_m":0.2}}}}`,
					},
					"/navlab/fcu/setpoint/output": map[string]any{
						"data": `{"ready":true,"state":"hold_position","intent_topic":"/navlab/fcu/setpoint/intent","cmd_vel_topic":"/ap/v1/cmd_vel","setpoint_intent_samples":5,"cmd_vel_publish_count":42,"mavlink_setpoint_count":21,"mavlink_setpoint_error":"","mavlink_local_position_count":9,"path_length_m":1.2,"min_path_length_m":0.35}`,
					},
				},
			},
		},
	}, nil)
	if metrics.Controller["mavlink_setpoint_count"] != float64(21) ||
		metrics.Controller["mavlink_local_position_count"] != float64(9) ||
		metrics.Controller["bootstrap_ready"] != true ||
		metrics.Setpoint["mavlink_setpoint_count"] != float64(21) ||
		metrics.Setpoint["mavlink_local_position_count"] != float64(9) ||
		metrics.Setpoint["setpoint_intent_samples"] != float64(5) ||
		metrics.Controller["bootstrap"] == nil {
		t.Fatalf("fcu setpoint metrics controller=%#v setpoint=%#v", metrics.Controller, metrics.Setpoint)
	}
}

func TestSummarizeLatestJSONStatusFromRosbagFillsSelectorEvidence(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_status_rosbag_0.mcap")
	writeLatestStatusMCAP(t, path, "/external_nav/source_selector/status", []string{
		`{"ready":true,"publish":true,"source":"slam_bootstrap","output_odom_topic":"/external_nav/odom_candidate","uses_gazebo_truth_input":false}`,
		`{"ready":false,"publish":false,"source":"not_ready","blockers":["candidate_step_jump"],"reject_reason":"candidate_step_jump","rejected_step_m":1.7,"cartographer_scan_disagreement":false,"uses_gazebo_truth_input":false,"uses_known_map_input":false,"output_odom_topic":"/external_nav/odom_candidate","output_frame_id":"map","output_child_frame_id":"base_link"}`,
	})

	summary, err := summarizeLatestJSONStatusFromRosbag(path, "/external_nav/source_selector/status", "ready", "publish", "source", "blockers", "reject_reason", "rejected_step_m", "cartographer_scan_disagreement", "uses_gazebo_truth_input", "uses_known_map_input", "output_odom_topic", "output_frame_id", "output_child_frame_id")
	if err != nil {
		t.Fatal(err)
	}
	if summary["source"] != "not_ready" ||
		summary["ready"] != false ||
		summary["publish"] != false ||
		summary["reject_reason"] != "candidate_step_jump" ||
		metricFloat(summary, "rejected_step_m") != 1.7 ||
		summary["output_odom_topic"] != "/external_nav/odom_candidate" ||
		metricInt(summary, "status_sample_count") != 2 {
		t.Fatalf("summary = %#v", summary)
	}
}

func TestSummarizeLatestJSONStatusFromRosbagFillsExternalNavEvidence(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_external_nav_status_rosbag_0.mcap")
	writeLatestStatusMCAP(t, path, "/external_nav/status", []string{
		`{"state":"waiting_for_odom","ready":false}`,
		`{"state":"healthy","ready":true,"odom":{"input_topic":"/external_nav/odom_candidate","rate_hz":200.0,"ready":true},"height":{"ready":true},"output":{"topic":"/external_nav/odom"}}`,
	})

	summary, err := summarizeLatestJSONStatusFromRosbag(path, "/external_nav/status", "state", "ready", "odom", "height", "output")
	if err != nil {
		t.Fatal(err)
	}
	odom := mapFromAny(summary["odom"])
	if summary["state"] != "healthy" ||
		summary["ready"] != true ||
		odom["input_topic"] != "/external_nav/odom_candidate" ||
		metricInt(summary, "status_sample_count") != 2 {
		t.Fatalf("summary = %#v", summary)
	}
}

func TestMetricSummaryIncludesScanReferenceCorrectionAxisGateEvidence(t *testing.T) {
	metrics := metricSummaryFromEvidence([]ProbeOutputSummary{
		{
			Name: "scan_reference_correction_probe",
			Payload: map[string]any{
				"samples": map[string]any{
					"/navlab/scan_reference_correction/status": map[string]any{
						"data": `{"ready":true,"correction_applied":false,"runtime_consistency_ok":true,"phase4b_consistency_ok":false,"phase4b_consistency_source":"missing_runtime_phase4b_consistency","allowed_axes":["x"],"blocked_axes":["y"],"axis_blockers":{"y":["scan_reference_runtime_y_sign_flips"]}}`,
					},
				},
			},
		},
	}, nil)

	if metrics.ScanReferenceCorrection["runtime_consistency_ok"] != true ||
		metrics.ScanReferenceCorrection["phase4b_consistency_ok"] != false ||
		metrics.ScanReferenceCorrection["phase4b_consistency_source"] != "missing_runtime_phase4b_consistency" ||
		metrics.ScanReferenceCorrection["axis_blockers"] == nil {
		t.Fatalf("scan reference correction metrics = %#v", metrics.ScanReferenceCorrection)
	}
}

func TestMetricSummaryIncludesExternalNavSourceSelectorEvidence(t *testing.T) {
	metrics := metricSummaryFromEvidence([]ProbeOutputSummary{
		{
			Name: "external_nav_source_selector_probe",
			Payload: map[string]any{
				"samples": map[string]any{
					"/external_nav/source_selector/status": map[string]any{
						"data": `{"ready":true,"publish":true,"degraded":true,"source":"scan_reference_hold","blockers":["candidate_step_jump"],"reject_reason":"candidate_step_jump","rejected_step_m":1.7,"hold_age_ms":100.0,"hold_reason":"candidate_step_jump_hold","cartographer_scan_disagreement":false,"uses_gazebo_truth_input":false,"uses_known_map_input":false,"output_odom_topic":"/external_nav/odom_candidate","output_frame_id":"map","output_child_frame_id":"base_link"}`,
					},
				},
			},
		},
	}, nil)

	if metrics.ExternalNavSourceSelector["source"] != "scan_reference_hold" ||
		metrics.ExternalNavSourceSelector["publish"] != true ||
		metrics.ExternalNavSourceSelector["degraded"] != true ||
		metrics.ExternalNavSourceSelector["reject_reason"] != "candidate_step_jump" ||
		metrics.ExternalNavSourceSelector["output_odom_topic"] != "/external_nav/odom_candidate" {
		t.Fatalf("external nav source selector metrics = %#v", metrics.ExternalNavSourceSelector)
	}
}

func TestProbeBlockersIgnoresSourceSelectorContextBlockers(t *testing.T) {
	blockers := probeBlockers(ProbeOutputSummary{
		Name: "slam_hover_probe",
		Payload: map[string]any{
			"samples": map[string]any{
				"/external_nav/source_selector/status": map[string]any{
					"parsed": map[string]any{
						"blockers": []any{
							"not_hover_correction_phase",
							"scan_reference_eligibility_not_allowed",
							"scan_reference_xy_axes_not_allowed",
						},
						"hover_phase": "complete",
					},
				},
				"/external_nav/status": map[string]any{
					"parsed": map[string]any{
						"blockers": []any{"external_nav_real_blocker"},
					},
				},
			},
		},
	})

	if stringSliceContains(blockers, "not_hover_correction_phase") ||
		stringSliceContains(blockers, "scan_reference_eligibility_not_allowed") ||
		stringSliceContains(blockers, "scan_reference_xy_axes_not_allowed") {
		t.Fatalf("source selector context blockers leaked into top-level blockers: %#v", blockers)
	}
	if !stringSliceContains(blockers, "external_nav_real_blocker") {
		t.Fatalf("non-selector blocker should still be preserved: %#v", blockers)
	}
}

func TestExternalNavSourceSelectorBlockersRejectTruthInput(t *testing.T) {
	blockers := externalNavSourceSelectorBlockers(map[string]any{
		"uses_gazebo_truth_input": true,
		"uses_known_map_input":    false,
		"output_odom_topic":       "/external_nav/odom_candidate",
		"output_frame_id":         "map",
		"output_child_frame_id":   "base_link",
	})

	if !stringSliceContains(blockers, "external_nav_source_selector_uses_gazebo_truth") {
		t.Fatalf("blockers = %#v, want truth input blocker", blockers)
	}
}

func TestExternalNavSourceSelectorBlockersExposeNotReadyRejectReason(t *testing.T) {
	blockers := externalNavSourceSelectorBlockers(map[string]any{
		"ready":                   false,
		"publish":                 false,
		"source":                  "not_ready",
		"reject_reason":           "candidate_step_jump",
		"uses_gazebo_truth_input": false,
		"uses_known_map_input":    false,
		"output_odom_topic":       "/external_nav/odom_candidate",
		"output_frame_id":         "map",
		"output_child_frame_id":   "base_link",
	})

	for _, want := range []string{
		"external_nav_source_selector_not_ready",
		"external_nav_source_selector_not_publishing",
		"external_nav_source_selector_rejected:candidate_step_jump",
	} {
		if !stringSliceContains(blockers, want) {
			t.Fatalf("blockers = %#v, want %s", blockers, want)
		}
	}
}

func TestExternalNavCandidateIsAllowedExternalNavInput(t *testing.T) {
	if !isAllowedExternalNavSLAMInputTopic("/external_nav/odom_candidate") {
		t.Fatal("/external_nav/odom_candidate should be an allowed hover ExternalNav input")
	}
}

func TestHoverSourceSelectorGateOnlyAppliesToSelectorRoute(t *testing.T) {
	if !hoverUsesExternalNavSourceSelector(config.TaskRuntimeConfig{}) {
		t.Fatal("default hover route should require source selector evidence")
	}
	if !hoverUsesExternalNavSourceSelector(config.TaskRuntimeConfig{
		SlamHover: config.SlamHoverConfig{ExternalNavInputOdomTopic: "/external_nav/odom_candidate"},
	}) {
		t.Fatal("selector candidate route should require source selector evidence")
	}
	if hoverUsesExternalNavSourceSelector(config.TaskRuntimeConfig{
		SlamHover: config.SlamHoverConfig{ExternalNavInputOdomTopic: "/slam/odom"},
	}) {
		t.Fatal("direct /slam/odom route should not require source selector evidence")
	}
}

func TestScanReferenceCorrectionBlockersRejectCorrectionWithoutPhase4B(t *testing.T) {
	blockers := scanReferenceCorrectionBlockers(map[string]any{
		"correction_applied":       true,
		"runtime_consistency_ok":   true,
		"phase4b_consistency_ok":   false,
		"uses_gazebo_truth_input":  false,
		"writes_external_nav_odom": false,
	})

	if !stringSliceContains(blockers, "scan_reference_correction_phase4b_not_ok") {
		t.Fatalf("blockers = %#v, want phase4b blocker", blockers)
	}
}

func TestScanReferenceCorrectionBlockersUseAppliedWindowEvidence(t *testing.T) {
	blockers := scanReferenceCorrectionBlockers(map[string]any{
		"corrected_count":                                        560,
		"phase4b_consistency_ok":                                 false,
		"runtime_consistency_ok":                                 false,
		"hover_window_applied_without_phase4b_count":             0,
		"hover_window_applied_without_runtime_consistency_count": 0,
		"uses_gazebo_truth_input":                                false,
		"writes_external_nav_odom":                               false,
	})

	if stringSliceContains(blockers, "scan_reference_correction_phase4b_not_ok") ||
		stringSliceContains(blockers, "scan_reference_correction_runtime_consistency_not_ok") {
		t.Fatalf("blockers = %#v, want no stale final-status correction blocker", blockers)
	}
}

func TestHoverTakeoffBlockersRequireObservedHeight(t *testing.T) {
	passing := map[string]any{
		"takeoff_alt_m": 0.5,
		"bootstrap": map[string]any{
			"takeoff": map[string]any{
				"ok":                true,
				"ack_accepted_seen": true,
				"height": map[string]any{
					"height_m":     0.42,
					"target_min_m": 0.175,
				},
			},
		},
	}
	if blockers := hoverTakeoffBlockers("hover", passing); len(blockers) != 0 {
		t.Fatalf("blockers = %#v, want none", blockers)
	}

	failing := map[string]any{
		"takeoff_alt_m": 0.5,
		"bootstrap": map[string]any{
			"takeoff": map[string]any{
				"ok":                true,
				"ack_accepted_seen": true,
				"height": map[string]any{
					"height_m":     0.0,
					"target_min_m": 0.175,
				},
			},
		},
	}
	if blockers := hoverTakeoffBlockers("hover", failing); !stringSliceContains(blockers, "hover_takeoff_height_not_observed") {
		t.Fatalf("blockers = %#v, want hover_takeoff_height_not_observed", blockers)
	}

	tooLow := map[string]any{
		"takeoff_alt_m": 0.5,
		"bootstrap": map[string]any{
			"takeoff": map[string]any{
				"ok":                true,
				"ack_accepted_seen": true,
				"height": map[string]any{
					"height_m":     0.19,
					"target_min_m": 0.175,
				},
			},
		},
	}
	if blockers := hoverTakeoffBlockers("hover", tooLow); !stringSliceContains(blockers, "hover_takeoff_target_altitude_not_reached") {
		t.Fatalf("blockers = %#v, want hover_takeoff_target_altitude_not_reached", blockers)
	}
}

func validNavigationRuntimeConfig() config.TaskRuntimeConfig {
	return config.TaskRuntimeConfig{
		Nav2: config.Nav2Config{
			Enabled:          true,
			Profile:          "indoor_2d",
			GlobalFrame:      "map",
			OdomFrame:        "odom",
			BaseFrame:        "base_link",
			ScanTopic:        "/scan",
			MapTopic:         "/map",
			CmdVelTopic:      "/navlab/navigation/cmd_vel",
			BTXML:            "navigate_to_pose_w_replanning_and_recovery.xml",
			PlannerPlugin:    "GridBased",
			ControllerPlugin: "FollowPath",
			UseSimTime:       true,
			Costmap: config.Nav2CostmapConfig{
				GlobalCostmapTopic: "/global_costmap/costmap",
				LocalCostmapTopic:  "/local_costmap/costmap",
				RequiredLayers:     []string{"static_layer", "obstacle_layer", "inflation_layer"},
				MaxCostmapAgeSec:   1.5,
				MinObstacleCells:   1,
				MaxUnknownRatio:    0.35,
				HealthTopic:        "/navlab/navigation/costmap_health",
			},
		},
		NavigationAdapter: config.NavigationAdapterConfig{
			SetpointIntentTopic: "/navlab/fcu/setpoint/intent",
			StatusTopic:         "/navlab/navigation/adapter/status",
			MaxXYSpeedMPS:       0.25,
			MaxYawRateDPS:       35,
			MaxAccelMPS2:        0.35,
			FixedAltitudeM:      0.8,
			StopOnStaleCostmap:  true,
			StopOnStaleSlam:     true,
		},
		NavigationMission: config.NavigationMissionConfig{
			Strategy:            "bounded_frontier",
			GoalFrame:           "map",
			StatusTopic:         "/navlab/navigation/status",
			NavigationWindowSec: 120,
			MinPathLengthM:      4,
			MinCoverageGrowth:   0.5,
			MinAcceptedGoals:    3,
			CompletionPolicy:    helpers.PolicyLandInPlace,
			ReturnHomePolicy:    helpers.PolicyLandInPlace,
			NavigationClaim:     "evaluated",
			ExitGoal:            config.NavigationGoalConfig{ID: "maze_exit", XM: 1.5, YM: -0.5, YawRad: 0},
			BoundedGoals:        []config.NavigationGoalConfig{{ID: "p13_probe_1", XM: 1, YM: 0, YawRad: 0}},
			HomeGoal:            config.NavigationGoalConfig{ID: "home"},
		},
		FCUController: config.FCUControllerConfig{
			CmdVelTopic:           "/ap/v1/cmd_vel",
			ControllerStatusTopic: "/navlab/fcu/controller/status",
			OwnerStatusTopic:      "/navlab/fcu/owner/status",
		},
		ScanStabilization: config.ScanStabilizationConfig{
			OutputScanTopic: "/scan",
		},
		Landing: config.LandingConfig{
			ExplorationPolicy: helpers.PolicyReturnHomeThenLand,
			NavigationPolicy:  helpers.PolicyLandInPlace,
			DefaultPolicy:     helpers.PolicyLandInPlace,
		},
	}
}
