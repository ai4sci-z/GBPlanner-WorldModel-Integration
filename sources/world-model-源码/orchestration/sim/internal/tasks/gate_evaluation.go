package tasks

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/foxglove/mcap/go/mcap"
	"github.com/klauspost/compress/zstd"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

type GateEvaluation struct {
	OK             bool                 `json:"ok"`
	Blocked        bool                 `json:"blocked"`
	Blockers       []string             `json:"blockers"`
	FSMArtifacts   []FSMArtifactRef     `json:"fsm_artifacts,omitempty"`
	ProbeOutputs   []ProbeOutputSummary `json:"probe_outputs"`
	RosbagProfiles []RosbagGateSummary  `json:"rosbag_profiles"`
	Landing        helpers.Acceptance   `json:"landing_acceptance"`
	TaskChecks     map[string]bool      `json:"task_checks"`
	Metrics        MetricSummary        `json:"metrics"`
}

type ProbeOutputSummary struct {
	Name    string         `json:"name"`
	Path    string         `json:"path"`
	Exists  bool           `json:"exists"`
	Empty   bool           `json:"empty,omitempty"`
	OK      bool           `json:"ok"`
	Status  string         `json:"status,omitempty"`
	Payload map[string]any `json:"payload,omitempty"`
}

type RosbagGateSummary struct {
	Name                        string         `json:"name"`
	MetadataPath                string         `json:"metadata_path"`
	MCAPPaths                   []string       `json:"mcap_paths,omitempty"`
	Exists                      bool           `json:"exists"`
	OK                          bool           `json:"ok"`
	RequiredTopics              []string       `json:"required_topics"`
	MessageCounts               map[string]int `json:"message_counts,omitempty"`
	MessageCountsSource         string         `json:"message_counts_source,omitempty"`
	MissingRequiredTopics       []string       `json:"missing_required_topics,omitempty"`
	ZeroCountRequiredTopics     []string       `json:"zero_count_required_topics,omitempty"`
	MetadataMissingOrUnreadable string         `json:"metadata_missing_or_unreadable,omitempty"`
}

type MetricSummary struct {
	Hover                     map[string]any            `json:"hover,omitempty"`
	HoverMission              map[string]any            `json:"hover_mission,omitempty"`
	Controller                map[string]any            `json:"controller,omitempty"`
	Setpoint                  map[string]any            `json:"setpoint,omitempty"`
	Owner                     map[string]any            `json:"owner,omitempty"`
	Exploration               map[string]any            `json:"exploration,omitempty"`
	Nav2                      map[string]any            `json:"nav2,omitempty"`
	Navigation                map[string]any            `json:"navigation,omitempty"`
	NavigationAdapter         map[string]any            `json:"navigation_adapter,omitempty"`
	CostmapHealth             map[string]any            `json:"costmap_health,omitempty"`
	SLAM                      map[string]any            `json:"slam,omitempty"`
	ExternalNav               map[string]any            `json:"external_nav,omitempty"`
	ExternalNavSourceSelector map[string]any            `json:"external_nav_source_selector,omitempty"`
	MAVLinkExternalNav        map[string]any            `json:"mavlink_external_nav,omitempty"`
	RangefinderSerial         map[string]any            `json:"rangefinder_serial,omitempty"`
	X2                        map[string]any            `json:"x2,omitempty"`
	GazeboModelHoverDrift     map[string]any            `json:"gazebo_model_hover_drift,omitempty"`
	ScanReferenceHoverDrift   map[string]any            `json:"scan_reference_hover_drift,omitempty"`
	ScanReferenceRuntimeDrift map[string]any            `json:"scan_reference_runtime_drift,omitempty"`
	ScanReferenceCorrection   map[string]any            `json:"scan_reference_correction,omitempty"`
	HoverXYAlignment          map[string]any            `json:"hover_xy_alignment,omitempty"`
	HoverHealth               map[string]any            `json:"hover_health,omitempty"`
	StartupReadiness          map[string]any            `json:"startup_readiness,omitempty"`
	SLAMRuntimeLog            map[string]any            `json:"slam_runtime_log,omitempty"`
	ScanIntegrity             map[string]any            `json:"scan_integrity,omitempty"`
	ScanStabilization         map[string]any            `json:"scan_stabilization,omitempty"`
	AirframeDisturbance       map[string]any            `json:"airframe_disturbance,omitempty"`
	RosbagMessageCounts       map[string]map[string]int `json:"rosbag_message_counts,omitempty"`
	MetricEvidenceSources     map[string]string         `json:"metric_evidence_sources,omitempty"`
}

func EvaluateResultGates(
	project config.ProjectConfig,
	runtimeConfig config.TaskRuntimeConfig,
	plan Plan,
	artifactDir string,
	runtimeSpecs RuntimeSpecBundle,
	execution RuntimeExecutionResult,
	executionErr error,
) GateEvaluation {
	blockers := []string{}
	taskChecks := taskSpecificChecks(runtimeConfig, plan.TaskID)
	for name, ok := range taskChecks {
		if !ok {
			blockers = append(blockers, "task_check_failed:"+name)
		}
	}
	blockers = append(blockers, taskSpecificBlockers(runtimeConfig, plan.TaskID)...)
	if executionErr != nil {
		blockers = append(blockers, "runtime_execution_failed")
	}
	for _, result := range execution.ProbeResults {
		if !result.OK() && runtimeProbeRequired(runtimeSpecs, result.Name) {
			blockers = append(blockers, fmt.Sprintf("probe_failed:%s:rc=%d", result.Name, result.ReturnCode))
			if result.ReturnCode < 0 {
				blockers = append(blockers, "probe_killed:"+result.Name)
			}
		}
	}

	probeOutputs := evaluateProbeOutputs(plan, artifactDir)
	for _, probe := range probeOutputs {
		probeRequired := runtimeProbeRequired(runtimeSpecs, probe.Name)
		if !probe.OK && probeRequired {
			if !probe.Exists {
				blockers = append(blockers, "probe_output_missing:"+probe.Name)
			} else if probe.Empty {
				blockers = append(blockers, "probe_output_empty:"+probe.Name)
			} else {
				blockers = append(blockers, "probe_output_not_ok:"+probe.Name)
			}
		}
		if probeRequired {
			blockers = append(blockers, probeBlockers(probe)...)
		}
	}

	rosbagProfiles := evaluateRosbagProfiles(plan, artifactDir)
	for _, rosbag := range rosbagProfiles {
		if !rosbag.OK {
			blockers = append(blockers, "rosbag_profile_failed:"+rosbag.Name)
		}
	}

	metrics := metricSummaryFromEvidence(probeOutputs, rosbagProfiles, artifactDir)
	if isHoverSLAMProfileTask(plan.TaskID) && len(metrics.StartupReadiness) > 0 {
		metrics.StartupReadiness["runtime_policy"] = startupReadinessPolicySummary(runtimeConfig.SlamHover.StartupReadinessPolicy)
	}
	landingEvidence := landingFromProbeOutputs(probeOutputs)
	if landingEvidence == nil {
		landingEvidence = landingFromHoverMissionSummary(metrics.HoverMission)
	}
	landing := helpers.BuildAcceptance(
		"simulation",
		landingConfig(project, runtimeConfig, plan.TaskID),
		landingEvidence,
		false,
	)
	if plan.TaskID != "hover-slam-only" {
		blockers = append(blockers, landing.Blockers...)
	}
	blockers = append(blockers, slamRuntimeLogBlockers(metrics.SLAMRuntimeLog)...)
	if plan.TaskID == "hover" {
		blockers = append(blockers, slamPreflightBlockers(metrics.SLAM, metrics.SLAMRuntimeLog)...)
		blockers = append(blockers, x2ScanSourceBlockers(metrics.X2)...)
		blockers = append(blockers, externalNavFeedbackBlockers(metrics.ExternalNav, metrics.MAVLinkExternalNav, metrics.HoverMission)...)
		if hoverUsesExternalNavSourceSelector(runtimeConfig) {
			blockers = append(blockers, externalNavSourceSelectorBlockers(metrics.ExternalNavSourceSelector)...)
		}
		blockers = append(blockers, hoverMissionBlockers(metrics.HoverMission)...)
		blockers = append(blockers, hoverXYAlignmentBlockers(metrics.HoverXYAlignment)...)
		blockers = append(blockers, scanReferenceCorrectionBlockers(metrics.ScanReferenceCorrection)...)
		if len(metrics.Controller) > 0 {
			blockers = append(blockers, hoverTakeoffBlockers(plan.TaskID, metrics.Controller)...)
		}
	}

	blockers = uniqueStrings(blockers)
	return GateEvaluation{
		OK:             len(blockers) == 0,
		Blocked:        len(blockers) > 0,
		Blockers:       blockers,
		ProbeOutputs:   probeOutputs,
		RosbagProfiles: rosbagProfiles,
		Landing:        landing,
		TaskChecks:     taskChecks,
		Metrics:        metrics,
	}
}

func runtimeProbeRequired(runtimeSpecs RuntimeSpecBundle, name string) bool {
	if len(runtimeSpecs.Probes) == 0 {
		return true
	}
	for _, probe := range runtimeSpecs.Probes {
		if probe.Name == name {
			return probe.Required
		}
	}
	return true
}

