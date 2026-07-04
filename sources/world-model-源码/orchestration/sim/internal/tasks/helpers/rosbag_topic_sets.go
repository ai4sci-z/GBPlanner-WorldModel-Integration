package helpers

var matureWorldSLAMReviewTopics = []string{
	"/tf",
	"/tf_static",
	"/ap/v1/pose/filtered",
	"/ap/v1/twist/filtered",
	"/navlab/fcu/local_position_pose",
	"/rangefinder/down/range",
	"/navlab/slam/imu",
	"/height/estimate",
	"/height/status",
	"/navlab/fcu/setpoint/intent",
	"/navlab/fcu/setpoint/output",
	"/navlab/fcu/controller/status",
	"/navlab/slam/status",
	"/external_nav/odom",
	"/external_nav/status",
	"/mavlink_external_nav/status",
	"/navlab/scan_reference_drift/odom",
	"/navlab/scan_reference_drift/status",
	"/slam/odom_corrected",
	"/navlab/scan_reference_correction/status",
	"/external_nav/odom_candidate",
	"/external_nav/source_selector/status",
	"/navlab/hover/status",
	"/slam/odom",
	"/lidar",
	"/scan",
	"/submap_list",
	"/trajectory_node_list",
	"/sim/x2/status",
	"/navlab/x2/scan_time_normalizer/status",
	"/map",
	OfficialMazeOverlayTopic,
	"/navlab/landing/status",
}

// MatureWorldSLAMReviewTopics is the stable Foxglove review surface carried
// forward from the mature world/SLAM runs. Navigation tasks may append topics,
// but should not replace this baseline.
func MatureWorldSLAMReviewTopics() []string {
	return append([]string(nil), matureWorldSLAMReviewTopics...)
}

func HoverTaskRequiredTopics(spec SlamHoverSpec) []string {
	return appendUniqueTopics(nil,
		"/tf",
		"/tf_static",
		spec.RangefinderRangeTopic,
		"/height/estimate",
		"/height/status",
		"/external_nav/odom",
		"/navlab/fcu/local_position_pose",
		spec.ScanReferenceOdomTopic,
		spec.ScanReferenceStatusTopic,
		"/external_nav/odom_candidate",
		"/external_nav/source_selector/status",
		spec.IMUTopic,
		spec.HoverStatusTopic,
		spec.SlamOdomTopic,
		"/lidar",
		"/navlab/landing/status",
		"/scan",
		"/sim/x2/status",
		"/map",
	)
}

func ExplorationTaskReviewTopics(spec ExplorationWorkflowSpec) []string {
	topics := MatureWorldSLAMReviewTopics()
	return appendUniqueTopics(topics,
		spec.SetpointIntentTopic,
		spec.SetpointOutputTopic,
		spec.ExplorationStatusTopic,
		"/navlab/exploration/goal",
		"/navlab/exploration/coverage",
		"/navlab/exploration/frontiers",
		"/navlab/exploration/path",
		"/navlab/exploration/markers",
	)
}

func ExplorationTaskRequiredTopics(spec ExplorationWorkflowSpec) []string {
	return appendUniqueTopics(nil,
		"/tf",
		"/tf_static",
		"/ap/v1/pose/filtered",
		"/ap/v1/twist/filtered",
		"/rangefinder/down/range",
		spec.ControllerStatusTopic,
		spec.SetpointIntentTopic,
		spec.SetpointOutputTopic,
		spec.ExplorationStatusTopic,
		spec.SlamOdomTopic,
		"/scan",
		"/map",
	)
}

func NavigationTaskReviewTopics(spec Nav2NavigationSpec) []string {
	topics := MatureWorldSLAMReviewTopics()
	return appendUniqueTopics(topics,
		spec.NavigationStatusTopic,
		spec.NavigationEventsTopic,
		spec.NavigationGoalTopic,
		spec.NavigationPathTopic,
		spec.NavigationRecoveryTopic,
		spec.AdapterStatusTopic,
		spec.CostmapHealthTopic,
		spec.CmdVelTopic,
		spec.GlobalCostmapTopic,
		spec.LocalCostmapTopic,
		"/submap_list",
		"/trajectory_node_list",
	)
}

func NavigationTaskRequiredTopics(spec Nav2NavigationSpec) []string {
	return appendUniqueTopics(nil,
		"/tf",
		"/tf_static",
		"/ap/v1/pose/filtered",
		"/ap/v1/twist/filtered",
		"/rangefinder/down/range",
		spec.SetpointIntentTopic,
		"/navlab/fcu/setpoint/output",
		spec.ControllerStatusTopic,
		spec.SlamStatusTopic,
		"/navlab/hover/status",
		spec.SlamOdomTopic,
		spec.ScanTopic,
		spec.MapTopic,
		spec.LandingStatusTopic,
		spec.NavigationStatusTopic,
		spec.NavigationEventsTopic,
		spec.NavigationGoalTopic,
		spec.AdapterStatusTopic,
		spec.CostmapHealthTopic,
		spec.CmdVelTopic,
		spec.GlobalCostmapTopic,
		spec.LocalCostmapTopic,
	)
}

func appendUniqueTopics(topics []string, additions ...string) []string {
	seen := make(map[string]bool, len(topics)+len(additions))
	result := make([]string, 0, len(topics)+len(additions))
	for _, topic := range append(topics, additions...) {
		if topic == "" || seen[topic] {
			continue
		}
		seen[topic] = true
		result = append(result, topic)
	}
	return result
}