func metricSummaryFromEvidence(probes []ProbeOutputSummary, rosbags []RosbagGateSummary, artifactDirs ...string) MetricSummary {
	summary := MetricSummary{
		MetricEvidenceSources: map[string]string{},
	}
	if payload, topic := statusPayloadBySuffix(probes, "/hover/status"); payload != nil {
		summary.Hover = subsetMap(payload, "claim", "state", "phase", "reason", "pose_samples", "setpoints_sent_count", "local_position_count", "position", "max_hover_horizontal_drift_m", "max_hover_altitude_error_m", "max_hover_yaw_drift_rad", "drift_reference")
		summary.MetricEvidenceSources["hover"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/fcu/controller/status"); payload != nil {
		summary.Controller = subsetMap(payload, "ready", "state", "pose_samples", "control_route", "takeoff_alt_m", "fcu_mode_window", "cmd_vel_publish_count", "mavlink_setpoint_count", "mavlink_setpoint_error", "mavlink_local_position_count", "bootstrap_ready", "bootstrap")
		summary.MetricEvidenceSources["controller"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/fcu/setpoint/output"); payload != nil {
		summary.Setpoint = subsetMap(payload, "ready", "state", "intent_topic", "cmd_vel_topic", "setpoint_intent_samples", "cmd_vel_publish_count", "mavlink_setpoint_count", "mavlink_setpoint_error", "mavlink_local_position_count", "path_length_m", "min_path_length_m")
		summary.MetricEvidenceSources["setpoint"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/fcu/owner/status"); payload != nil {
		summary.Owner = subsetMap(payload, "active", "owner", "active_owner_count", "owner_unique", "conflicting_owners")
		summary.MetricEvidenceSources["owner"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/exploration/status"); payload != nil {
		summary.Exploration = subsetMap(payload, "claim", "strategy", "accepted_goals", "min_accepted_goals", "path_length_m", "min_path_length_m", "motion_speed_mps")
		summary.MetricEvidenceSources["exploration"] = topic
	}
	if payload, source := probePayloadByName(probes, "nav2_lifecycle_probe"); payload != nil {
		summary.Nav2 = subsetMap(payload, "claim", "nav2_claim", "nav2_lifecycle_active", "nav2_action_server_ready", "lifecycle", "action", "tf")
		summary.MetricEvidenceSources["nav2"] = source
	}
	if payload, topic := statusPayloadBySuffix(probes, "/navigation/status"); payload != nil {
		summary.Navigation = subsetMap(payload, "claim", "navigation_claim", "frontier_claim", "strategy", "frontier_candidates", "accepted_frontiers", "rejected_frontiers", "blacklisted_goals", "accepted_goals", "min_accepted_goals", "path_length_m", "min_path_length_m", "recovery_count", "completion_policy", "return_home_policy", "goal_success_ratio", "coverage_growth", "min_coverage_growth", "uses_gazebo_truth_as_input")
		summary.MetricEvidenceSources["navigation"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/navigation/adapter/status"); payload != nil {
		summary.NavigationAdapter = subsetMap(payload, "claim", "adapter_claim", "active", "max_xy_speed_mps", "fixed_altitude_m", "stop_on_stale_costmap", "stop_on_stale_slam", "clamp_count", "hold_count", "intent_count", "hold_reason")
		summary.MetricEvidenceSources["navigation_adapter"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/navigation/costmap_health"); payload != nil {
		summary.CostmapHealth = subsetMap(payload, "claim", "costmap_claim", "global_costmap_age_sec", "local_costmap_age_sec", "local_costmap_update_frequency_hz", "unknown_ratio", "obstacle_cells", "required_layers")
		summary.MetricEvidenceSources["costmap_health"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/slam/status"); payload != nil {
		summary.SLAM = subsetMap(payload, "state", "ready", "mode", "tracking_state", "odom_samples", "pose_samples", "max_position_jump_m", "map_frame", "base_frame", "quality", "scan", "imu", "tf", "output")
		summary.MetricEvidenceSources["slam"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/external_nav/status"); payload != nil {
		summary.ExternalNav = subsetMap(payload, "state", "ready", "odom", "imu", "height", "output")
		summary.MetricEvidenceSources["external_nav"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/external_nav/source_selector/status"); payload != nil {
		summary.ExternalNavSourceSelector = subsetMap(payload, "ready", "publish", "degraded", "source", "blockers", "hover_phase", "cartographer_scan_disagreement", "uses_gazebo_truth_input", "uses_known_map_input", "output_odom_topic", "output_frame_id", "output_child_frame_id", "slam_odom_topic", "scan_reference_odom_topic", "scan_reference_status_topic", "hold_age_ms", "hold_reason", "reject_reason", "rejected_step_m", "rejected_yaw_step_rad", "last_accepted_age_ms")
		summary.MetricEvidenceSources["external_nav_source_selector"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/mavlink_external_nav/status"); payload != nil {
		summary.MAVLinkExternalNav = subsetMap(payload, "state", "ready", "endpoint", "input_topic", "sent_count", "rate_hz", "odom_age_ms", "max_odom_age_ms", "odom_fresh", "frame_id", "child_frame_id", "quality", "use_fcu_roll_pitch", "fcu_attitude_age_ms", "local_position_pose_topic", "local_position_count", "local_position_age_ms", "max_local_position_age_ms", "fcu_local_position_ready")
		summary.MetricEvidenceSources["mavlink_external_nav"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/x2/status"); payload != nil {
		summary.X2 = subsetMap(payload, "source", "state", "scan_source", "scan_ideal_topic", "latest_scan_ideal_age_sec", "packet_count", "byte_count", "command_count", "range_min_m", "range_max_m", "sample_rate_hz")
		summary.MetricEvidenceSources["x2"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/scan_reference_drift/status"); payload != nil {
		summary.ScanReferenceRuntimeDrift = subsetMap(payload, "ready", "quality_good", "blockers", "source_topic", "reference_source", "estimator", "x_m", "y_m", "horizontal_drift_m", "valid_beams", "total_beams", "inlier_beams", "inlier_ratio", "residual_rms_m", "max_abs_residual_m", "raw_residual_rms_m", "raw_max_abs_residual_m", "uses_gazebo_truth_input", "uses_known_map_input", "correction_output_enabled", "phase4b_consistency_ok", "phase4b_consistency_source", "phase4b_consistency", "correction_eligibility", "correction_intent")
		summary.MetricEvidenceSources["scan_reference_runtime_drift_status"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/scan_reference_correction/status"); payload != nil {
		summary.ScanReferenceCorrection = subsetMap(payload, "ready", "state", "correction_enabled", "correction_applied", "fail_closed", "blockers", "hover_phase", "input_odom_topic", "scan_reference_status_topic", "output_odom_topic", "input_odom_qos_reliability", "output_odom_qos_reliability", "status_age_ms", "published_count", "corrected_count", "passthrough_count", "runtime_consistency_sample_count", "runtime_consistency_ok", "phase4b_consistency_ok", "phase4b_consistency_source", "measurement_delta_x_m", "measurement_delta_y_m", "measurement_delta_magnitude_m", "source_intent_x_m", "source_intent_y_m", "source_intent_magnitude_m", "axes", "allowed_axes", "blocked_axes", "axis_blockers", "max_correction_m", "max_measurement_delta_m", "max_correction_step_m", "uses_gazebo_truth_input", "uses_known_map_input", "writes_external_nav_odom", "external_nav_input_topic")
		summary.MetricEvidenceSources["scan_reference_correction_status"] = topic
	}
	if len(artifactDirs) > 0 && strings.TrimSpace(artifactDirs[0]) != "" {
		if metrics := parseHoverMissionSummary(filepath.Join(artifactDirs[0], "mission_summary.json")); metrics != nil {
			summary.HoverMission = metrics
			summary.MetricEvidenceSources["hover_mission"] = "mission_summary.json"
		}
		if metrics := parseSLAMRuntimeLog(artifactlayout.RuntimeLog(artifactDirs[0], "slam_backend.runtime.log")); metrics != nil {
			summary.SLAMRuntimeLog = metrics
			summary.MetricEvidenceSources["slam_runtime_log"] = artifactlayout.RuntimeLogRel("slam_backend.runtime.log")
		}
		if metrics := parseBenewakeTFMiniRuntimeLog(artifactlayout.RuntimeLog(artifactDirs[0], "benewake_tfmini_serial.runtime.log")); metrics != nil {
			summary.RangefinderSerial = metrics
			summary.MetricEvidenceSources["rangefinder_serial_runtime_log"] = artifactlayout.RuntimeLogRel("benewake_tfmini_serial.runtime.log")
		} else if metrics := parseBenewakeTFMiniRuntimeLog(filepath.Join(artifactDirs[0], "benewake_tfmini_serial.runtime.log")); metrics != nil {
			summary.RangefinderSerial = metrics
			summary.MetricEvidenceSources["rangefinder_serial_runtime_log"] = "benewake_tfmini_serial.runtime.log"
		}
		if runtimeReadiness := parseJSONMap(artifactlayout.Audit(artifactDirs[0], "startup_readiness_runtime.json")); runtimeReadiness != nil {
			summary.MetricEvidenceSources["startup_readiness_runtime"] = artifactlayout.AuditRel("startup_readiness_runtime.json")
			if summary.StartupReadiness == nil {
				summary.StartupReadiness = map[string]any{}
			}
			summary.StartupReadiness["runtime_decision"] = runtimeReadiness["final_decision"]
			summary.StartupReadiness["runtime_artifact"] = artifactlayout.AuditRel("startup_readiness_runtime.json")
		}
		if metrics, err := summarizeGazeboModelOdom(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd")); err == nil {
			summary.GazeboModelHoverDrift = metrics
			summary.MetricEvidenceSources["gazebo_model_hover_drift"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap.zstd"
		} else if metrics, err := summarizeGazeboModelOdom(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap")); err == nil {
			summary.GazeboModelHoverDrift = metrics
			summary.MetricEvidenceSources["gazebo_model_hover_drift"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap"
		}
		if metrics, err := summarizeScanReferenceHoverDrift(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd")); err == nil {
			summary.ScanReferenceHoverDrift = metrics
			summary.MetricEvidenceSources["scan_reference_hover_drift"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap.zstd"
		} else if metrics, err := summarizeScanReferenceHoverDrift(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap")); err == nil {
			summary.ScanReferenceHoverDrift = metrics
			summary.MetricEvidenceSources["scan_reference_hover_drift"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap"
		}
		if metrics, err := summarizeOdomHoverDrift(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd"), "/navlab/scan_reference_drift/odom", false); err == nil {
			summary.ScanReferenceRuntimeDrift = mergeMaps(summary.ScanReferenceRuntimeDrift, metrics)
			summary.MetricEvidenceSources["scan_reference_runtime_drift"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap.zstd"
			if statusMetrics, err := summarizeScanReferenceStatusHoverWindow(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd")); err == nil {
				summary.ScanReferenceRuntimeDrift = mergeMaps(summary.ScanReferenceRuntimeDrift, statusMetrics)
			}
		} else if metrics, err := summarizeOdomHoverDrift(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap"), "/navlab/scan_reference_drift/odom", false); err == nil {
			summary.ScanReferenceRuntimeDrift = mergeMaps(summary.ScanReferenceRuntimeDrift, metrics)
			summary.MetricEvidenceSources["scan_reference_runtime_drift"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap"
			if statusMetrics, err := summarizeScanReferenceStatusHoverWindow(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap")); err == nil {
				summary.ScanReferenceRuntimeDrift = mergeMaps(summary.ScanReferenceRuntimeDrift, statusMetrics)
			}
		}
		if metrics, err := summarizeOdomHoverDrift(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd"), "/slam/odom_corrected", false); err == nil {
			summary.ScanReferenceCorrection = mergeMaps(summary.ScanReferenceCorrection, map[string]any{"corrected_odom_hover_drift": metrics})
			summary.MetricEvidenceSources["scan_reference_corrected_odom_drift"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap.zstd"
		} else if metrics, err := summarizeOdomHoverDrift(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap"), "/slam/odom_corrected", false); err == nil {
			summary.ScanReferenceCorrection = mergeMaps(summary.ScanReferenceCorrection, map[string]any{"corrected_odom_hover_drift": metrics})
			summary.MetricEvidenceSources["scan_reference_corrected_odom_drift"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap"
		}
		if statusMetrics, err := summarizeScanReferenceCorrectionStatusHoverWindow(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd")); err == nil {
			summary.ScanReferenceCorrection = mergeMaps(summary.ScanReferenceCorrection, statusMetrics)
			summary.MetricEvidenceSources["scan_reference_correction_status_hover_window"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap.zstd"
		} else if statusMetrics, err := summarizeScanReferenceCorrectionStatusHoverWindow(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap")); err == nil {
			summary.ScanReferenceCorrection = mergeMaps(summary.ScanReferenceCorrection, statusMetrics)
			summary.MetricEvidenceSources["scan_reference_correction_status_hover_window"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap"
		}
		if statusMetrics, source := summarizeLatestJSONStatusFromHoverRosbag(artifactDirs[0], "/external_nav/source_selector/status", "ready", "publish", "degraded", "source", "blockers", "hover_phase", "cartographer_scan_disagreement", "uses_gazebo_truth_input", "uses_known_map_input", "output_odom_topic", "output_frame_id", "output_child_frame_id", "slam_odom_topic", "scan_reference_odom_topic", "scan_reference_status_topic", "hold_age_ms", "hold_reason", "reject_reason", "rejected_step_m", "rejected_yaw_step_rad", "last_accepted_age_ms"); statusMetrics != nil {
			summary.ExternalNavSourceSelector = mergeMaps(summary.ExternalNavSourceSelector, statusMetrics)
			summary.MetricEvidenceSources["external_nav_source_selector"] = source
		}
		if statusMetrics, source := summarizeLatestJSONStatusFromHoverRosbag(artifactDirs[0], "/external_nav/status", "state", "ready", "odom", "imu", "height", "output"); statusMetrics != nil {
			summary.ExternalNav = mergeMaps(summary.ExternalNav, statusMetrics)
			summary.MetricEvidenceSources["external_nav"] = source
		}
		if statusMetrics, source := summarizeLatestJSONStatusFromHoverRosbag(artifactDirs[0], "/mavlink_external_nav/status", "state", "ready", "endpoint", "input_topic", "sent_count", "rate_hz", "odom_age_ms", "max_odom_age_ms", "odom_fresh", "frame_id", "child_frame_id", "quality", "use_fcu_roll_pitch", "fcu_attitude_age_ms", "local_position_pose_topic", "local_position_count", "local_position_age_ms", "max_local_position_age_ms", "fcu_local_position_ready"); statusMetrics != nil {
			summary.MAVLinkExternalNav = mergeMaps(summary.MAVLinkExternalNav, statusMetrics)
			summary.MetricEvidenceSources["mavlink_external_nav"] = source
		}
		if metrics, err := summarizeHoverXYAlignment(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd")); err == nil {
			summary.HoverXYAlignment = metrics
			summary.MetricEvidenceSources["hover_xy_alignment"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap.zstd"
		} else if metrics, err := summarizeHoverXYAlignment(filepath.Join(artifactDirs[0], "rosbag", "hover_rosbag", "hover_rosbag_0.mcap")); err == nil {
			summary.HoverXYAlignment = metrics
			summary.MetricEvidenceSources["hover_xy_alignment"] = "rosbag/hover_rosbag/hover_rosbag_0.mcap"
		}
	}
	if payload, topic := statusPayloadBySuffix(probes, "/scan_integrity/status"); payload != nil {
		summary.ScanIntegrity = subsetMap(payload, "claim", "scan_contract", "scan_samples", "drop_ratio", "false_drop_ratio", "compensated_ratio", "floor_hit_risk_beam_ratio", "max_scan_attitude_time_offset_ms", "source_evidence")
		summary.MetricEvidenceSources["scan_integrity"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/scan_stabilization/status"); payload != nil {
		summary.ScanStabilization = subsetMap(payload, "claim", "mode", "scan_samples", "imu_samples", "retained_beam_ratio", "rejected_beam_ratio", "floor_hit_risk_beam_ratio", "max_vertical_projection_error_m")
		summary.MetricEvidenceSources["scan_stabilization"] = topic
	}
	if payload, topic := statusPayloadBySuffix(probes, "/airframe_disturbance/status"); payload != nil {
		summary.AirframeDisturbance = subsetMap(payload, "claim", "profile", "imu_samples", "pose_samples", "max_abs_roll_deg", "max_abs_pitch_deg", "estimated_attitude_response_lag_ms", "attitude_overshoot_count", "attitude_noise_rms_deg", "false_drop_ratio", "compensation_jitter_score", "scan_integrity", "profile_sweep", "fcu_mode_window")
		summary.MetricEvidenceSources["airframe_disturbance"] = topic
	}
	for _, rosbag := range rosbags {
		if len(rosbag.MessageCounts) == 0 {
			continue
		}
		if summary.RosbagMessageCounts == nil {
			summary.RosbagMessageCounts = map[string]map[string]int{}
		}
		summary.RosbagMessageCounts[rosbag.Name] = rosbag.MessageCounts
	}
	summary.StartupReadiness = startupReadinessSummary(probes, rosbags, summary)
	if len(artifactDirs) > 0 && strings.TrimSpace(artifactDirs[0]) != "" {
		if runtimeReadiness := parseJSONMap(artifactlayout.Audit(artifactDirs[0], "startup_readiness_runtime.json")); runtimeReadiness != nil {
			if summary.StartupReadiness == nil {
				summary.StartupReadiness = map[string]any{}
			}
			summary.StartupReadiness["runtime_decision"] = runtimeReadiness["final_decision"]
			summary.StartupReadiness["runtime_artifact"] = artifactlayout.AuditRel("startup_readiness_runtime.json")
			if _, ok := summary.StartupReadiness["classification"]; !ok {
				summary.StartupReadiness["classification"] = startupRuntimeClassification(runtimeReadiness)
				summary.StartupReadiness["preflight_invalid"] = summary.StartupReadiness["classification"] == "startup_readiness_failure"
				summary.StartupReadiness["valid_hover_body_sample"] = false
				summary.StartupReadiness["not_hover_span_slo"] = summary.StartupReadiness["classification"] == "startup_readiness_failure"
				summary.StartupReadiness["reason_codes"] = startupRuntimeReasonCodes(runtimeReadiness)
			}
			summary.MetricEvidenceSources["startup_readiness_runtime"] = artifactlayout.AuditRel("startup_readiness_runtime.json")
		}
	}
	if len(summary.StartupReadiness) > 0 {
		summary.MetricEvidenceSources["startup_readiness"] = "probe_outputs+mission_summary+rosbag_profiles"
	}
	if len(summary.MetricEvidenceSources) == 0 {
		summary.MetricEvidenceSources = nil
	}
	return summary
}

func startupReadinessSummary(probes []ProbeOutputSummary, rosbags []RosbagGateSummary, metrics MetricSummary) map[string]any {
	mission := metrics.HoverMission
	if len(mission) == 0 && len(probes) == 0 && len(rosbags) == 0 {
		return nil
	}
	hoverHoldSeen := stringAnySliceContains(mission["phases_seen"], "hover_hold")
	airborneSeen, _ := mission["airborne_seen"].(bool)
	missionOK := hoverMissionCompletedOK(mission)
	abortReason, _ := mission["mission_abort_reason"].(string)
	fsmState, _ := mission["mission_phase_state"].(string)
	classification := "unknown"
	if missionOK || hoverHoldSeen {
		classification = "hover_body_sample"
	} else if len(mission) > 0 {
		classification = "startup_readiness_failure"
	}

	rangeSample := probeSampleByTopic(probes, "/rangefinder/down/range")
	rangeStatusSample := probeSampleByTopic(probes, "/rangefinder/down/status")
	rangeStatus := mapFromAny(rangeStatusSample["parsed"])
	externalHeight := mapFromAny(metrics.ExternalNav["height"])
	counts := mergedRosbagMessageCounts(rosbags)
	reasons := []string{}
	addReason := func(reason string) {
		if reason != "" && !stringSliceContains(reasons, reason) {
			reasons = append(reasons, reason)
		}
	}
	if classification == "startup_readiness_failure" {
		if strings.Contains(abortReason, "preflight") {
			addReason("preflight_timeout")
		}
		if strings.Contains(fsmState, "wait_nav_ready") {
			addReason("wait_nav_ready")
		}
		if strings.Contains(abortReason, "waiting_for_external_nav") {
			addReason("external_nav_waiting")
		}
		if len(mission) > 0 && !airborneSeen {
			addReason("airborne_not_seen")
		}
		if len(mission) > 0 && !hoverHoldSeen {
			addReason("hover_hold_not_seen")
		}
		if !boolFromMap(rangeStatus, "ready") {
			addReason("rangefinder_not_ready")
		}
		if metricInt(rangeStatus, "input_count") == 0 {
			addReason("rangefinder_input_missing")
		}
		if sampleFailureKind(rangeSample) == "topic_sample_missing" || counts["/rangefinder/down/range"] == 0 {
			addReason("rangefinder_range_sample_missing")
		}
		if len(externalHeight) > 0 && !boolFromMap(externalHeight, "ready") {
			addReason("external_nav_waiting_for_height")
		}
		if counts["/height/estimate"] == 0 {
			addReason("height_estimate_missing")
		}
		if len(reasons) == 0 {
			addReason("startup_not_ready")
		}
	}

	return map[string]any{
		"classification":            classification,
		"preflight_invalid":         classification == "startup_readiness_failure",
		"valid_hover_body_sample":   classification == "hover_body_sample",
		"not_hover_span_slo":        classification == "startup_readiness_failure",
		"reason_codes":              reasons,
		"mission":                   startupMissionEvidence(mission, hoverHoldSeen),
		"rangefinder":               startupRangefinderEvidence(rangeSample, rangeStatusSample, rangeStatus, metrics.RangefinderSerial, counts),
		"height":                    startupHeightEvidence(externalHeight, counts),
		"probe_semantics":           startupProbeSemantics(probes),
		"rosbag_message_counts":     subsetIntMap(counts, "/rangefinder/down/range", "/rangefinder/down/status", "/height/estimate", "/height/status", "/external_nav/odom", "/navlab/fcu/local_position_pose"),
		"decision_rule":             "startup_readiness_failure artifacts are excluded from hover span SLO percentiles and routed to Phase 51 startup/readiness.",
		"runtime_control_unchanged": true,
	}
}

func startupRuntimeClassification(runtimeReadiness map[string]any) string {
	decision := mapFromAny(runtimeReadiness["final_decision"])
	switch strings.TrimSpace(stringFromAny(decision["action"])) {
	case StartupReadinessActionProceed:
		return "startup_readiness_passed"
	case StartupReadinessActionFailFast, StartupReadinessActionFailClosed, StartupReadinessActionRestartLeaf:
		return "startup_readiness_failure"
	default:
		return "startup_readiness_unknown"
	}
}

func startupRuntimeReasonCodes(runtimeReadiness map[string]any) []string {
	decision := mapFromAny(runtimeReadiness["final_decision"])
	reason := strings.TrimSpace(stringFromAny(decision["reason"]))
	if reason == "" {
		return nil
	}
	return []string{reason}
}

func startupMissionEvidence(mission map[string]any, hoverHoldSeen bool) map[string]any {
	if len(mission) == 0 {
		return map[string]any{"exists": false}
	}
	return map[string]any{
		"exists":                  true,
		"ok":                      mission["ok"],
		"reason":                  mission["reason"],
		"mission_phase_state":     mission["mission_phase_state"],
		"mission_abort_reason":    mission["mission_abort_reason"],
		"airborne_seen":           mission["airborne_seen"],
		"hover_hold_seen":         hoverHoldSeen,
		"guided_seen":             mission["guided_seen"],
		"armed_seen":              mission["armed_seen"],
		"local_position_count":    metricInt(mission, "local_position_count"),
		"setpoints_sent_count":    metricInt(mission, "setpoints_sent_count"),
		"hover_hold_duration_sec": metricFloat(mission, "hover_hold_duration_sec"),
	}
}

func startupRangefinderEvidence(rangeSample map[string]any, statusSample map[string]any, status map[string]any, serial map[string]any, counts map[string]int) map[string]any {
	return map[string]any{
		"range_sample_ok":           boolFromMap(rangeSample, "ok"),
		"range_sample_return_code":  metricInt(rangeSample, "return_code"),
		"range_sample_failure_kind": sampleFailureKind(rangeSample),
		"status_sample_ok":          boolFromMap(statusSample, "ok"),
		"ready":                     boolFromMap(status, "ready"),
		"state":                     status["state"],
		"source":                    status["source"],
		"input_count":               metricInt(status, "input_count"),
		"latest_distance_m":         status["latest_distance_m"],
		"latest_input_age_sec":      status["latest_input_age_sec"],
		"virtual_serial_link":       status["virtual_serial_link"],
		"range_topic":               status["range_topic"],
		"scan_ideal_topic":          status["scan_ideal_topic"],
		"serial":                    serial,
		"serial_byte_count":         metricInt(serial, "byte_count"),
		"serial_frame_count":        metricInt(serial, "frame_count"),
		"rosbag_range_count":        counts["/rangefinder/down/range"],
		"rosbag_status_count":       counts["/rangefinder/down/status"],
	}
}

func startupHeightEvidence(externalHeight map[string]any, counts map[string]int) map[string]any {
	return map[string]any{
		"external_nav_height_ready":    boolFromMap(externalHeight, "ready"),
		"external_nav_height":          externalHeight,
		"rosbag_height_estimate_count": counts["/height/estimate"],
		"rosbag_height_status_count":   counts["/height/status"],
	}
}

func startupProbeSemantics(probes []ProbeOutputSummary) map[string]any {
	samples := map[string]any{}
	for _, probe := range probes {
		rawSamples := mapFromAny(probe.Payload["samples"])
		for topic, rawSample := range rawSamples {
			sample := mapFromAny(rawSample)
			failureKind := sampleFailureKind(sample)
			if boolFromMap(sample, "ok") && failureKind == "" {
				continue
			}
			key := probe.Name + ":" + topic
			samples[key] = map[string]any{
				"topic":         topic,
				"probe":         probe.Name,
				"ok":            boolFromMap(sample, "ok"),
				"return_code":   metricInt(sample, "return_code"),
				"sample_method": sample["sample_method"],
				"failure_kind":  failureKind,
				"has_stdout":    strings.TrimSpace(stringFromAny(sample["stdout"])) != "",
				"parsed_ready":  mapFromAny(sample["parsed"])["ready"],
				"parsed_state":  mapFromAny(sample["parsed"])["state"],
			}
		}
	}
	return map[string]any{
		"samples": samples,
		"known_failure_kinds": []string{
			"topic_type_missing",
			"topic_sample_missing",
			"sample_stdout_present_timeout",
			"parsed_payload_not_ready",
		},
	}
}

func probeSampleByTopic(probes []ProbeOutputSummary, topic string) map[string]any {
	for _, probe := range probes {
		samples := mapFromAny(probe.Payload["samples"])
		if sample := mapFromAny(samples[topic]); sample != nil {
			return sample
		}
	}
	return nil
}

func sampleFailureKind(sample map[string]any) string {
	if len(sample) == 0 {
		return "topic_sample_missing"
	}
	if kind, _ := sample["failure_kind"].(string); strings.TrimSpace(kind) != "" {
		return strings.TrimSpace(kind)
	}
	if errText, _ := sample["error"].(string); strings.Contains(errText, "topic_type_missing") {
		return "topic_type_missing"
	}
	if strings.TrimSpace(stringFromAny(sample["stdout"])) != "" && metricInt(sample, "return_code") == 124 {
		return "sample_stdout_present_timeout"
	}
	if !boolFromMap(sample, "ok") {
		return "topic_sample_missing"
	}
	parsed := mapFromAny(sample["parsed"])
	if ready, ok := parsed["ready"].(bool); ok && !ready {
		return "parsed_payload_not_ready"
	}
	return ""
}

func mergedRosbagMessageCounts(rosbags []RosbagGateSummary) map[string]int {
	out := map[string]int{}
	for _, rosbag := range rosbags {
		for topic, count := range rosbag.MessageCounts {
			out[topic] += count
		}
	}
	return out
}

func subsetIntMap(source map[string]int, keys ...string) map[string]int {
	out := map[string]int{}
	for _, key := range keys {
		out[key] = source[key]
	}
	return out
}

func boolFromMap(values map[string]any, key string) bool {
	value, _ := values[key].(bool)
	return value
}

func stringFromAny(value any) string {
	text, _ := value.(string)
	return text
}

func parseHoverMissionSummary(path string) map[string]any {
	payload := parseJSONMap(path)
	if payload == nil {
		return nil
	}
	if payload["parse_error"] != nil {
		payload["ok"] = false
		return payload
	}
	return subsetHoverMissionSummary(payload)
}

func parseJSONMap(path string) map[string]any {
	var data []byte
	var err error
	for attempt := 0; attempt < 50; attempt++ {
		data, err = os.ReadFile(path)
		if err != nil {
			return nil
		}
		payload := map[string]any{}
		if err := json.Unmarshal(data, &payload); err == nil {
			payload["path"] = path
			payload["exists"] = true
			return payload
		}
		time.Sleep(100 * time.Millisecond)
	}
	payload := map[string]any{}
	if err := json.Unmarshal(data, &payload); err != nil {
		return map[string]any{"path": path, "exists": true, "parse_error": err.Error(), "ok": false}
	}
	payload["path"] = path
	payload["exists"] = true
	return payload
}

func subsetHoverMissionSummary(payload map[string]any) map[string]any {
	if reason := missionAbortReason(payload); reason != "" {
		payload["mission_abort_reason"] = reason
	}
	return subsetMap(payload,
		"path",
		"exists",
		"ok",
		"reason",
		"mission_phase_state",
		"mission_phase_blocker",
		"mission_phase_last_transition_reason",
		"mission_abort_reason",
		"hover_body_ok",
		"landing_ok",
		"phases_seen",
		"phase_counts",
		"guided_seen",
		"armed_seen",
		"takeoff_ack_ok",
		"airborne_seen",
		"local_position_count",
		"setpoints_sent_count",
		"target_alt_m",
		"takeoff_alt_m",
		"current_z_ned",
		"last_position",
		"target_z_ned",
		"altitude_error_m",
		"hover_altitude_sources",
		"hover_altitude_crosscheck",
		"hover_altitude_tolerance_m",
		"hover_hold_sec",
		"hover_hold_duration_sec",
		"hover_hold_segments_seen",
		"require_external_nav",
		"external_nav_ready",
		"external_nav_status_age_sec",
		"external_nav_status_history",
		"mavlink_external_nav_ready",
		"fcu_local_position_ready",
		"mavlink_external_nav_status_age_sec",
		"mavlink_external_nav_status",
		"mavlink_external_nav_status_history",
		"land_command_accepted",
		"touchdown_confirmed",
		"disarmed",
		"motors_safe",
		"hover_drift",
		"landing",
		"parse_error",
	)
}

func externalNavFeedbackBlockers(externalNav map[string]any, mavlinkExternalNav map[string]any, mission map[string]any) []string {
	blockers := []string{}
	missionOK := hoverMissionCompletedOK(mission)
	if len(externalNav) == 0 {
		blockers = append(blockers, "external_nav_status_missing")
	} else {
		if ready, _ := externalNav["ready"].(bool); !ready && !missionOK {
			blockers = append(blockers, "external_nav_bridge_not_ready")
		}
		odom := mapFromAny(externalNav["odom"])
		inputTopic, _ := odom["input_topic"].(string)
		inputTopic = strings.TrimSpace(inputTopic)
		if inputTopic == "" {
			blockers = append(blockers, "external_nav_input_topic_missing")
		} else {
			if !isAllowedExternalNavSLAMInputTopic(inputTopic) {
				blockers = append(blockers, "external_nav_not_using_slam_odom")
			}
			if strings.Contains(inputTopic, "gazebo") || inputTopic == "/odometry" {
				blockers = append(blockers, "external_nav_uses_diagnostic_truth_input")
			}
		}
	}
	if len(mavlinkExternalNav) == 0 {
		blockers = append(blockers, "mavlink_external_nav_status_missing")
		return blockers
	}
	if state, _ := mavlinkExternalNav["state"].(string); state != "sending" {
		blockers = append(blockers, "mavlink_external_nav_not_sending")
	}
	if ready, _ := mavlinkExternalNav["ready"].(bool); !ready && !missionOK {
		blockers = append(blockers, "mavlink_external_nav_not_ready")
	}
	if metricInt(mavlinkExternalNav, "sent_count") <= 0 {
		blockers = append(blockers, "mavlink_external_nav_not_sent")
	}
	if inputTopic, _ := mavlinkExternalNav["input_topic"].(string); strings.TrimSpace(inputTopic) != "/external_nav/odom" {
		blockers = append(blockers, "mavlink_external_nav_input_topic_invalid")
	}
	if metricInt(mavlinkExternalNav, "local_position_count") <= 0 {
		blockers = append(blockers, "external_nav_not_seen_by_fcu")
	}
	if fcuReady, ok := mavlinkExternalNav["fcu_local_position_ready"].(bool); ok && !fcuReady && !missionOK {
		blockers = append(blockers, "external_nav_fcu_local_position_not_ready")
	}
	localPositionAgeMS := metricFloat(mavlinkExternalNav, "local_position_age_ms")
	maxLocalPositionAgeMS := metricFloat(mavlinkExternalNav, "max_local_position_age_ms")
	if maxLocalPositionAgeMS <= 0 {
		maxLocalPositionAgeMS = 1000
	}
	if !missionOK && (localPositionAgeMS < 0 || localPositionAgeMS > maxLocalPositionAgeMS) {
		blockers = append(blockers, "external_nav_fcu_local_position_stale")
	}
	return blockers
}

func hoverMissionCompletedOK(mission map[string]any) bool {
	if len(mission) == 0 {
		return false
	}
	ok, _ := mission["ok"].(bool)
	if !ok {
		return false
	}
	if state, _ := mission["mission_phase_state"].(string); hoverMissionFSMCompleted(strings.TrimSpace(state)) {
		return true
	}
	if reason, _ := mission["reason"].(string); strings.TrimSpace(reason) == "hover_complete" {
		return true
	}
	return false
}

func hoverMissionFSMCompleted(state string) bool {
	return state == "S12 landing_complete" || state == "S13 task_success"
}

func missionAbortReason(mission map[string]any) string {
	for _, key := range []string{"mission_phase_blocker", "mission_abort_reason"} {
		if reason, _ := mission[key].(string); strings.TrimSpace(reason) != "" {
			return strings.TrimSpace(reason)
		}
	}
	history, ok := mission["mission_phase_history"].([]any)
	if !ok {
		return ""
	}
	for index := len(history) - 1; index >= 0; index-- {
		entry, ok := history[index].(map[string]any)
		if !ok {
			continue
		}
		state, _ := entry["state"].(string)
		guard, _ := entry["guard"].(string)
		if strings.TrimSpace(state) != "S_abort" && strings.TrimSpace(guard) != "abort" {
			continue
		}
		if blocker, _ := entry["blocker"].(string); strings.TrimSpace(blocker) != "" {
			return strings.TrimSpace(blocker)
		}
		if reason, _ := entry["reason"].(string); strings.TrimSpace(reason) != "" {
			return strings.TrimSpace(reason)
		}
	}
	return ""
}

func isAllowedExternalNavSLAMInputTopic(topic string) bool {
	switch strings.TrimSpace(topic) {
	case "/slam/odom", "/slam/odom_corrected", "/external_nav/odom_candidate":
		return true
	default:
		return false
	}
}

func hoverUsesExternalNavSourceSelector(runtimeConfig config.TaskRuntimeConfig) bool {
	topic := strings.TrimSpace(runtimeConfig.SlamHover.ExternalNavInputOdomTopic)
	return topic == "" || topic == "/external_nav/odom_candidate"
}

func hoverMissionBlockers(mission map[string]any) []string {
	if len(mission) == 0 {
		return []string{"hover_mission_summary_missing"}
	}
	if parseError, _ := mission["parse_error"].(string); strings.TrimSpace(parseError) != "" {
		return []string{"hover_mission_summary_unreadable"}
	}
	blockers := []string{}
	missionOK := hoverMissionCompletedOK(mission)
	if ok, _ := mission["ok"].(bool); !ok {
		blockers = append(blockers, "hover_mission_not_ok")
	}
	if !missionOK {
		if abortReason, _ := mission["mission_abort_reason"].(string); strings.TrimSpace(abortReason) != "" {
			blockers = append(blockers, "hover_mission_abort:"+strings.TrimSpace(abortReason))
		}
	}
	if requireExternalNav, _ := mission["require_external_nav"].(bool); requireExternalNav {
		if externalNavReady, _ := mission["external_nav_ready"].(bool); !externalNavReady && !missionOK {
			blockers = append(blockers, "hover_mission_external_nav_not_ready")
		}
	}
	if !stringAnySliceContains(mission["phases_seen"], "hover_hold") {
		blockers = append(blockers, "hover_mission_hover_hold_missing")
	}
	for _, field := range []string{"guided_seen", "armed_seen", "airborne_seen"} {
		if value, _ := mission[field].(bool); !value {
			blockers = append(blockers, "hover_mission_"+field+"_missing")
		}
	}
	if metricInt(mission, "local_position_count") <= 0 {
		blockers = append(blockers, "hover_mission_local_position_missing")
	}
	if metricInt(mission, "setpoints_sent_count") <= 0 {
		blockers = append(blockers, "hover_mission_setpoints_missing")
	}
	targetAlt := metricFloat(mission, "target_alt_m")
	if targetAlt <= 0 {
		targetAlt = metricFloat(mission, "takeoff_alt_m")
	}
	if targetAlt <= 0 || !metricNumberPresent(mission, "current_z_ned") || !metricNumberPresent(mission, "altitude_error_m") {
		blockers = append(blockers, "hover_mission_altitude_evidence_missing")
	} else {
		altitudeError := metricFloat(mission, "altitude_error_m")
		tolerance := metricFloat(mission, "hover_altitude_tolerance_m")
		if tolerance <= 0 {
			tolerance = 0.18
		}
		if altitudeError > tolerance {
			blockers = append(blockers, "hover_mission_target_altitude_not_reached")
		}
	}
	altitudeCrosscheck := mapFromAny(mission["hover_altitude_crosscheck"])
	if len(altitudeCrosscheck) == 0 {
		blockers = append(blockers, "hover_mission_altitude_crosscheck_missing")
	} else {
		if metricInt(altitudeCrosscheck, "sample_count") < 2 {
			blockers = append(blockers, "hover_mission_altitude_crosscheck_samples_missing")
		}
		if ok, _ := altitudeCrosscheck["ok"].(bool); !ok {
			blockers = append(blockers, "hover_mission_altitude_crosscheck_failed")
		}
	}
	if takeoffAckOK, _ := mission["takeoff_ack_ok"].(bool); !takeoffAckOK && !hoverMissionHasTakeoffEvidence(mission) {
		blockers = append(blockers, "hover_mission_takeoff_ack_missing")
	}
	hoverDrift := mapFromAny(mission["hover_drift"])
	hoverHoldSec := metricFloat(mission, "hover_hold_sec")
	durationTolerance := metricFloat(hoverDrift, "duration_tolerance_sec")
	if durationTolerance <= 0 {
		durationTolerance = 0.25
	}
	if len(hoverDrift) == 0 {
		blockers = append(blockers, "hover_mission_drift_evidence_missing")
	} else {
		if metricInt(hoverDrift, "sample_count") < 2 {
			blockers = append(blockers, "hover_mission_hold_samples_missing")
		}
		if hoverHoldSec > 0 && metricFloat(hoverDrift, "duration_sec") < hoverHoldSec-durationTolerance {
			blockers = append(blockers, "hover_mission_hold_duration_short")
		}
		if driftOK, _ := hoverDrift["ok"].(bool); !driftOK {
			blockers = append(blockers, "hover_mission_drift_not_ok")
		}
		if horizontalDriftOK, ok := hoverDrift["horizontal_drift_ok"].(bool); ok && !horizontalDriftOK {
			blockers = append(blockers, "hover_mission_horizontal_drift_not_ok")
		}
		if horizontalSpanOK, ok := hoverDrift["horizontal_span_ok"].(bool); ok && !horizontalSpanOK {
			blockers = append(blockers, "hover_mission_horizontal_span_not_ok")
		}
		if zSpanOK, ok := hoverDrift["z_span_ok"].(bool); ok && !zSpanOK {
			blockers = append(blockers, "hover_mission_z_span_not_ok")
		}
		if slamQualityLossOK, ok := hoverDrift["no_slam_quality_loss_after_airborne"].(bool); ok && !slamQualityLossOK {
			blockers = append(blockers, "hover_mission_slam_quality_lost_after_airborne")
		}
		if externalNavLossOK, ok := hoverDrift["no_external_nav_loss_after_airborne"].(bool); ok && !externalNavLossOK {
			blockers = append(blockers, "hover_mission_external_nav_lost_after_airborne")
		}
		if mavlinkExternalNavLossOK, ok := hoverDrift["no_mavlink_external_nav_loss_after_airborne"].(bool); ok && !mavlinkExternalNavLossOK {
			blockers = append(blockers, "hover_mission_mavlink_external_nav_lost_after_airborne")
		}
		if slamJumpOK, ok := hoverDrift["no_slam_quality_jump_in_hover_window"].(bool); ok && !slamJumpOK {
			blockers = append(blockers, "hover_mission_slam_quality_jump_in_hover_window")
		}
		switch quality, _ := hoverDrift["quality"].(string); quality {
		case "tight", "nominal", "marginal":
		case "":
			blockers = append(blockers, "hover_mission_drift_quality_missing")
		default:
			blockers = append(blockers, "hover_mission_drift_quality_unacceptable")
		}
	}
	if hoverBodyOK, _ := mission["hover_body_ok"].(bool); !hoverBodyOK {
		blockers = append(blockers, "hover_mission_body_not_ok")
	}
	if landingOK, _ := mission["landing_ok"].(bool); !landingOK {
		blockers = append(blockers, "hover_mission_landing_not_ok")
	}
	landing := mapFromAny(mission["landing"])
	if len(landing) == 0 {
		landing = mission
	}
	for _, field := range []string{"touchdown_confirmed", "disarmed", "motors_safe"} {
		if value, _ := landing[field].(bool); !value {
			blockers = append(blockers, "hover_mission_landing_"+field+"_missing")
		}
	}
	return blockers
}

type gazeboOdomSample struct {
	X            float64
	Y            float64
	Z            float64
	FrameID      string
	ChildFrameID string
}

type scanDriftSample struct {
	AngleMin       float64
	AngleIncrement float64
	RangeMin       float64
	RangeMax       float64
	Ranges         []float64
	LogTimeSec     float64
}

type scanReferenceStatusSample struct {
	LogTimeSec          float64
	QualityGood         bool
	CorrectionAllowed   bool
	ResidualRMS         float64
	RawResidualRMS      float64
	InlierRatio         float64
	AllowedAxes         []any
	Blockers            []any
	IntentActive        bool
	IntentAxes          []any
	IntentMagnitude     float64
	IntentX             float64
	IntentY             float64
	IntentMaxCorrection float64
	IntentBlockers      []any
	Phase4BOK           bool
	Phase4BSource       string
	Phase4BConsistency  map[string]any
}

type scanReferenceCorrectionStatusSample struct {
	LogTimeSec        float64
	Status            map[string]any
	CorrectionApplied bool
}

type timedGazeboOdomSample struct {
	gazeboOdomSample
	LogTimeSec float64
}

type timedXYSample struct {
	X            float64
	Y            float64
	Z            float64
	FrameID      string
	ChildFrameID string
	LogTimeSec   float64
}

func hoverXYAlignmentBlockers(summary map[string]any) []string {
	if len(summary) == 0 {
		return nil
	}
	if ok, _ := summary["ok"].(bool); ok {
		return nil
	}
	blockers := stringsFromAny(summary["blockers"])
	if len(blockers) == 0 {
		return []string{"hover_xy_evidence_disagreement"}
	}
	return blockers
}

func scanReferenceCorrectionBlockers(summary map[string]any) []string {
	if len(summary) == 0 {
		return nil
	}
	blockers := []string{}
	if usedTruth, _ := summary["uses_gazebo_truth_input"].(bool); usedTruth {
		blockers = append(blockers, "scan_reference_correction_uses_gazebo_truth")
	}
	if writesExternal, _ := summary["writes_external_nav_odom"].(bool); writesExternal {
		blockers = append(blockers, "scan_reference_correction_writes_external_nav_directly")
	}
	correctionApplied, _ := summary["correction_applied"].(bool)
	if metricInt(summary, "corrected_count") > 0 {
		correctionApplied = true
	}
	if metricInt(summary, "hover_window_correction_applied_count") > 0 {
		correctionApplied = true
	}
	if correctionApplied {
		if metricInt(summary, "hover_window_applied_without_phase4b_count") > 0 {
			blockers = append(blockers, "scan_reference_correction_phase4b_not_ok")
		} else if _, hasWindowEvidence := summary["hover_window_applied_without_phase4b_count"]; !hasWindowEvidence {
			if phase4BOK, _ := summary["phase4b_consistency_ok"].(bool); !phase4BOK {
				blockers = append(blockers, "scan_reference_correction_phase4b_not_ok")
			}
		}
		if metricInt(summary, "hover_window_applied_without_runtime_consistency_count") > 0 {
			blockers = append(blockers, "scan_reference_correction_runtime_consistency_not_ok")
		} else if _, hasWindowEvidence := summary["hover_window_applied_without_runtime_consistency_count"]; !hasWindowEvidence {
			if runtimeOK, _ := summary["runtime_consistency_ok"].(bool); !runtimeOK {
				blockers = append(blockers, "scan_reference_correction_runtime_consistency_not_ok")
			}
		}
	}
	return blockers
}

func externalNavSourceSelectorBlockers(summary map[string]any) []string {
	if len(summary) == 0 {
		return []string{"external_nav_source_selector_status_missing"}
	}
	blockers := []string{}
	if ready, ok := summary["ready"].(bool); ok && !ready {
		blockers = append(blockers, "external_nav_source_selector_not_ready")
	}
	if publish, ok := summary["publish"].(bool); ok && !publish {
		blockers = append(blockers, "external_nav_source_selector_not_publishing")
	}
	if rejectReason, _ := summary["reject_reason"].(string); strings.TrimSpace(rejectReason) != "" {
		blockers = append(blockers, "external_nav_source_selector_rejected:"+strings.TrimSpace(rejectReason))
	}
	if usedTruth, _ := summary["uses_gazebo_truth_input"].(bool); usedTruth {
		blockers = append(blockers, "external_nav_source_selector_uses_gazebo_truth")
	}
	if usesMap, _ := summary["uses_known_map_input"].(bool); usesMap {
		blockers = append(blockers, "external_nav_source_selector_uses_known_map")
	}
	if outputTopic, _ := summary["output_odom_topic"].(string); strings.TrimSpace(outputTopic) != "/external_nav/odom_candidate" {
		blockers = append(blockers, "external_nav_source_selector_output_topic_invalid")
	}
	if frameID, _ := summary["output_frame_id"].(string); strings.TrimSpace(frameID) != "map" {
		blockers = append(blockers, "external_nav_source_selector_frame_invalid")
	}
	if childFrameID, _ := summary["output_child_frame_id"].(string); strings.TrimSpace(childFrameID) != "base_link" {
		blockers = append(blockers, "external_nav_source_selector_child_frame_invalid")
	}
	return blockers
}

func gazeboModelHoverDriftMetricBlockers(summary map[string]any, maxHorizontalDriftM float64) []string {
	return nil
}

func summarizeGazeboModelOdom(path string) (map[string]any, error) {
	return summarizeOdomHoverDrift(path, helpers.DiagnosticGazeboModelOdometryTopic, false)
}

func summarizeOdomHoverDrift(path string, topic string, usesGazeboTruthInput bool) (map[string]any, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	var stream io.Reader = file
	var decoder *zstd.Decoder
	if strings.HasSuffix(path, ".zstd") {
		decoder, err = zstd.NewReader(file)
		if err != nil {
			return nil, err
		}
		defer decoder.Close()
		stream = decoder
	}
	reader, err := mcap.NewReader(stream)
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return nil, err
	}
	type stampedGazeboOdomSample struct {
		gazeboOdomSample
		LogTimeSec float64
	}
	samples := []stampedGazeboOdomSample{}
	hoverStartSec := 0.0
	hoverEndSec := 0.0
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errorsIsEOF(err) {
			break
		}
		if err != nil {
			return nil, err
		}
		switch channel.Topic {
		case topic:
			sample, err := parseGazeboModelOdomCDR(message.Data)
			if err != nil {
				return nil, err
			}
			samples = append(samples, stampedGazeboOdomSample{
				gazeboOdomSample: sample,
				LogTimeSec:       float64(message.LogTime) / 1e9,
			})
		case "/navlab/hover/status":
			phase, err := parseHoverStatusPhaseCDR(message.Data)
			if err != nil || phase != "hover_hold" {
				continue
			}
			stampSec := float64(message.LogTime) / 1e9
			if hoverStartSec == 0 {
				hoverStartSec = stampSec
			}
			hoverEndSec = stampSec
		}
	}
	windowed := samples
	windowSource := "full_bag_fallback"
	if hoverStartSec > 0 && hoverEndSec > hoverStartSec {
		windowed = windowed[:0]
		for _, sample := range samples {
			if sample.LogTimeSec >= hoverStartSec && sample.LogTimeSec <= hoverEndSec {
				windowed = append(windowed, sample)
			}
		}
		windowSource = "hover_status_phase_hover_hold"
	}
	if len(windowed) == 0 {
		return map[string]any{
			"sample_count":            0,
			"raw_sample_count":        len(samples),
			"window_source":           windowSource,
			"source_topic":            topic,
			"uses_gazebo_truth_input": usesGazeboTruthInput,
		}, nil
	}
	first := windowed[0]
	count := 0
	maxHorizontalDrift := 0.0
	minX, maxX := math.Inf(1), math.Inf(-1)
	minY, maxY := math.Inf(1), math.Inf(-1)
	minZ, maxZ := math.Inf(1), math.Inf(-1)
	for _, sample := range windowed {
		count++
		dx := sample.X - first.X
		dy := sample.Y - first.Y
		maxHorizontalDrift = math.Max(maxHorizontalDrift, math.Hypot(dx, dy))
		minX, maxX = math.Min(minX, sample.X), math.Max(maxX, sample.X)
		minY, maxY = math.Min(minY, sample.Y), math.Max(maxY, sample.Y)
		minZ, maxZ = math.Min(minZ, sample.Z), math.Max(maxZ, sample.Z)
	}
	return map[string]any{
		"sample_count":            count,
		"raw_sample_count":        len(samples),
		"max_horizontal_drift_m":  maxHorizontalDrift,
		"x_span_m":                maxX - minX,
		"y_span_m":                maxY - minY,
		"z_span_m":                maxZ - minZ,
		"final_x_m":               windowed[len(windowed)-1].X - first.X,
		"final_y_m":               windowed[len(windowed)-1].Y - first.Y,
		"frame_id":                first.FrameID,
		"child_frame_id":          first.ChildFrameID,
		"source_topic":            topic,
		"window_source":           windowSource,
		"window_start_sec":        hoverStartSec,
		"window_end_sec":          hoverEndSec,
		"window_duration_sec":     math.Max(0, hoverEndSec-hoverStartSec),
		"uses_gazebo_truth_input": usesGazeboTruthInput,
	}, nil
}

func summarizeHoverXYAlignment(path string) (map[string]any, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	var stream io.Reader = file
	var decoder *zstd.Decoder
	if strings.HasSuffix(path, ".zstd") {
		decoder, err = zstd.NewReader(file)
		if err != nil {
			return nil, err
		}
		defer decoder.Close()
		stream = decoder
	}
	reader, err := mcap.NewReader(stream)
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return nil, err
	}
	type sourceSpec struct {
		key       string
		topic     string
		kind      string
		compareXY bool
		hardGate  bool
	}
	sources := []sourceSpec{
		{key: "gazebo_model_odometry", topic: helpers.DiagnosticGazeboModelOdometryTopic, kind: "odometry", compareXY: true, hardGate: false},
		{key: "fcu_local_position_pose", topic: "/navlab/fcu/local_position_pose", kind: "pose_stamped", compareXY: true, hardGate: true},
		{key: "external_nav_odom_candidate", topic: "/external_nav/odom_candidate", kind: "odometry", compareXY: true, hardGate: true},
		{key: "slam_odom_corrected", topic: "/slam/odom_corrected", kind: "odometry", compareXY: true, hardGate: true},
		{key: "external_nav_odom", topic: "/external_nav/odom", kind: "odometry", compareXY: true, hardGate: true},
	}
	byTopic := map[string]sourceSpec{}
	rawSamples := map[string][]timedXYSample{}
	for _, source := range sources {
		byTopic[source.topic] = source
		rawSamples[source.key] = []timedXYSample{}
	}
	hoverStartSec := 0.0
	hoverEndSec := 0.0
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errorsIsEOF(err) {
			break
		}
		if err != nil {
			return nil, err
		}
		if channel.Topic == "/navlab/hover/status" {
			phase, err := parseHoverStatusPhaseCDR(message.Data)
			if err == nil && phase == "hover_hold" {
				stampSec := float64(message.LogTime) / 1e9
				if hoverStartSec == 0 {
					hoverStartSec = stampSec
				}
				hoverEndSec = stampSec
			}
			continue
		}
		source, ok := byTopic[channel.Topic]
		if !ok {
			continue
		}
		var sample gazeboOdomSample
		switch source.kind {
		case "pose_stamped":
			sample, err = parsePoseStampedPositionCDR(message.Data)
		default:
			sample, err = parseGazeboModelOdomCDR(message.Data)
		}
		if err != nil {
			return nil, err
		}
		rawSamples[source.key] = append(rawSamples[source.key], timedXYSample{
			X:            sample.X,
			Y:            sample.Y,
			Z:            sample.Z,
			FrameID:      sample.FrameID,
			ChildFrameID: sample.ChildFrameID,
			LogTimeSec:   float64(message.LogTime) / 1e9,
		})
	}
	windowSource := "full_bag_fallback"
	sourceSummaries := map[string]any{}
	vectorByKey := map[string][2]float64{}
	for _, source := range sources {
		windowed := rawSamples[source.key]
		if hoverStartSec > 0 && hoverEndSec > hoverStartSec {
			filtered := make([]timedXYSample, 0, len(windowed))
			for _, sample := range windowed {
				if sample.LogTimeSec >= hoverStartSec && sample.LogTimeSec <= hoverEndSec {
					filtered = append(filtered, sample)
				}
			}
			windowed = filtered
			windowSource = "hover_status_phase_hover_hold"
		}
		sourceSummary := summarizeTimedXYSamples(source.topic, rawSamples[source.key], windowed, hoverStartSec, hoverEndSec, windowSource)
		comparisonVector := [2]float64{metricFloat(sourceSummary, "final_x_m"), metricFloat(sourceSummary, "final_y_m")}
		switch source.key {
		case "fcu_local_position_pose":
			// /navlab/fcu/local_position_pose mirrors MAVLink LOCAL_POSITION_NED
			// as x=north,y=east. The hover map contract used by the scan and
			// ExternalNav topics is x=west,y=north, so compare as map_x=-east,
			// map_y=north without changing any runtime control input.
			comparisonVector = [2]float64{-comparisonVector[1], comparisonVector[0]}
			sourceSummary["comparison_frame"] = "ros_map_xy_from_mavlink_local_position_ned"
			sourceSummary["comparison_final_x_m"] = comparisonVector[0]
			sourceSummary["comparison_final_y_m"] = comparisonVector[1]
		case "external_nav_odom_candidate", "external_nav_odom", "slam_odom_corrected":
			// These are ROS odometry topics. The MAVLink ExternalNav sender
			// later projects /external_nav/odom into MAV_FRAME_LOCAL_FRD, but
			// that protocol mapping must not be applied while comparing rosbag
			// topic evidence. Keep them in native ROS/map XY so pass-through
			// topics such as /external_nav/odom_candidate and /slam/odom_corrected
			// are not falsely reported as opposite directions.
			sourceSummary["comparison_frame"] = "ros_map_xy"
			sourceSummary["comparison_final_x_m"] = comparisonVector[0]
			sourceSummary["comparison_final_y_m"] = comparisonVector[1]
		default:
			sourceSummary["comparison_frame"] = "native_xy"
			sourceSummary["comparison_final_x_m"] = comparisonVector[0]
			sourceSummary["comparison_final_y_m"] = comparisonVector[1]
		}
		sourceSummaries[source.key] = sourceSummary
		vectorByKey[source.key] = comparisonVector
	}
	pairwise := map[string]any{}
	blockers := []string{}
	auditBlockers := []string{}
	comparableSources := []sourceSpec{}
	for _, source := range sources {
		if source.compareXY {
			comparableSources = append(comparableSources, source)
		}
	}
	for leftIdx := 0; leftIdx < len(comparableSources); leftIdx++ {
		for rightIdx := leftIdx + 1; rightIdx < len(comparableSources); rightIdx++ {
			left := comparableSources[leftIdx]
			right := comparableSources[rightIdx]
			leftSummary := mapFromAny(sourceSummaries[left.key])
			rightSummary := mapFromAny(sourceSummaries[right.key])
			pairKey := left.key + "__" + right.key
			pair := summarizeXYVectorPair(vectorByKey[left.key], vectorByKey[right.key], metricInt(leftSummary, "sample_count"), metricInt(rightSummary, "sample_count"))
			pairwise[pairKey] = pair
			if xyPairDirectionMismatch(pair) {
				auditBlockers = append(auditBlockers, "hover_xy_alignment_direction_mismatch:"+pairKey)
				if left.hardGate && right.hardGate {
					blockers = append(blockers, "hover_xy_evidence_disagreement")
					blockers = append(blockers, "hover_xy_alignment_direction_mismatch:"+pairKey)
				}
			}
		}
	}
	for _, source := range sources {
		if !source.compareXY || !source.hardGate {
			continue
		}
		if metricInt(mapFromAny(sourceSummaries[source.key]), "sample_count") < 2 {
			blockers = append(blockers, "hover_xy_evidence_disagreement")
			blockers = append(blockers, "hover_xy_alignment_samples_missing:"+source.key)
		}
	}
	return map[string]any{
		"ok":             len(blockers) == 0,
		"blockers":       uniqueStrings(blockers),
		"audit_blockers": uniqueStrings(auditBlockers),
		"gazebo_model_odometry_evidence": summarizeGazeboModelOdometryEvidence(
			filepath.Dir(filepath.Dir(filepath.Dir(path))),
			mapFromAny(sourceSummaries["gazebo_model_odometry"]),
			sourceSummaries,
		),
		"window_source":             windowSource,
		"window_start_sec":          hoverStartSec,
		"window_end_sec":            hoverEndSec,
		"window_duration_sec":       math.Max(0, hoverEndSec-hoverStartSec),
		"sources":                   sourceSummaries,
		"pairwise":                  pairwise,
		"uses_gazebo_truth_input":   false,
		"gazebo_source":             "review_only_not_runtime_input",
		"uses_known_map_input":      false,
		"runtime_control_unchanged": true,
	}, nil
}

func summarizeTimedXYSamples(topic string, raw []timedXYSample, windowed []timedXYSample, hoverStartSec float64, hoverEndSec float64, windowSource string) map[string]any {
	if len(windowed) == 0 {
		return map[string]any{
			"sample_count":        0,
			"raw_sample_count":    len(raw),
			"source_topic":        topic,
			"frame_id":            "",
			"child_frame_id":      "",
			"window_source":       windowSource,
			"window_start_sec":    hoverStartSec,
			"window_end_sec":      hoverEndSec,
			"window_duration_sec": math.Max(0, hoverEndSec-hoverStartSec),
		}
	}
	first := windowed[0]
	minX, maxX := math.Inf(1), math.Inf(-1)
	minY, maxY := math.Inf(1), math.Inf(-1)
	minZ, maxZ := math.Inf(1), math.Inf(-1)
	maxHorizontalDrift := 0.0
	for _, sample := range windowed {
		dx := sample.X - first.X
		dy := sample.Y - first.Y
		maxHorizontalDrift = math.Max(maxHorizontalDrift, math.Hypot(dx, dy))
		minX, maxX = math.Min(minX, sample.X), math.Max(maxX, sample.X)
		minY, maxY = math.Min(minY, sample.Y), math.Max(maxY, sample.Y)
		minZ, maxZ = math.Min(minZ, sample.Z), math.Max(maxZ, sample.Z)
	}
	final := windowed[len(windowed)-1]
	return map[string]any{
		"sample_count":           len(windowed),
		"raw_sample_count":       len(raw),
		"source_topic":           topic,
		"frame_id":               first.FrameID,
		"child_frame_id":         first.ChildFrameID,
		"window_source":          windowSource,
		"window_start_sec":       hoverStartSec,
		"window_end_sec":         hoverEndSec,
		"window_duration_sec":    math.Max(0, hoverEndSec-hoverStartSec),
		"max_horizontal_drift_m": maxHorizontalDrift,
		"x_span_m":               maxX - minX,
		"y_span_m":               maxY - minY,
		"z_span_m":               maxZ - minZ,
		"final_x_m":              final.X - first.X,
		"final_y_m":              final.Y - first.Y,
	}
}

func summarizeXYVectorPair(left [2]float64, right [2]float64, leftCount int, rightCount int) map[string]any {
	leftMag := math.Hypot(left[0], left[1])
	rightMag := math.Hypot(right[0], right[1])
	directionCosine := cosine2D(left[0], left[1], right[0], right[1])
	swappedCosine := cosine2D(left[0], left[1], right[1], right[0])
	scaleRatio := 0.0
	if leftMag > 1e-9 && rightMag > 1e-9 {
		scaleRatio = math.Min(leftMag, rightMag) / math.Max(leftMag, rightMag)
	}
	xSignAgreement := deadbandSign(left[0], 0.02) == deadbandSign(right[0], 0.02)
	ySignAgreement := deadbandSign(left[1], 0.02) == deadbandSign(right[1], 0.02)
	return map[string]any{
		"sample_count_ok":    leftCount >= 2 && rightCount >= 2,
		"direction_check_ok": leftCount >= 2 && rightCount >= 2 && leftMag >= 0.05 && rightMag >= 0.05,
		"direction_cosine":   directionCosine,
		"scale_ratio":        scaleRatio,
		"x_sign_agreement":   xSignAgreement,
		"y_sign_agreement":   ySignAgreement,
		"xy_swap_suspicious": leftMag > 0.05 && rightMag > 0.05 && swappedCosine > directionCosine+0.25,
		"swapped_cosine":     swappedCosine,
		"left_magnitude_m":   leftMag,
		"right_magnitude_m":  rightMag,
	}
}

func xyPairDirectionMismatch(pair map[string]any) bool {
	if ok, _ := pair["direction_check_ok"].(bool); !ok {
		return false
	}
	return metricFloat(pair, "direction_cosine") < 0.50
}

func summarizeGazeboModelOdometryEvidence(artifactDir string, odomSource map[string]any, sourceSummaries map[string]any) map[string]any {
	evidence := map[string]any{
		"ok":                      false,
		"artifact_dir":            artifactDir,
		"ros_topic":               helpers.DiagnosticGazeboModelOdometryTopic,
		"uses_gazebo_truth_input": false,
		"review_only":             true,
		"blockers":                []string{},
	}
	blockers := []string{}
	if len(odomSource) > 0 {
		evidence["message_frame_id"] = odomSource["frame_id"]
		evidence["message_child_frame_id"] = odomSource["child_frame_id"]
		evidence["raw_final_x_m"] = odomSource["final_x_m"]
		evidence["raw_final_y_m"] = odomSource["final_y_m"]
		evidence["raw_final_magnitude_m"] = math.Hypot(metricFloat(odomSource, "final_x_m"), metricFloat(odomSource, "final_y_m"))
	}
	bridge := parseGazeboBridgeOdometryEvidence(filepath.Join(artifactDir, "bridge_override.yaml"))
	for key, value := range bridge {
		evidence[key] = value
	}
	model := parseGazeboModelOverlayOdometryEvidence(filepath.Join(artifactDir, "model_overlay.sdf"))
	for key, value := range model {
		evidence[key] = value
	}
	if evidence["bridge_gz_topic_name"] == nil {
		blockers = append(blockers, "gazebo_model_odometry_bridge_mapping_missing")
	}
	if evidence["sdf_model_name"] == nil {
		blockers = append(blockers, "gazebo_model_odometry_sdf_model_missing")
	}
	if evidence["sdf_odom_plugin_present"] != true {
		blockers = append(blockers, "gazebo_model_odometry_plugin_missing")
	}
	if evidence["sdf_ardupilot_plugin_present"] != true {
		blockers = append(blockers, "gazebo_model_odometry_ardupilot_plugin_missing")
	}
	if projection := gazeboXYFrameProjection(evidence, odomSource, sourceSummaries); len(projection) > 0 {
		evidence["gazebo_xyz_to_ned_projection"] = projection
	}
	if frame, _ := evidence["message_frame_id"].(string); frame != "" && frame != evidence["sdf_odom_frame"] {
		blockers = append(blockers, "gazebo_model_odometry_frame_mismatch")
	}
	if child, _ := evidence["message_child_frame_id"].(string); child != "" && child != evidence["sdf_robot_base_frame"] {
		blockers = append(blockers, "gazebo_model_odometry_child_frame_mismatch")
	}
	evidence["blockers"] = blockers
	evidence["ok"] = len(blockers) == 0
	return evidence
}

func gazeboXYFrameProjection(evidence map[string]any, odomSource map[string]any, sourceSummaries map[string]any) map[string]any {
	transform, _ := evidence["sdf_gazebo_xyz_to_ned"].(string)
	if strings.TrimSpace(transform) != "0 0 0 180 0 90" || len(odomSource) == 0 {
		return nil
	}
	rawX := metricFloat(odomSource, "final_x_m")
	rawY := metricFloat(odomSource, "final_y_m")
	projectedX := rawY
	projectedY := -rawX
	projection := map[string]any{
		"source":                  "sdf_gazeboXYZToNED",
		"transform":               transform,
		"formula":                 "projected_x=raw_y, projected_y=-raw_x",
		"projected_final_x_m":     projectedX,
		"projected_final_y_m":     projectedY,
		"projected_magnitude_m":   math.Hypot(projectedX, projectedY),
		"magnitude_preserved":     math.Abs(math.Hypot(rawX, rawY)-math.Hypot(projectedX, projectedY)) < 1e-9,
		"review_only_not_runtime": true,
	}
	alignment := map[string]any{}
	for _, key := range []string{"fcu_local_position_pose", "external_nav_odom", "slam_odom_corrected"} {
		source := mapFromAny(sourceSummaries[key])
		if metricInt(source, "sample_count") < 2 {
			continue
		}
		alignment[key] = summarizeXYVectorPair(
			[2]float64{projectedX, projectedY},
			[2]float64{metricFloat(source, "final_x_m"), metricFloat(source, "final_y_m")},
			metricInt(odomSource, "sample_count"),
			metricInt(source, "sample_count"),
		)
	}
	if len(alignment) > 0 {
		projection["alignment_to_sources"] = alignment
	}
	return projection
}

func parseGazeboBridgeOdometryEvidence(path string) map[string]any {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	lines := strings.Split(string(data), "\n")
	inEntry := false
	result := map[string]any{"bridge_override_path": path}
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "- ros_topic_name:") {
			inEntry = strings.Contains(trimmed, `"gazebo/model/odometry"`) || strings.Contains(trimmed, "gazebo/model/odometry")
			if inEntry {
				result["bridge_ros_topic_name"] = strings.Trim(strings.TrimPrefix(trimmed, "- ros_topic_name:"), ` "`)
			}
			continue
		}
		if !inEntry {
			continue
		}
		switch {
		case strings.HasPrefix(trimmed, "gz_topic_name:"):
			result["bridge_gz_topic_name"] = strings.Trim(strings.TrimPrefix(trimmed, "gz_topic_name:"), ` "`)
		case strings.HasPrefix(trimmed, "ros_type_name:"):
			result["bridge_ros_type_name"] = strings.Trim(strings.TrimPrefix(trimmed, "ros_type_name:"), ` "`)
		case strings.HasPrefix(trimmed, "gz_type_name:"):
			result["bridge_gz_type_name"] = strings.Trim(strings.TrimPrefix(trimmed, "gz_type_name:"), ` "`)
		case strings.HasPrefix(trimmed, "direction:"):
			result["bridge_direction"] = strings.TrimSpace(strings.TrimPrefix(trimmed, "direction:"))
		}
	}
	if len(result) == 1 {
		return nil
	}
	return result
}

func parseGazeboModelOverlayOdometryEvidence(path string) map[string]any {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	text := string(data)
	result := map[string]any{
		"sdf_path":                     path,
		"sdf_model_name":               firstRegexSubmatch(text, `<model\s+name="([^"]+)"`),
		"sdf_odom_plugin_present":      strings.Contains(text, `gz-sim-odometry-publisher-system`) || strings.Contains(text, `OdometryPublisher`),
		"sdf_ardupilot_plugin_present": strings.Contains(text, `name="ArduPilotPlugin"`) || strings.Contains(text, `filename="ArduPilotPlugin"`),
		"sdf_odom_frame":               firstRegexSubmatch(text, `<odom_frame>\s*([^<\s]+)\s*</odom_frame>`),
		"sdf_robot_base_frame":         firstRegexSubmatch(text, `<robot_base_frame>\s*([^<\s]+)\s*</robot_base_frame>`),
		"sdf_imu_name":                 firstRegexSubmatch(text, `<imuName>\s*([^<\s]+)\s*</imuName>`),
		"sdf_model_xyz_to_airplane":    strings.TrimSpace(firstRegexSubmatch(text, `<modelXYZToAirplaneXForwardZDown[^>]*>\s*([^<]+)\s*</modelXYZToAirplaneXForwardZDown>`)),
		"sdf_gazebo_xyz_to_ned":        strings.TrimSpace(firstRegexSubmatch(text, `<gazeboXYZToNED[^>]*>\s*([^<]+)\s*</gazeboXYZToNED>`)),
	}
	if modelName, _ := result["sdf_model_name"].(string); modelName != "" {
		result["expected_bridge_gz_topic_name"] = "/model/" + modelName + "/odometry"
	}
	return result
}

func firstRegexSubmatch(text string, pattern string) string {
	match := regexp.MustCompile(pattern).FindStringSubmatch(text)
	if len(match) < 2 {
		return ""
	}
	return match[1]
}

func summarizeScanReferenceHoverDrift(path string) (map[string]any, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	var stream io.Reader = file
	var decoder *zstd.Decoder
	if strings.HasSuffix(path, ".zstd") {
		decoder, err = zstd.NewReader(file)
		if err != nil {
			return nil, err
		}
		defer decoder.Close()
		stream = decoder
	}
	reader, err := mcap.NewReader(stream)
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return nil, err
	}
	scans := []scanDriftSample{}
	hoverStartSec := 0.0
	hoverEndSec := 0.0
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errorsIsEOF(err) {
			break
		}
		if err != nil {
			return nil, err
		}
		switch channel.Topic {
		case "/scan":
			sample, err := parseLaserScanDriftCDR(message.Data)
			if err != nil {
				return nil, err
			}
			sample.LogTimeSec = float64(message.LogTime) / 1e9
			scans = append(scans, sample)
		case "/navlab/hover/status":
			phase, err := parseHoverStatusPhaseCDR(message.Data)
			if err != nil || phase != "hover_hold" {
				continue
			}
			stampSec := float64(message.LogTime) / 1e9
			if hoverStartSec == 0 {
				hoverStartSec = stampSec
			}
			hoverEndSec = stampSec
		}
	}
	windowed := scans
	windowSource := "full_bag_fallback"
	if hoverStartSec > 0 && hoverEndSec > hoverStartSec {
		windowed = windowed[:0]
		for _, sample := range scans {
			if sample.LogTimeSec >= hoverStartSec && sample.LogTimeSec <= hoverEndSec {
				windowed = append(windowed, sample)
			}
		}
		windowSource = "hover_status_phase_hover_hold"
	}
	if len(windowed) < 2 {
		return map[string]any{
			"sample_count":            len(windowed),
			"raw_sample_count":        len(scans),
			"window_source":           windowSource,
			"source_topic":            "/scan",
			"uses_gazebo_truth_input": false,
			"uses_known_map_input":    false,
		}, nil
	}
	reference := windowed[0]
	count := 0
	maxHorizontalDrift := 0.0
	minX, maxX := math.Inf(1), math.Inf(-1)
	minY, maxY := math.Inf(1), math.Inf(-1)
	minValid, maxValid := math.MaxInt, 0
	finalX, finalY := 0.0, 0.0
	for _, sample := range windowed {
		dx, dy, valid := estimateScanReferenceTranslation(reference, sample)
		if valid < 4 {
			continue
		}
		count++
		finalX, finalY = dx, dy
		maxHorizontalDrift = math.Max(maxHorizontalDrift, math.Hypot(dx, dy))
		minX, maxX = math.Min(minX, dx), math.Max(maxX, dx)
		minY, maxY = math.Min(minY, dy), math.Max(maxY, dy)
		minValid = min(minValid, valid)
		maxValid = max(maxValid, valid)
	}
	if count == 0 {
		return map[string]any{
			"sample_count":            0,
			"raw_sample_count":        len(scans),
			"window_source":           windowSource,
			"source_topic":            "/scan",
			"reference_source":        "first_hover_hold_scan",
			"uses_gazebo_truth_input": false,
			"uses_known_map_input":    false,
		}, nil
	}
	return map[string]any{
		"sample_count":            count,
		"raw_sample_count":        len(scans),
		"window_source":           windowSource,
		"window_start_sec":        hoverStartSec,
		"window_end_sec":          hoverEndSec,
		"window_duration_sec":     math.Max(0, hoverEndSec-hoverStartSec),
		"source_topic":            "/scan",
		"reference_source":        "first_hover_hold_scan",
		"estimator":               "range_residual_least_squares",
		"max_horizontal_drift_m":  maxHorizontalDrift,
		"x_span_m":                maxX - minX,
		"y_span_m":                maxY - minY,
		"final_x_m":               finalX,
		"final_y_m":               finalY,
		"min_valid_beams":         minValid,
		"max_valid_beams":         maxValid,
		"uses_gazebo_truth_input": false,
		"uses_known_map_input":    false,
	}, nil
}

func summarizeScanReferenceStatusHoverWindow(path string) (map[string]any, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	var stream io.Reader = file
	var decoder *zstd.Decoder
	if strings.HasSuffix(path, ".zstd") {
		decoder, err = zstd.NewReader(file)
		if err != nil {
			return nil, err
		}
		defer decoder.Close()
		stream = decoder
	}
	reader, err := mcap.NewReader(stream)
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return nil, err
	}
	samples := []scanReferenceStatusSample{}
	gazeboSamples := []timedGazeboOdomSample{}
	hoverStartSec := 0.0
	hoverEndSec := 0.0
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errorsIsEOF(err) {
			break
		}
		if err != nil {
			return nil, err
		}
		switch channel.Topic {
		case "/navlab/hover/status":
			phase, err := parseHoverStatusPhaseCDR(message.Data)
			if err != nil || phase != "hover_hold" {
				continue
			}
			stampSec := float64(message.LogTime) / 1e9
			if hoverStartSec == 0 {
				hoverStartSec = stampSec
			}
			hoverEndSec = stampSec
		case helpers.DiagnosticGazeboModelOdometryTopic:
			sample, err := parseGazeboModelOdomCDR(message.Data)
			if err != nil {
				return nil, err
			}
			gazeboSamples = append(gazeboSamples, timedGazeboOdomSample{
				gazeboOdomSample: sample,
				LogTimeSec:       float64(message.LogTime) / 1e9,
			})
		case "/navlab/scan_reference_drift/status":
			payload, err := parseStdStringCDR(message.Data)
			if err != nil {
				return nil, err
			}
			status := map[string]any{}
			if err := json.Unmarshal([]byte(payload), &status); err != nil {
				return nil, err
			}
			eligibility, _ := status["correction_eligibility"].(map[string]any)
			intent, _ := status["correction_intent"].(map[string]any)
			allowedAxes, _ := eligibility["allowed_axes"].([]any)
			blockers, _ := status["blockers"].([]any)
			intentAxes, _ := intent["axes"].([]any)
			intentBlockers, _ := intent["blockers"].([]any)
			phase4BConsistency, _ := status["phase4b_consistency"].(map[string]any)
			phase4BSource, _ := status["phase4b_consistency_source"].(string)
			samples = append(samples, scanReferenceStatusSample{
				LogTimeSec:          float64(message.LogTime) / 1e9,
				QualityGood:         anyBool(status["quality_good"]),
				CorrectionAllowed:   anyBool(eligibility["correction_allowed"]),
				ResidualRMS:         anyFloat(status["residual_rms_m"]),
				RawResidualRMS:      anyFloat(status["raw_residual_rms_m"]),
				InlierRatio:         anyFloat(status["inlier_ratio"]),
				AllowedAxes:         allowedAxes,
				Blockers:            blockers,
				IntentActive:        anyBool(intent["active"]),
				IntentAxes:          intentAxes,
				IntentMagnitude:     anyFloat(intent["correction_magnitude_m"]),
				IntentX:             anyFloat(intent["correction_x_m"]),
				IntentY:             anyFloat(intent["correction_y_m"]),
				IntentMaxCorrection: anyFloat(intent["max_correction_m"]),
				IntentBlockers:      intentBlockers,
				Phase4BOK:           anyBool(status["phase4b_consistency_ok"]),
				Phase4BSource:       phase4BSource,
				Phase4BConsistency:  phase4BConsistency,
			})
		}
	}
	windowed := samples
	windowSource := "full_bag_fallback"
	if hoverStartSec > 0 && hoverEndSec > hoverStartSec {
		windowed = windowed[:0]
		for _, sample := range samples {
			if sample.LogTimeSec >= hoverStartSec && sample.LogTimeSec <= hoverEndSec {
				windowed = append(windowed, sample)
			}
		}
		windowSource = "hover_status_phase_hover_hold"
	}
	if len(windowed) == 0 {
		return map[string]any{
			"status_sample_count":     0,
			"raw_status_sample_count": len(samples),
			"status_window_source":    windowSource,
		}, nil
	}
	qualityGoodCount := 0
	correctionAllowedCount := 0
	maxConsecutiveAllowed := 0
	currentConsecutiveAllowed := 0
	intentActiveCount := 0
	maxConsecutiveIntentActive := 0
	currentConsecutiveIntentActive := 0
	firstAllowedOffsetSec := 0.0
	lastAllowedOffsetSec := 0.0
	firstIntentActiveOffsetSec := 0.0
	lastIntentActiveOffsetSec := 0.0
	residuals := make([]float64, 0, len(windowed))
	rawResiduals := make([]float64, 0, len(windowed))
	inlierRatios := make([]float64, 0, len(windowed))
	intentMagnitudes := make([]float64, 0, len(windowed))
	for _, sample := range windowed {
		if sample.QualityGood {
			qualityGoodCount++
		}
		if sample.CorrectionAllowed {
			correctionAllowedCount++
			currentConsecutiveAllowed++
			if firstAllowedOffsetSec == 0 {
				firstAllowedOffsetSec = sample.LogTimeSec - hoverStartSec
			}
			lastAllowedOffsetSec = sample.LogTimeSec - hoverStartSec
		} else {
			maxConsecutiveAllowed = max(maxConsecutiveAllowed, currentConsecutiveAllowed)
			currentConsecutiveAllowed = 0
		}
		if sample.IntentActive {
			intentActiveCount++
			currentConsecutiveIntentActive++
			if firstIntentActiveOffsetSec == 0 {
				firstIntentActiveOffsetSec = sample.LogTimeSec - hoverStartSec
			}
			lastIntentActiveOffsetSec = sample.LogTimeSec - hoverStartSec
		} else {
			maxConsecutiveIntentActive = max(maxConsecutiveIntentActive, currentConsecutiveIntentActive)
			currentConsecutiveIntentActive = 0
		}
		residuals = append(residuals, sample.ResidualRMS)
		rawResiduals = append(rawResiduals, sample.RawResidualRMS)
		inlierRatios = append(inlierRatios, sample.InlierRatio)
		intentMagnitudes = append(intentMagnitudes, sample.IntentMagnitude)
	}
	maxConsecutiveAllowed = max(maxConsecutiveAllowed, currentConsecutiveAllowed)
	maxConsecutiveIntentActive = max(maxConsecutiveIntentActive, currentConsecutiveIntentActive)
	last := windowed[len(windowed)-1]
	intentConsistency := summarizeIntentConsistency(windowed, gazeboSamples, hoverStartSec, hoverEndSec)
	return map[string]any{
		"status_sample_count":                                    len(windowed),
		"raw_status_sample_count":                                len(samples),
		"status_window_source":                                   windowSource,
		"status_window_start_sec":                                hoverStartSec,
		"status_window_end_sec":                                  hoverEndSec,
		"status_window_duration_sec":                             math.Max(0, hoverEndSec-hoverStartSec),
		"hover_window_quality_good_count":                        qualityGoodCount,
		"hover_window_quality_good_ratio":                        float64(qualityGoodCount) / float64(len(windowed)),
		"hover_window_correction_allowed_count":                  correctionAllowedCount,
		"hover_window_correction_allowed_ratio":                  float64(correctionAllowedCount) / float64(len(windowed)),
		"hover_window_max_consecutive_correction_allowed":        maxConsecutiveAllowed,
		"hover_window_first_correction_allowed_offset_sec":       firstAllowedOffsetSec,
		"hover_window_last_correction_allowed_offset_sec":        lastAllowedOffsetSec,
		"hover_window_residual_rms":                              numberStats(residuals),
		"hover_window_raw_residual_rms":                          numberStats(rawResiduals),
		"hover_window_inlier_ratio":                              numberStats(inlierRatios),
		"hover_window_last_correction_allowed":                   last.CorrectionAllowed,
		"hover_window_last_quality_good":                         last.QualityGood,
		"hover_window_last_allowed_axes":                         last.AllowedAxes,
		"hover_window_last_blockers":                             last.Blockers,
		"hover_window_correction_intent_active_count":            intentActiveCount,
		"hover_window_correction_intent_active_ratio":            float64(intentActiveCount) / float64(len(windowed)),
		"hover_window_max_consecutive_correction_intent_active":  maxConsecutiveIntentActive,
		"hover_window_first_correction_intent_active_offset_sec": firstIntentActiveOffsetSec,
		"hover_window_last_correction_intent_active_offset_sec":  lastIntentActiveOffsetSec,
		"hover_window_correction_intent_magnitude":               numberStats(intentMagnitudes),
		"hover_window_last_correction_intent_active":             last.IntentActive,
		"hover_window_last_correction_intent_axes":               last.IntentAxes,
		"hover_window_last_correction_intent_x_m":                last.IntentX,
		"hover_window_last_correction_intent_y_m":                last.IntentY,
		"hover_window_last_correction_intent_magnitude_m":        last.IntentMagnitude,
		"hover_window_last_correction_intent_blockers":           last.IntentBlockers,
		"hover_window_last_phase4b_consistency_ok":               last.Phase4BOK,
		"hover_window_last_phase4b_consistency_source":           last.Phase4BSource,
		"hover_window_last_phase4b_consistency":                  last.Phase4BConsistency,
		"hover_window_correction_intent_consistency":             intentConsistency,
	}, nil
}

func summarizeScanReferenceCorrectionStatusHoverWindow(path string) (map[string]any, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	var stream io.Reader = file
	var decoder *zstd.Decoder
	if strings.HasSuffix(path, ".zstd") {
		decoder, err = zstd.NewReader(file)
		if err != nil {
			return nil, err
		}
		defer decoder.Close()
		stream = decoder
	}
	reader, err := mcap.NewReader(stream)
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return nil, err
	}
	samples := []scanReferenceCorrectionStatusSample{}
	hoverStartSec := 0.0
	hoverEndSec := 0.0
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errorsIsEOF(err) {
			break
		}
		if err != nil {
			return nil, err
		}
		switch channel.Topic {
		case "/navlab/hover/status":
			phase, err := parseHoverStatusPhaseCDR(message.Data)
			if err != nil || phase != "hover_hold" {
				continue
			}
			stampSec := float64(message.LogTime) / 1e9
			if hoverStartSec == 0 {
				hoverStartSec = stampSec
			}
			hoverEndSec = stampSec
		case "/navlab/scan_reference_correction/status":
			payload, err := parseStdStringCDR(message.Data)
			if err != nil {
				return nil, err
			}
			status := map[string]any{}
			if err := json.Unmarshal([]byte(payload), &status); err != nil {
				return nil, err
			}
			samples = append(samples, scanReferenceCorrectionStatusSample{
				LogTimeSec:        float64(message.LogTime) / 1e9,
				Status:            status,
				CorrectionApplied: anyBool(status["correction_applied"]),
			})
		}
	}
	windowed := samples
	windowSource := "full_bag_fallback"
	if hoverStartSec > 0 && hoverEndSec > hoverStartSec {
		windowed = windowed[:0]
		for _, sample := range samples {
			if sample.LogTimeSec >= hoverStartSec && sample.LogTimeSec <= hoverEndSec {
				windowed = append(windowed, sample)
			}
		}
		windowSource = "hover_status_phase_hover_hold"
	}
	if len(windowed) == 0 {
		return map[string]any{
			"correction_status_sample_count":     0,
			"raw_correction_status_sample_count": len(samples),
			"correction_status_window_source":    windowSource,
		}, nil
	}
	appliedCount := 0
	appliedWithoutPhase4BCount := 0
	appliedWithoutRuntimeConsistencyCount := 0
	for _, sample := range windowed {
		if sample.CorrectionApplied {
			appliedCount++
			if phase4BOK, _ := sample.Status["phase4b_consistency_ok"].(bool); !phase4BOK {
				appliedWithoutPhase4BCount++
			}
			if runtimeOK, _ := sample.Status["runtime_consistency_ok"].(bool); !runtimeOK {
				appliedWithoutRuntimeConsistencyCount++
			}
		}
	}
	last := windowed[len(windowed)-1].Status
	statusSummary := subsetMap(last,
		"ready",
		"state",
		"correction_enabled",
		"correction_applied",
		"fail_closed",
		"blockers",
		"hover_phase",
		"input_odom_topic",
		"scan_reference_status_topic",
		"output_odom_topic",
		"input_odom_qos_reliability",
		"output_odom_qos_reliability",
		"status_age_ms",
		"published_count",
		"corrected_count",
		"passthrough_count",
		"runtime_consistency_sample_count",
		"runtime_consistency_ok",
		"phase4b_consistency_ok",
		"phase4b_consistency_source",
		"measurement_delta_x_m",
		"measurement_delta_y_m",
		"measurement_delta_magnitude_m",
		"source_intent_x_m",
		"source_intent_y_m",
		"source_intent_magnitude_m",
		"axes",
		"allowed_axes",
		"blocked_axes",
		"axis_blockers",
		"max_correction_m",
		"max_measurement_delta_m",
		"max_correction_step_m",
		"uses_gazebo_truth_input",
		"uses_known_map_input",
		"writes_external_nav_odom",
		"external_nav_input_topic",
	)
	windowSummary := map[string]any{
		"correction_status_sample_count":                         len(windowed),
		"raw_correction_status_sample_count":                     len(samples),
		"correction_status_window_source":                        windowSource,
		"correction_status_window_start_sec":                     hoverStartSec,
		"correction_status_window_end_sec":                       hoverEndSec,
		"correction_status_window_duration_sec":                  math.Max(0, hoverEndSec-hoverStartSec),
		"hover_window_correction_applied_count":                  appliedCount,
		"hover_window_correction_applied_ratio":                  float64(appliedCount) / float64(len(windowed)),
		"hover_window_applied_without_phase4b_count":             appliedWithoutPhase4BCount,
		"hover_window_applied_without_runtime_consistency_count": appliedWithoutRuntimeConsistencyCount,
		"hover_window_last_correction_applied":                   windowed[len(windowed)-1].CorrectionApplied,
		"hover_window_last_correction_status_time":               windowed[len(windowed)-1].LogTimeSec,
	}
	return mergeMaps(statusSummary, windowSummary), nil
}

func summarizeLatestJSONStatusFromHoverRosbag(artifactDir string, topic string, keys ...string) (map[string]any, string) {
	for _, name := range []string{"hover_rosbag_0.mcap.zstd", "hover_rosbag_0.mcap"} {
		path := filepath.Join(artifactDir, "rosbag", "hover_rosbag", name)
		metrics, err := summarizeLatestJSONStatusFromRosbag(path, topic, keys...)
		if err == nil && metrics != nil {
			return metrics, filepath.ToSlash(filepath.Join("rosbag", "hover_rosbag", name))
		}
	}
	return nil, ""
}

func summarizeLatestJSONStatusFromRosbag(path string, topic string, keys ...string) (map[string]any, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	var stream io.Reader = file
	var decoder *zstd.Decoder
	if strings.HasSuffix(path, ".zstd") {
		decoder, err = zstd.NewReader(file)
		if err != nil {
			return nil, err
		}
		defer decoder.Close()
		stream = decoder
	}
	reader, err := mcap.NewReader(stream)
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return nil, err
	}
	var last map[string]any
	lastLogTimeSec := 0.0
	count := 0
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errorsIsEOF(err) {
			break
		}
		if err != nil {
			return nil, err
		}
		if channel.Topic != topic {
			continue
		}
		payload, err := parseStdStringCDR(message.Data)
		if err != nil {
			return nil, err
		}
		status := map[string]any{}
		if err := json.Unmarshal([]byte(payload), &status); err != nil {
			return nil, err
		}
		last = status
		lastLogTimeSec = float64(message.LogTime) / 1e9
		count++
	}
	if count == 0 || last == nil {
		return nil, nil
	}
	summary := subsetMap(last, keys...)
	summary["status_sample_count"] = count
	summary["last_status_log_time_sec"] = lastLogTimeSec
	summary["status_source_topic"] = topic
	summary["status_source"] = "rosbag_latest_json_status"
	return summary, nil
}

func summarizeIntentConsistency(samples []scanReferenceStatusSample, gazeboSamples []timedGazeboOdomSample, hoverStartSec float64, hoverEndSec float64) map[string]any {
	windowedGazebo := make([]timedGazeboOdomSample, 0, len(gazeboSamples))
	for _, sample := range gazeboSamples {
		if hoverStartSec > 0 && hoverEndSec > hoverStartSec && (sample.LogTimeSec < hoverStartSec || sample.LogTimeSec > hoverEndSec) {
			continue
		}
		windowedGazebo = append(windowedGazebo, sample)
	}
	activeSamples := make([]scanReferenceStatusSample, 0, len(samples))
	for _, sample := range samples {
		if sample.IntentActive {
			activeSamples = append(activeSamples, sample)
		}
	}
	blockers := []string{}
	if len(windowedGazebo) < 2 {
		blockers = append(blockers, "intent_consistency_gazebo_review_samples_low")
	}
	if len(activeSamples) < 5 {
		blockers = append(blockers, "intent_consistency_active_samples_low")
	}
	if len(blockers) > 0 {
		return map[string]any{
			"ok":                      false,
			"blockers":                blockers,
			"uses_gazebo_truth_input": false,
			"gazebo_source":           "review_only_not_runtime_input",
			"active_sample_count":     len(activeSamples),
			"gazebo_sample_count":     len(windowedGazebo),
		}
	}

	reference := windowedGazebo[0]
	counterDriftCosines := []float64{}
	intentDirectionCosines := []float64{}
	intentMagnitudes := []float64{}
	activeWithDrift := 0
	opposesDriftCount := 0
	saturationCount := 0
	xSigns := []int{}
	ySigns := []int{}
	previousIntentX := 0.0
	previousIntentY := 0.0
	previousIntentNorm := 0.0
	for _, sample := range activeSamples {
		gazebo := nearestGazeboOdom(windowedGazebo, sample.LogTimeSec)
		driftX := gazebo.X - reference.X
		driftY := gazebo.Y - reference.Y
		intentNorm := math.Hypot(sample.IntentX, sample.IntentY)
		driftNorm := math.Hypot(driftX, driftY)
		if intentNorm > 1e-9 {
			intentMagnitudes = append(intentMagnitudes, intentNorm)
			if sample.IntentMaxCorrection > 0 && intentNorm >= sample.IntentMaxCorrection*0.98 {
				saturationCount++
			}
			if sign := deadbandSign(sample.IntentX, 0.02); sign != 0 {
				xSigns = append(xSigns, sign)
			}
			if sign := deadbandSign(sample.IntentY, 0.02); sign != 0 {
				ySigns = append(ySigns, sign)
			}
			if previousIntentNorm > 1e-9 {
				intentDirectionCosines = append(intentDirectionCosines, cosine2D(previousIntentX, previousIntentY, sample.IntentX, sample.IntentY))
			}
			previousIntentX = sample.IntentX
			previousIntentY = sample.IntentY
			previousIntentNorm = intentNorm
		}
		if intentNorm <= 1e-9 || driftNorm <= 0.05 {
			continue
		}
		activeWithDrift++
		cosine := cosine2D(sample.IntentX, sample.IntentY, -driftX, -driftY)
		counterDriftCosines = append(counterDriftCosines, cosine)
		if cosine >= 0.70 {
			opposesDriftCount++
		}
	}
	if activeWithDrift == 0 {
		blockers = append(blockers, "intent_consistency_drift_observation_low")
	}
	counterStats := numberStats(counterDriftCosines)
	directionStats := numberStats(intentDirectionCosines)
	intentMagnitudeStats := numberStats(intentMagnitudes)
	xFlips := signFlipsInt(xSigns)
	yFlips := signFlipsInt(ySigns)
	opposesRatio := 0.0
	if activeWithDrift > 0 {
		opposesRatio = float64(opposesDriftCount) / float64(activeWithDrift)
	}
	saturationRatio := 0.0
	if len(activeSamples) > 0 {
		saturationRatio = float64(saturationCount) / float64(len(activeSamples))
	}
	minCounterCosine := metricFloat(counterStats, "min")
	minIntentDirectionCosine := metricFloat(directionStats, "min")
	if activeWithDrift > 0 && minCounterCosine < 0.70 {
		blockers = append(blockers, "intent_consistency_counter_drift_direction_low")
	}
	if activeWithDrift > 0 && opposesRatio < 0.80 {
		blockers = append(blockers, "intent_consistency_counter_drift_ratio_low")
	}
	if len(intentDirectionCosines) > 0 && minIntentDirectionCosine < 0.70 {
		blockers = append(blockers, "intent_consistency_intent_direction_unstable")
	}
	if xFlips > 0 {
		blockers = append(blockers, "intent_consistency_x_sign_flips")
	}
	if yFlips > 0 {
		blockers = append(blockers, "intent_consistency_y_sign_flips")
	}
	if saturationRatio > 0.95 {
		blockers = append(blockers, "intent_consistency_saturation_ratio_high")
	}
	return map[string]any{
		"ok":                             len(blockers) == 0,
		"blockers":                       blockers,
		"uses_gazebo_truth_input":        false,
		"gazebo_source":                  "review_only_not_runtime_input",
		"active_sample_count":            len(activeSamples),
		"gazebo_sample_count":            len(windowedGazebo),
		"active_with_drift_sample_count": activeWithDrift,
		"counter_drift_cosine":           counterStats,
		"counter_drift_opposes_count":    opposesDriftCount,
		"counter_drift_opposes_ratio":    opposesRatio,
		"intent_direction_cosine":        directionStats,
		"intent_x_sign_flips":            xFlips,
		"intent_y_sign_flips":            yFlips,
		"intent_saturation_count":        saturationCount,
		"intent_saturation_ratio":        saturationRatio,
		"intent_magnitude":               intentMagnitudeStats,
		"min_counter_drift_cosine":       minCounterCosine,
		"min_intent_direction_cosine":    minIntentDirectionCosine,
		"max_allowed_saturation_ratio":   0.95,
		"min_allowed_counter_cosine":     0.70,
		"min_allowed_counter_ratio":      0.80,
		"min_allowed_direction_cosine":   0.70,
	}
}

func nearestGazeboOdom(samples []timedGazeboOdomSample, targetSec float64) timedGazeboOdomSample {
	if len(samples) == 0 {
		return timedGazeboOdomSample{}
	}
	best := samples[0]
	bestDelta := math.Abs(samples[0].LogTimeSec - targetSec)
	for _, sample := range samples[1:] {
		if delta := math.Abs(sample.LogTimeSec - targetSec); delta < bestDelta {
			best = sample
			bestDelta = delta
		}
	}
	return best
}

func cosine2D(ax float64, ay float64, bx float64, by float64) float64 {
	an := math.Hypot(ax, ay)
	bn := math.Hypot(bx, by)
	if an <= 1e-9 || bn <= 1e-9 {
		return 0
	}
	return (ax*bx + ay*by) / (an * bn)
}

func deadbandSign(value float64, deadband float64) int {
	if value > deadband {
		return 1
	}
	if value < -deadband {
		return -1
	}
	return 0
}

func signFlipsInt(signs []int) int {
	flips := 0
	for idx := 1; idx < len(signs); idx++ {
		if signs[idx] != signs[idx-1] {
			flips++
		}
	}
	return flips
}

func estimateScanReferenceTranslation(reference scanDriftSample, current scanDriftSample) (float64, float64, int) {
	beamCount := min(len(reference.Ranges), len(current.Ranges))
	a00, a01, a11 := 0.0, 0.0, 0.0
	b0, b1 := 0.0, 0.0
	valid := 0
	for idx := 0; idx < beamCount; idx++ {
		refRange := reference.Ranges[idx]
		curRange := current.Ranges[idx]
		if !scanRangeValid(refRange, reference.RangeMin, reference.RangeMax) ||
			!scanRangeValid(curRange, current.RangeMin, current.RangeMax) {
			continue
		}
		deltaRange := curRange - refRange
		if math.Abs(deltaRange) > 3.0 {
			continue
		}
		theta := reference.AngleMin + float64(idx)*reference.AngleIncrement
		ux := math.Cos(theta)
		uy := math.Sin(theta)
		// For small translations, range change is approximately -u dot t.
		a00 += ux * ux
		a01 += ux * uy
		a11 += uy * uy
		b0 += -ux * deltaRange
		b1 += -uy * deltaRange
		valid++
	}
	determinant := a00*a11 - a01*a01
	if math.Abs(determinant) < 1e-9 {
		return 0, 0, valid
	}
	x := (b0*a11 - b1*a01) / determinant
	y := (a00*b1 - a01*b0) / determinant
	return x, y, valid
}

func scanRangeValid(value float64, rangeMin float64, rangeMax float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0) && value >= rangeMin && value <= rangeMax
}

type gateCDRCursor struct {
	data []byte
	off  int
}

func parseGazeboModelOdomCDR(data []byte) (gazeboOdomSample, error) {
	cursor := gateCDRCursor{data: data}
	if err := cursor.skip(4); err != nil {
		return gazeboOdomSample{}, err
	}
	if _, err := cursor.int32(); err != nil {
		return gazeboOdomSample{}, err
	}
	if _, err := cursor.uint32(); err != nil {
		return gazeboOdomSample{}, err
	}
	frameID, err := cursor.stringValue()
	if err != nil {
		return gazeboOdomSample{}, err
	}
	childFrameID, err := cursor.stringValue()
	if err != nil {
		return gazeboOdomSample{}, err
	}
	x, err := cursor.float64()
	if err != nil {
		return gazeboOdomSample{}, err
	}
	y, err := cursor.float64()
	if err != nil {
		return gazeboOdomSample{}, err
	}
	z, err := cursor.float64()
	if err != nil {
		return gazeboOdomSample{}, err
	}
	return gazeboOdomSample{X: x, Y: y, Z: z, FrameID: frameID, ChildFrameID: childFrameID}, nil
}

func parsePoseStampedPositionCDR(data []byte) (gazeboOdomSample, error) {
	cursor := gateCDRCursor{data: data}
	if err := cursor.skip(4); err != nil {
		return gazeboOdomSample{}, err
	}
	if _, err := cursor.int32(); err != nil {
		return gazeboOdomSample{}, err
	}
	if _, err := cursor.uint32(); err != nil {
		return gazeboOdomSample{}, err
	}
	frameID, err := cursor.stringValue()
	if err != nil {
		return gazeboOdomSample{}, err
	}
	x, err := cursor.float64()
	if err != nil {
		return gazeboOdomSample{}, err
	}
	y, err := cursor.float64()
	if err != nil {
		return gazeboOdomSample{}, err
	}
	z, err := cursor.float64()
	if err != nil {
		return gazeboOdomSample{}, err
	}
	return gazeboOdomSample{X: x, Y: y, Z: z, FrameID: frameID}, nil
}

func parseLaserScanDriftCDR(data []byte) (scanDriftSample, error) {
	cursor := gateCDRCursor{data: data}
	if err := cursor.skip(4); err != nil {
		return scanDriftSample{}, err
	}
	if _, err := cursor.int32(); err != nil {
		return scanDriftSample{}, err
	}
	if _, err := cursor.uint32(); err != nil {
		return scanDriftSample{}, err
	}
	if err := cursor.string(); err != nil {
		return scanDriftSample{}, err
	}
	angleMin, err := cursor.float32()
	if err != nil {
		return scanDriftSample{}, err
	}
	if _, err := cursor.float32(); err != nil {
		return scanDriftSample{}, err
	}
	angleIncrement, err := cursor.float32()
	if err != nil {
		return scanDriftSample{}, err
	}
	if _, err := cursor.float32(); err != nil {
		return scanDriftSample{}, err
	}
	if _, err := cursor.float32(); err != nil {
		return scanDriftSample{}, err
	}
	rangeMin, err := cursor.float32()
	if err != nil {
		return scanDriftSample{}, err
	}
	rangeMax, err := cursor.float32()
	if err != nil {
		return scanDriftSample{}, err
	}
	rangeCount, err := cursor.uint32()
	if err != nil {
		return scanDriftSample{}, err
	}
	ranges := make([]float64, 0, rangeCount)
	for idx := uint32(0); idx < rangeCount; idx++ {
		value, err := cursor.float32()
		if err != nil {
			return scanDriftSample{}, err
		}
		ranges = append(ranges, float64(value))
	}
	return scanDriftSample{
		AngleMin:       float64(angleMin),
		AngleIncrement: float64(angleIncrement),
		RangeMin:       float64(rangeMin),
		RangeMax:       float64(rangeMax),
		Ranges:         ranges,
	}, nil
}

func parseHoverStatusPhaseCDR(data []byte) (string, error) {
	payload, err := parseStdStringCDR(data)
	if err != nil {
		return "", err
	}
	var status map[string]any
	if err := json.Unmarshal([]byte(payload), &status); err != nil {
		return "", err
	}
	phase, _ := status["phase"].(string)
	return phase, nil
}

func parseStdStringCDR(data []byte) (string, error) {
	cursor := gateCDRCursor{data: data}
	if err := cursor.skip(4); err != nil {
		return "", err
	}
	return cursor.stringValue()
}

func numberStats(values []float64) map[string]any {
	if len(values) == 0 {
		return map[string]any{"min": 0.0, "avg": 0.0, "max": 0.0}
	}
	sorted := append([]float64{}, values...)
	sort.Float64s(sorted)
	sum := 0.0
	for _, value := range sorted {
		sum += value
	}
	return map[string]any{
		"min": sorted[0],
		"avg": sum / float64(len(sorted)),
		"max": sorted[len(sorted)-1],
	}
}

func anyFloat(value any) float64 {
	switch typed := value.(type) {
	case float64:
		return typed
	case float32:
		return float64(typed)
	case int:
		return float64(typed)
	case int64:
		return float64(typed)
	case json.Number:
		parsed, _ := typed.Float64()
		return parsed
	default:
		return 0.0
	}
}

func anyBool(value any) bool {
	typed, _ := value.(bool)
	return typed
}

func (cursor *gateCDRCursor) align(size int) {
	if size <= 1 {
		return
	}
	remainder := (cursor.off - 4) % size
	if remainder < 0 {
		remainder += size
	}
	if remainder != 0 {
		cursor.off += size - remainder
	}
}

func (cursor *gateCDRCursor) skip(size int) error {
	if cursor.off+size > len(cursor.data) {
		return io.ErrUnexpectedEOF
	}
	cursor.off += size
	return nil
}

func (cursor *gateCDRCursor) uint32() (uint32, error) {
	cursor.align(4)
	if cursor.off+4 > len(cursor.data) {
		return 0, io.ErrUnexpectedEOF
	}
	value := binary.LittleEndian.Uint32(cursor.data[cursor.off : cursor.off+4])
	cursor.off += 4
	return value, nil
}

func (cursor *gateCDRCursor) int32() (int32, error) {
	value, err := cursor.uint32()
	return int32(value), err
}

func (cursor *gateCDRCursor) float64() (float64, error) {
	cursor.align(8)
	if cursor.off+8 > len(cursor.data) {
		return 0, io.ErrUnexpectedEOF
	}
	value := math.Float64frombits(binary.LittleEndian.Uint64(cursor.data[cursor.off : cursor.off+8]))
	cursor.off += 8
	return value, nil
}

func (cursor *gateCDRCursor) float32() (float32, error) {
	cursor.align(4)
	if cursor.off+4 > len(cursor.data) {
		return 0, io.ErrUnexpectedEOF
	}
	value := math.Float32frombits(binary.LittleEndian.Uint32(cursor.data[cursor.off : cursor.off+4]))
	cursor.off += 4
	return value, nil
}

func (cursor *gateCDRCursor) string() error {
	_, err := cursor.stringValue()
	return err
}

func (cursor *gateCDRCursor) stringValue() (string, error) {
	length, err := cursor.uint32()
	if err != nil {
		return "", err
	}
	if int(length) > len(cursor.data)-cursor.off {
		return "", io.ErrUnexpectedEOF
	}
	value := cursor.data[cursor.off : cursor.off+int(length)]
	if len(value) > 0 && value[len(value)-1] == 0 {
		value = value[:len(value)-1]
	}
	cursor.off += int(length)
	cursor.align(4)
	return string(value), nil
}

func errorsIsEOF(err error) bool {
	return err == io.EOF
}

func hoverMissionHasTakeoffEvidence(mission map[string]any) bool {
	if airborneSeen, _ := mission["airborne_seen"].(bool); !airborneSeen {
		return false
	}
	altitudeCrosscheck := mapFromAny(mission["hover_altitude_crosscheck"])
	if ok, _ := altitudeCrosscheck["ok"].(bool); !ok {
		return false
	}
	if metricInt(mission, "local_position_count") <= 0 {
		return false
	}
	if !metricNumberPresent(mission, "current_z_ned") || !metricNumberPresent(mission, "altitude_error_m") {
		return false
	}
	tolerance := metricFloat(mission, "hover_altitude_tolerance_m")
	if tolerance <= 0 {
		tolerance = 0.18
	}
	return metricFloat(mission, "altitude_error_m") <= tolerance
}

func x2ScanSourceBlockers(x2 map[string]any) []string {
	if len(x2) == 0 {
		return []string{"x2_status_missing"}
	}
	blockers := []string{}
	if source, _ := x2["source"].(string); strings.TrimSpace(source) != "x2_serial_emulator" {
		blockers = append(blockers, "x2_status_source_invalid")
	}
	if scanSource, _ := x2["scan_source"].(string); strings.TrimSpace(scanSource) != "gazebo_ideal" {
		blockers = append(blockers, "x2_scan_source_not_gazebo_ideal")
	}
	age := metricFloat(x2, "latest_scan_ideal_age_sec")
	if age < 0 || age > 2.0 {
		blockers = append(blockers, "x2_scan_ideal_stale")
	}
	if metricInt(x2, "packet_count") <= 0 || metricInt(x2, "byte_count") <= 0 {
		blockers = append(blockers, "x2_packets_missing")
	}
	return blockers
}

func parseSLAMRuntimeLog(path string) map[string]any {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	lines := strings.Split(string(data), "\n")
	metrics := map[string]any{
		"path":                         path,
		"exists":                       true,
		"dropped_earlier_points_count": 0,
		"rejected_odom_tf_log_count":   0,
		"std_length_error_count":       0,
		"cartographer_waiting_for_imu_queue_count":     0,
		"cartographer_waiting_for_imu_queue_threshold": 20,
		"fatal_count":   0,
		"error_count":   0,
		"warning_count": 0,
	}
	problemLines := []string{}
	waitingForIMULines := []string{}
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		lower := strings.ToLower(trimmed)
		matched := false
		if strings.Contains(lower, "dropped") && strings.Contains(lower, "earlier points") {
			incrementMetric(metrics, "dropped_earlier_points_count")
			matched = true
		}
		if strings.Contains(trimmed, "rejected odom TF") {
			incrementMetric(metrics, "rejected_odom_tf_log_count")
			matched = true
		}
		if strings.Contains(trimmed, "std::length_error") {
			incrementMetric(metrics, "std_length_error_count")
			matched = true
		}
		if strings.Contains(trimmed, "Queue waiting for data: (0, imu)") {
			incrementMetric(metrics, "cartographer_waiting_for_imu_queue_count")
			waitingForIMULines = appendLimited(waitingForIMULines, trimmed, 8)
			matched = true
		}
		if strings.Contains(lower, "fatal") || hasGlogSeverityPrefix(trimmed, 'F') {
			incrementMetric(metrics, "fatal_count")
			matched = true
		}
		if strings.Contains(lower, "error") || hasGlogSeverityPrefix(trimmed, 'E') {
			incrementMetric(metrics, "error_count")
			matched = true
		}
		if strings.Contains(lower, "warn") || hasGlogSeverityPrefix(trimmed, 'W') {
			incrementMetric(metrics, "warning_count")
			matched = true
		}
		if matched {
			problemLines = appendLimited(problemLines, trimmed, 8)
		}
	}
	metrics["quality"] = slamRuntimeQuality(metrics)
	metrics["ok"] = metrics["std_length_error_count"] == 0 &&
		metrics["fatal_count"] == 0 &&
		metrics["error_count"] == 0 &&
		metricInt(metrics, "cartographer_waiting_for_imu_queue_count") <= metricInt(metrics, "cartographer_waiting_for_imu_queue_threshold")
	if len(problemLines) > 0 {
		metrics["last_problem_lines"] = problemLines
	}
	if len(waitingForIMULines) > 0 {
		metrics["cartographer_waiting_for_imu_queue_last_lines"] = waitingForIMULines
	}
	return metrics
}

func parseBenewakeTFMiniRuntimeLog(path string) map[string]any {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var latest map[string]any
	for _, line := range strings.Split(string(data), "\n") {
		index := strings.Index(line, "Benewake TFmini status ")
		if index < 0 {
			continue
		}
		raw := strings.TrimSpace(line[index+len("Benewake TFmini status "):])
		payload := map[string]any{}
		if err := json.Unmarshal([]byte(raw), &payload); err != nil {
			continue
		}
		latest = payload
	}
	if latest == nil {
		return nil
	}
	latest["path"] = path
	latest["exists"] = true
	return latest
}

func slamRuntimeQuality(metrics map[string]any) string {
	if metricInt(metrics, "std_length_error_count") > 0 || metricInt(metrics, "fatal_count") > 0 || metricInt(metrics, "error_count") > 0 {
		return "unhealthy"
	}
	if metricInt(metrics, "cartographer_waiting_for_imu_queue_count") > metricInt(metrics, "cartographer_waiting_for_imu_queue_threshold") {
		return "blocked_waiting_for_imu"
	}
	dropped := metricInt(metrics, "dropped_earlier_points_count")
	warnings := metricInt(metrics, "warning_count")
	switch {
	case dropped == 0 && warnings <= 10:
		return "tight"
	case dropped <= 10 && warnings <= 100:
		return "nominal"
	case dropped <= 100:
		return "marginal"
	default:
		return "unstable"
	}
}

func slamRuntimeLogBlockers(metrics map[string]any) []string {
	if len(metrics) == 0 {
		return nil
	}
	blockers := []string{}
	if ok, _ := metrics["ok"].(bool); !ok {
		blockers = append(blockers, "slam_runtime_unhealthy")
	}
	if metricInt(metrics, "std_length_error_count") > 0 {
		blockers = append(blockers, "slam_runtime_std_length_error")
	}
	if metricInt(metrics, "cartographer_waiting_for_imu_queue_count") > metricInt(metrics, "cartographer_waiting_for_imu_queue_threshold") {
		blockers = append(blockers, "slam_cartographer_waiting_for_imu_queue")
	}
	if metricInt(metrics, "fatal_count") > 0 {
		blockers = append(blockers, "slam_runtime_fatal")
	}
	if metricInt(metrics, "error_count") > 0 {
		blockers = append(blockers, "slam_runtime_error")
	}
	return blockers
}

func slamPreflightBlockers(slam map[string]any, runtimeLog map[string]any) []string {
	blockers := []string{}
	if len(slam) == 0 {
		return blockers
	}
	ready, _ := slam["ready"].(bool)
	state, _ := slam["state"].(string)
	output := mapFromAny(slam["output"])
	odomCount := metricInt(output, "odom_count")
	if !ready && state == "waiting_for_cartographer_tf" {
		blockers = append(blockers, "slam_cartographer_tf_not_ready")
	}
	if odomCount <= 0 && metricInt(slam, "odom_samples") <= 0 {
		blockers = append(blockers, "slam_odom_preflight_missing")
	}
	if metricInt(runtimeLog, "cartographer_waiting_for_imu_queue_count") > metricInt(runtimeLog, "cartographer_waiting_for_imu_queue_threshold") {
		blockers = append(blockers, "slam_cartographer_waiting_for_imu_queue")
	}
	return blockers
}

func hoverTakeoffBlockers(taskID string, controller map[string]any) []string {
	if taskID != "hover" {
		return nil
	}
	if len(controller) == 0 {
		return []string{"hover_takeoff_evidence_missing"}
	}
	bootstrap := mapFromAny(controller["bootstrap"])
	takeoff := mapFromAny(bootstrap["takeoff"])
	if len(takeoff) == 0 {
		return []string{"hover_takeoff_evidence_missing"}
	}
	if ok, _ := takeoff["ok"].(bool); !ok {
		return []string{"hover_takeoff_not_ok"}
	}
	if ackAccepted, _ := takeoff["ack_accepted_seen"].(bool); !ackAccepted {
		return []string{"hover_takeoff_ack_missing"}
	}
	height := mapFromAny(takeoff["height"])
	observed := metricFloat(height, "height_m")
	required := hoverRequiredTakeoffHeightM(controller, height)
	if observed <= 0 || required <= 0 {
		return []string{"hover_takeoff_height_not_observed"}
	}
	if observed < required {
		return []string{"hover_takeoff_target_altitude_not_reached"}
	}
	return nil
}

func hoverRequiredTakeoffHeightM(controller map[string]any, height map[string]any) float64 {
	takeoffAlt := metricFloat(controller, "takeoff_alt_m")
	if takeoffAlt > 0 {
		required := takeoffAlt * 0.80
		if required < 0.40 {
			required = 0.40
		}
		if required > takeoffAlt {
			required = takeoffAlt
		}
		return required
	}
	return metricFloat(height, "target_min_m")
}

func metricInt(metrics map[string]any, key string) int {
	switch value := metrics[key].(type) {
	case int:
		return value
	case int64:
		return int(value)
	case float64:
		return int(value)
	default:
		return 0
	}
}

func metricFloat(metrics map[string]any, key string) float64 {
	switch value := metrics[key].(type) {
	case int:
		return float64(value)
	case int64:
		return float64(value)
	case float64:
		return value
	default:
		return 0
	}
}

func metricNumberPresent(metrics map[string]any, key string) bool {
	switch metrics[key].(type) {
	case int, int64, float64:
		return true
	default:
		return false
	}
}

func mapFromAny(value any) map[string]any {
	if typed, ok := value.(map[string]any); ok {
		return typed
	}
	return nil
}

func stringsFromAny(value any) []string {
	switch typed := value.(type) {
	case []string:
		return typed
	case []any:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			if text, ok := item.(string); ok {
				out = append(out, text)
			}
		}
		return out
	default:
		return nil
	}
}

func hasGlogSeverityPrefix(line string, severity byte) bool {
	if len(line) < 2 || line[0] != severity {
		return false
	}
	return line[1] >= '0' && line[1] <= '9'
}

func incrementMetric(metrics map[string]any, key string) {
	count, _ := metrics[key].(int)
	metrics[key] = count + 1
}

func appendLimited(values []string, value string, limit int) []string {
	values = append(values, value)
	if len(values) <= limit {
		return values
	}
	return values[len(values)-limit:]
}

func statusPayloadBySuffix(probes []ProbeOutputSummary, suffix string) (map[string]any, string) {
	for _, probe := range probes {
		samples, ok := probe.Payload["samples"].(map[string]any)
		if !ok {
			continue
		}
		for topic, rawSample := range samples {
			if !strings.HasSuffix(topic, suffix) {
				continue
			}
			sample, ok := rawSample.(map[string]any)
			if !ok {
				continue
			}
			if parsed, ok := sample["parsed"].(map[string]any); ok {
				return parsed, topic
			}
			data, ok := sample["data"].(string)
			if !ok || strings.TrimSpace(data) == "" {
				continue
			}
			payload := map[string]any{}
			if err := json.Unmarshal([]byte(data), &payload); err != nil {
				continue
			}
			return payload, topic
		}
	}
	return nil, ""
}

func probePayloadByName(probes []ProbeOutputSummary, name string) (map[string]any, string) {
	for _, probe := range probes {
		if probe.Name != name || len(probe.Payload) == 0 {
			continue
		}
		return probe.Payload, probe.Name
	}
	return nil, ""
}

func probeBlockers(probe ProbeOutputSummary) []string {
	blockers := stringListFromAny(probe.Payload["blockers"])
	samples, ok := probe.Payload["samples"].(map[string]any)
	if !ok {
		return blockers
	}
	for topic, rawSample := range samples {
		if strings.HasSuffix(topic, "/landing/status") {
			continue
		}
		if strings.HasSuffix(topic, "/scan_reference_drift/status") {
			continue
		}
		if strings.HasSuffix(topic, "/scan_reference_correction/status") {
			continue
		}
		if strings.HasSuffix(topic, "/external_nav/source_selector/status") {
			continue
		}
		sample, ok := rawSample.(map[string]any)
		if !ok {
			continue
		}
		if parsed, ok := sample["parsed"].(map[string]any); ok {
			blockers = append(blockers, stringListFromAny(parsed["blockers"])...)
		}
	}
	return blockers
}

func stringListFromAny(raw any) []string {
	values, ok := raw.([]any)
	if !ok {
		return nil
	}
	out := make([]string, 0, len(values))
	for _, value := range values {
		text, ok := value.(string)
		if !ok || strings.TrimSpace(text) == "" {
			continue
		}
		out = append(out, text)
	}
	return out
}

func stringAnySliceContains(raw any, expected string) bool {
	for _, value := range stringListFromAny(raw) {
		if value == expected {
			return true
		}
	}
	return false
}

func subsetMap(source map[string]any, keys ...string) map[string]any {
	result := map[string]any{}
	for _, key := range keys {
		if value, ok := source[key]; ok {
			result[key] = value
		}
	}
	if len(result) == 0 {
		return nil
	}
	return result
}

func mergeMaps(base map[string]any, overlay map[string]any) map[string]any {
	if len(base) == 0 {
		return overlay
	}
	result := map[string]any{}
	for key, value := range base {
		result[key] = value
	}
	for key, value := range overlay {
		result[key] = value
	}
	return result
}

func landingFromProbeOutputs(probes []ProbeOutputSummary) *helpers.Landing {
	var fallback *helpers.Landing
	for _, probe := range probes {
		samples, ok := probe.Payload["samples"].(map[string]any)
		if !ok {
			continue
		}
		for topic, rawSample := range samples {
			if !strings.HasSuffix(topic, "/landing/status") {
				continue
			}
			sample, ok := rawSample.(map[string]any)
			if !ok {
				continue
			}
			payload := map[string]any{}
			if parsed, ok := sample["parsed"].(map[string]any); ok {
				payload = parsed
			} else if data, ok := sample["data"].(string); ok && strings.TrimSpace(data) != "" {
				if err := json.Unmarshal([]byte(data), &payload); err != nil {
					continue
				}
			}
			if len(payload) == 0 {
				continue
			}
			data, err := json.Marshal(payload)
			if err != nil {
				continue
			}
			var landing helpers.Landing
			if err := json.Unmarshal(data, &landing); err != nil {
				continue
			}
			if landing.OK {
				return &landing
			}
			value := landing
			fallback = &value
		}
	}
	return fallback
}

func landingFromHoverMissionSummary(mission map[string]any) *helpers.Landing {
	landingMap := mapFromAny(mission["landing"])
	if len(landingMap) == 0 {
		return nil
	}
	data, err := json.Marshal(landingMap)
	if err != nil {
		return nil
	}
	var landing helpers.Landing
	if err := json.Unmarshal(data, &landing); err != nil {
		return nil
	}
	if landingOK, _ := mission["landing_ok"].(bool); landing.Claim == "" && landingOK {
		landing.Claim = helpers.ClaimEvaluated
	}
	return &landing
}

func evaluateProbeOutputs(plan Plan, artifactDir string) []ProbeOutputSummary {
	summaries := make([]ProbeOutputSummary, 0, len(plan.Execution.ROSProbes))
	for _, probe := range plan.Execution.ROSProbes {
		path := filepath.Join(artifactDir, probe.OutputPath)
		summary := ProbeOutputSummary{Name: probe.Name, Path: path}
		data, err := readEventuallyStableProbeOutput(path)
		if err != nil {
			summaries = append(summaries, summary)
			continue
		}
		summary.Exists = true
		if strings.TrimSpace(string(data)) == "" {
			summary.Empty = true
			summaries = append(summaries, summary)
			continue
		}
		payload := map[string]any{}
		if err := json.Unmarshal(data, &payload); err != nil {
			summary.OK = strings.TrimSpace(string(data)) != ""
			summaries = append(summaries, summary)
			continue
		}
		summary.Payload = payload
		if status, _ := payload["status"].(string); status != "" {
			summary.Status = status
		}
		if ok, exists := payload["ok"].(bool); exists {
			summary.OK = ok
		} else {
			summary.OK = len(payload) > 0
		}
		summaries = append(summaries, summary)
	}
	return summaries
}

func readEventuallyStableProbeOutput(path string) ([]byte, error) {
	var lastData []byte
	var lastErr error
	for attempt := 0; attempt < 50; attempt++ {
		data, err := os.ReadFile(path)
		if err != nil {
			lastErr = err
			time.Sleep(100 * time.Millisecond)
			continue
		}
		lastData = data
		if len(strings.TrimSpace(string(data))) == 0 {
			time.Sleep(100 * time.Millisecond)
			continue
		}
		payload := map[string]any{}
		if err := json.Unmarshal(data, &payload); err == nil {
			return data, nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	if lastData != nil {
		return lastData, nil
	}
	return nil, lastErr
}

func evaluateRosbagProfiles(plan Plan, artifactDir string) []RosbagGateSummary {
	summaries := make([]RosbagGateSummary, 0, len(plan.Execution.RosbagRecords))
	for _, rosbag := range plan.Execution.RosbagRecords {
		requiredTopics := rosbag.RequiredTopics
		if len(requiredTopics) == 0 {
			requiredTopics = rosbag.Topics
		}
		metadataPath := filepath.Join(artifactDir, rosbag.OutputDir, "metadata.yaml")
		summary := RosbagGateSummary{
			Name:           rosbag.Name,
			MetadataPath:   metadataPath,
			RequiredTopics: append([]string(nil), requiredTopics...),
		}
		data, err := os.ReadFile(metadataPath)
		if err != nil {
			counts, paths, mcapErr := rosbagMCAPMessageCounts(filepath.Join(artifactDir, rosbag.OutputDir))
			if mcapErr != nil {
				summary.MetadataMissingOrUnreadable = err.Error() + "; mcap_fallback=" + mcapErr.Error()
				summaries = append(summaries, summary)
				continue
			}
			summary.Exists = true
			summary.MCAPPaths = paths
			summary.MessageCounts = counts
			summary.MessageCountsSource = "mcap_stream"
			evaluateRosbagRequiredTopics(&summary, requiredTopics)
			summaries = append(summaries, summary)
			continue
		}
		summary.Exists = true
		counts := helpers.MetadataCountsFromString(string(data))
		summary.MessageCounts = counts
		summary.MessageCountsSource = "metadata"
		evaluateRosbagRequiredTopics(&summary, requiredTopics)
		summaries = append(summaries, summary)
	}
	return summaries
}

func evaluateRosbagRequiredTopics(summary *RosbagGateSummary, requiredTopics []string) {
	for _, topic := range requiredTopics {
		count, exists := summary.MessageCounts[topic]
		if !exists {
			summary.MissingRequiredTopics = append(summary.MissingRequiredTopics, topic)
			continue
		}
		if count <= 0 {
			summary.ZeroCountRequiredTopics = append(summary.ZeroCountRequiredTopics, topic)
		}
	}
	summary.OK = len(summary.MissingRequiredTopics) == 0 && len(summary.ZeroCountRequiredTopics) == 0
}

func rosbagMCAPMessageCounts(outputDir string) (map[string]int, []string, error) {
	var lastErr error
	for attempt := 0; attempt < 40; attempt++ {
		paths, err := rosbagMCAPPaths(outputDir)
		if err != nil {
			return nil, nil, err
		}
		if len(paths) == 0 {
			lastErr = fmt.Errorf("no mcap files found in %s", outputDir)
			time.Sleep(250 * time.Millisecond)
			continue
		}
		counts := map[string]int{}
		readable := true
		for _, path := range paths {
			if err := addMCAPMessageCounts(path, counts); err != nil {
				lastErr = err
				readable = false
				break
			}
		}
		if readable {
			return counts, paths, nil
		}
		time.Sleep(250 * time.Millisecond)
	}
	if lastErr == nil {
		lastErr = fmt.Errorf("no readable mcap files found in %s", outputDir)
	}
	return nil, nil, lastErr
}

func rosbagMCAPPaths(outputDir string) ([]string, error) {
	paths, err := filepath.Glob(filepath.Join(outputDir, "*.mcap"))
	if err != nil {
		return nil, err
	}
	compressedPaths, err := filepath.Glob(filepath.Join(outputDir, "*.mcap.zstd"))
	if err != nil {
		return nil, err
	}
	paths = append(paths, compressedPaths...)
	sort.Strings(paths)
	return paths, nil
}

func addMCAPMessageCounts(path string, counts map[string]int) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer func() { _ = file.Close() }()
	var stream io.Reader = file
	var decoder *zstd.Decoder
	if strings.HasSuffix(path, ".zstd") {
		decoder, err = zstd.NewReader(file)
		if err != nil {
			return err
		}
		defer decoder.Close()
		stream = decoder
	}
	reader, err := mcap.NewReader(stream)
	if err != nil {
		return err
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return err
	}
	localCounts := map[string]int{}
	for {
		_, channel, _, err := it.Next(nil) //nolint:staticcheck
		if errorsIsEOF(err) {
			break
		}
		if err != nil {
			if len(localCounts) > 0 {
				for topic, count := range localCounts {
					counts[topic] += count
				}
				return nil
			}
			return err
		}
		if channel != nil {
			localCounts[channel.Topic]++
		}
	}
	for topic, count := range localCounts {
		counts[topic] += count
	}
	return nil
}

func taskSpecificChecks(runtimeConfig config.TaskRuntimeConfig, taskID string) map[string]bool {
	checks := map[string]bool{}
	switch taskID {
	case "hover-slam-only":
		checks["slam_only_task_id"] = runtimeConfig.TaskID == "hover-slam-only"
	case "hover":
		checks["hover_takeoff_altitude_positive"] = runtimeConfig.FCUController.TakeoffAltM > 0
		checks["hover_landing_policy_valid"] = validLandingPolicy(runtimeConfig.Landing.HoverPolicy)
		checks["hover_claim_evaluated"] = runtimeConfig.SlamHover.HoverClaim == "evaluated"
	case "exploration":
		checks["exploration_window_positive"] = runtimeConfig.ExplorationGate.ExplorationWindowSec > 0
		checks["exploration_min_goals_positive"] = runtimeConfig.ExplorationGate.MinAcceptedGoals > 0
		checks["exploration_landing_policy_valid"] = validLandingPolicy(runtimeConfig.Landing.ExplorationPolicy)
		checks["exploration_claim_evaluated"] = runtimeConfig.ExplorationGate.ExplorationClaim == "evaluated"
	case "navigation":
		checks["nav2_enabled"] = runtimeConfig.Nav2.Enabled
		checks["nav2_frames_configured"] = runtimeConfig.Nav2.GlobalFrame != "" && runtimeConfig.Nav2.OdomFrame != "" && runtimeConfig.Nav2.BaseFrame != ""
		checks["nav2_costmap_layers_configured"] = len(runtimeConfig.Nav2.Costmap.RequiredLayers) > 0
		checks["navigation_adapter_limits_positive"] = runtimeConfig.NavigationAdapter.MaxXYSpeedMPS > 0 && runtimeConfig.NavigationAdapter.FixedAltitudeM > 0
		checks["navigation_mission_positive"] = runtimeConfig.NavigationMission.NavigationWindowSec > 0 && runtimeConfig.NavigationMission.MinAcceptedGoals > 0 && runtimeConfig.NavigationMission.MinCoverageGrowth > 0
		checks["navigation_landing_policy_valid"] = validLandingPolicy(runtimeConfig.Landing.NavigationPolicy)
		checks["navigation_exit_goal_configured"] = runtimeConfig.NavigationMission.ExitGoal.ID != ""
		checks["navigation_claim_evaluated"] = runtimeConfig.NavigationMission.NavigationClaim == "evaluated"
	case "scan-robustness":
		scanStabilizationBlockers := helpers.ValidateScanStabilizationConfig(scanStabilizationSpec(runtimeConfig))
		checks["scan_stabilization_config_valid"] = len(scanStabilizationBlockers) == 0
		checks["airframe_required_profiles_configured"] = len(runtimeConfig.AirframeDisturbanceGate.RequiredProfiles) > 0
		checks["airframe_profile_configured"] = runtimeConfig.AirframeDisturbance.Profile != ""
		checks["scan_robustness_landing_policy_land_in_place"] = runtimeConfig.Landing.ScanRobustnessPolicy == "" || runtimeConfig.Landing.ScanRobustnessPolicy == helpers.PolicyLandInPlace
	}
	return checks
}

func taskSpecificBlockers(runtimeConfig config.TaskRuntimeConfig, taskID string) []string {
	switch taskID {
	case "navigation":
		return validateNavigationConfig(runtimeConfig)
	default:
		return nil
	}
}

func validateNavigationConfig(runtimeConfig config.TaskRuntimeConfig) []string {
	blockers := []string{}
	nav2 := runtimeConfig.Nav2
	costmap := runtimeConfig.Nav2.Costmap
	adapter := runtimeConfig.NavigationAdapter
	mission := runtimeConfig.NavigationMission
	if !nav2.Enabled {
		blockers = append(blockers, "nav2_config_disabled")
	}
	if nav2.GlobalFrame == "" || nav2.OdomFrame == "" || nav2.BaseFrame == "" {
		blockers = append(blockers, "nav2_tf_invalid:frame_missing")
	}
	if nav2.ScanTopic == "" || nav2.MapTopic == "" || nav2.CmdVelTopic == "" {
		blockers = append(blockers, "navigation_topic_missing")
	}
	if runtimeConfig.ScanStabilization.OutputScanTopic != "" && nav2.ScanTopic != runtimeConfig.ScanStabilization.OutputScanTopic {
		blockers = append(blockers, "navigation_scan_source_not_stabilized")
	}
	if nav2.CmdVelTopic == runtimeConfig.FCUController.CmdVelTopic || nav2.CmdVelTopic == "/ap/v1/cmd_vel" {
		blockers = append(blockers, "nav2_direct_fcu_cmd_vel_publisher")
	}
	if adapter.SetpointIntentTopic == runtimeConfig.FCUController.CmdVelTopic || adapter.SetpointIntentTopic == "/ap/v1/cmd_vel" {
		blockers = append(blockers, "navigation_adapter_direct_fcu_cmd_vel_publisher")
	}
	if !stringSliceContains(costmap.RequiredLayers, "obstacle_layer") {
		blockers = append(blockers, "nav2_obstacle_layer_missing")
	}
	if !stringSliceContains(costmap.RequiredLayers, "inflation_layer") {
		blockers = append(blockers, "nav2_inflation_layer_missing")
	}
	if costmap.GlobalCostmapTopic == "" || costmap.LocalCostmapTopic == "" {
		blockers = append(blockers, "navigation_costmap_topic_missing")
	}
	if costmap.MaxCostmapAgeSec <= 0 {
		blockers = append(blockers, "nav2_costmap_stale_threshold_invalid")
	}
	if costmap.MaxUnknownRatio <= 0 || costmap.MaxUnknownRatio > 1 {
		blockers = append(blockers, "navigation_costmap_unknown_ratio_invalid")
	}
	if costmap.UsesGazeboTruth || mission.UsesGazeboTruthAsInput {
		blockers = append(blockers, "navigation_uses_gazebo_truth_as_input")
	}
	if adapter.MaxXYSpeedMPS <= 0 || adapter.MaxYawRateDPS <= 0 || adapter.MaxAccelMPS2 <= 0 {
		blockers = append(blockers, "navigation_adapter_limit_invalid")
	}
	if adapter.FixedAltitudeM <= 0 {
		blockers = append(blockers, "navigation_fixed_altitude_invalid")
	}
	if mission.NavigationWindowSec <= 0 || mission.MinAcceptedGoals <= 0 || mission.MinPathLengthM <= 0 {
		blockers = append(blockers, "navigation_mission_threshold_invalid")
	}
	if mission.MinCoverageGrowth <= 0 || mission.MinCoverageGrowth > 1 {
		blockers = append(blockers, "navigation_coverage_threshold_invalid")
	}
	if mission.GoalFrame == "" || (mission.ExitGoal.ID == "" && len(mission.BoundedGoals) == 0) {
		blockers = append(blockers, "navigation_goal_contract_missing")
	}
	if mission.ExitGoal.ID == "" {
		blockers = append(blockers, "navigation_exit_goal_missing")
	}
	if mission.CompletionPolicy != "" && !validLandingPolicy(mission.CompletionPolicy) {
		blockers = append(blockers, "navigation_completion_policy_invalid")
	}
	return blockers
}

func validLandingPolicy(policy string) bool {
	return policy == "" ||
		policy == helpers.PolicyLandInPlace ||
		policy == helpers.PolicyAPLandModeAfterHover ||
		policy == helpers.PolicyReturnHomeThenLand
}

func landingConfig(project config.ProjectConfig, runtimeConfig config.TaskRuntimeConfig, taskID string) helpers.Config {
	landing := runtimeConfig.Landing
	policy := landing.DefaultPolicy
	switch taskID {
	case "hover":
		policy = landing.HoverPolicy
	case "exploration":
		policy = landing.ExplorationPolicy
	case "navigation":
		policy = landing.NavigationPolicy
	case "scan-robustness":
		policy = landing.ScanRobustnessPolicy
	}
	return helpers.Config{
		Enabled:                   landing.Enabled,
		Policy:                    policy,
		DefaultPolicy:             landing.DefaultPolicy,
		LandingStatusTopic:        landing.LandingStatusTopic,
		LandingIntentTopic:        landing.LandingIntentTopic,
		HomeSource:                landing.HomeSource,
		HomeRadiusM:               landing.HomeRadiusM,
		PreLandHoldSec:            landing.PreLandHoldSec,
		CompletionGraceSec:        landing.CompletionGraceSec,
		MaxReturnHomeDurationSec:  landing.MaxReturnHomeDurationSec,
		MaxLandingDurationSec:     landing.MaxLandingDurationSec,
		MaxDescentRateMPS:         landing.MaxDescentRateMPS,
		SetpointLookaheadSec:      landing.SetpointLookaheadSec,
		TouchdownAltitudeM:        landing.TouchdownAltitudeM,
		TouchdownVerticalSpeedMPS: landing.TouchdownVerticalSpeedMPS,
		RequireDisarm:             landing.RequireDisarm,
		RequireMotorsSafe:         landing.RequireMotorsSafe,
		UsesGazeboTruthAsInput:    project.Landing.UsesGazeboTruthAsInput,
	}
}

func stringSliceContains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func uniqueStrings(values []string) []string {
	seen := map[string]bool{}
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			continue
		}
		seen[value] = true
	}
	out := make([]string, 0, len(seen))
	for value := range seen {
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}
