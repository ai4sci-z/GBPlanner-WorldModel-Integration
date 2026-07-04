package hover

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"

	"github.com/foxglove/mcap/go/mcap"
)

func TestSummarizeHoverInitializationAuditRecordsTimingAnchorAndJumps(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "hover_rosbag_0.mcap")
	writeHoverInitializationAuditMCAP(t, path)
	summaryPath := filepath.Join(dir, "summary.json")
	writeInitializationAuditSummary(t, summaryPath)

	audit, err := summarizeHoverInitializationAudit(path, summaryPath)
	if err != nil {
		t.Fatal(err)
	}

	eventTimes := mapFromAny(audit["event_times_sec_from_bag_start"])
	if got := metricFloat(eventTimes, "takeoff_start"); math.Abs(got-1.0) > 1e-9 {
		t.Fatalf("takeoff_start = %v, want 1.0; audit=%#v", got, eventTimes)
	}
	if got := metricFloat(eventTimes, "hover_hold_start"); math.Abs(got-5.0) > 1e-9 {
		t.Fatalf("hover_hold_start = %v, want 5.0; audit=%#v", got, eventTimes)
	}

	anchor := mapFromAny(audit["hover_anchor"])
	if anchor["status"] != "found" || math.Abs(metricFloat(anchor, "hold_yaw_rad")-0.25) > 1e-9 {
		t.Fatalf("anchor = %#v, want found hold yaw", anchor)
	}

	externalTiming := mapFromAny(audit["external_nav_status_timing"])
	if got := metricFloat(externalTiming, "first_ready_true_sec"); math.Abs(got-2.0) > 1e-9 {
		t.Fatalf("external ready = %v, want 2.0; timing=%#v", got, externalTiming)
	}
	mavTiming := mapFromAny(audit["mavlink_external_nav_timing"])
	if got := metricFloat(mavTiming, "first_fcu_local_position_sec"); math.Abs(got-3.0) > 1e-9 {
		t.Fatalf("fcu first = %v, want 3.0; timing=%#v", got, mavTiming)
	}

	jumps := mapFromAny(audit["takeoff_to_hover_hold_jumps"])
	slamJump := mapFromAny(jumps["slam_odom"])
	if got := metricFloat(slamJump, "max_step_m"); math.Abs(got-0.3) > 1e-9 {
		t.Fatalf("slam max_step = %v, want 0.3; jump=%#v", got, slamJump)
	}
	sources := mapFromAny(audit["sources"])
	slam := mapFromAny(sources["slam_odom"])
	atHover := mapFromAny(slam["at_hover_hold_start"])
	if got := metricFloat(atHover, "horizontal_from_first_m"); math.Abs(got-0.4) > 1e-9 {
		t.Fatalf("slam hover horizontal = %v, want 0.4; row=%#v", got, atHover)
	}
	cartographerInput := mapFromAny(sources["cartographer_odometry_input"])
	if got := metricInt(cartographerInput, "sample_count"); got != 3 {
		t.Fatalf("cartographer input sample_count = %v, want 3; source=%#v", got, cartographerInput)
	}

	hoverWindow := mapFromAny(audit["hover_hold_window"])
	cartographerInputWindow := mapFromAny(hoverWindow["cartographer_odometry_input"])
	if got := metricFloat(cartographerInputWindow, "max_horizontal_drift_m"); math.Abs(got-0.2) > 1e-9 {
		t.Fatalf("cartographer input hover drift = %v, want 0.2; row=%#v", got, cartographerInputWindow)
	}

	sensorTiming := mapFromAny(audit["sensor_timing"])
	scanTiming := mapFromAny(sensorTiming["scan"])
	if got := metricInt(scanTiming, "sample_count"); got != 3 {
		t.Fatalf("scan timing sample_count = %v, want 3; timing=%#v", got, scanTiming)
	}
	if got := metricFloat(scanTiming, "rate_hz"); math.Abs(got-1.5) > 1e-9 {
		t.Fatalf("scan timing rate_hz = %v, want 1.5; timing=%#v", got, scanTiming)
	}
	cartographerTiming := mapFromAny(sensorTiming["cartographer_odometry_input"])
	if got := metricInt(cartographerTiming, "sample_count"); got != 3 {
		t.Fatalf("cartographer timing sample_count = %v, want 3; timing=%#v", got, cartographerTiming)
	}

	slamStatus := mapFromAny(audit["slam_status_window"])
	if got := metricInt(slamStatus, "scan_count_delta"); got != 14 {
		t.Fatalf("slam scan_count_delta = %v, want 14; status=%#v", got, slamStatus)
	}
	if got := metricInt(slamStatus, "odom_count_delta"); got != 2 {
		t.Fatalf("slam odom_count_delta = %v, want 2; status=%#v", got, slamStatus)
	}

	mission := mapFromAny(audit["mission_summary"])
	if mission["status"] != "TASK_STATUS_BLOCKED" || mission["mission_reason"] != "hover_span_unstable" {
		t.Fatalf("mission summary = %#v", mission)
	}
}

func TestSummarizeHoverTrajectoryAuditAlignsSourcesAndPeaks(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "hover_rosbag_0.mcap")
	writeHoverInitializationAuditMCAP(t, path)

	audit, err := summarizeHoverTrajectoryAudit(path)
	if err != nil {
		t.Fatal(err)
	}

	window := mapFromAny(audit["hover_window_sec_from_bag_start"])
	if got := metricFloat(window, "start"); math.Abs(got-5.0) > 1e-9 {
		t.Fatalf("hover start = %v, want 5.0; window=%#v", got, window)
	}
	peaks := mapFromAny(audit["peaks"])
	slamPeak := mapFromAny(peaks["slam_odom"])
	if got := metricFloat(slamPeak, "horizontal_m"); math.Abs(got-math.Hypot(0.15, 0.05)) > 1e-9 {
		t.Fatalf("slam peak = %v, want %v; peak=%#v", got, math.Hypot(0.15, 0.05), slamPeak)
	}
	pairwise := mapFromAny(audit["pairwise_aligned_relative_motion"])
	slamGazebo := mapFromAny(pairwise["slam_odom__gazebo_model_odometry"])
	if got := metricInt(slamGazebo, "aligned_sample_count"); got != 3 {
		t.Fatalf("aligned sample count = %v, want 3; pair=%#v", got, slamGazebo)
	}
	if got := metricFloat(slamGazebo, "max_relative_vector_difference_m"); got <= 0 {
		t.Fatalf("max relative difference = %v, want positive; pair=%#v", got, slamGazebo)
	}
	alignedAtPeak := mapFromAny(audit["aligned_at_each_source_peak"])
	slamAligned := mapFromAny(alignedAtPeak["slam_odom"])
	statuses := mapFromAny(slamAligned["statuses"])
	setpoint := mapFromAny(statuses["fcu_setpoint_output"])
	if got := metricInt(setpoint, "mavlink_setpoint_count"); got != 2 {
		t.Fatalf("setpoint count at peak = %v, want 2; setpoint=%#v", got, setpoint)
	}
}

func writeHoverInitializationAuditMCAP(t *testing.T, path string) {
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
	scanSchema := &mcap.Schema{ID: 4, Name: "sensor_msgs/msg/LaserScan", Encoding: "ros2msg", Data: []byte("std_msgs/Header header\nfloat32[] ranges\n")}
	for _, schema := range []*mcap.Schema{odomSchema, stringSchema, poseSchema, scanSchema} {
		if err := writer.WriteSchema(schema); err != nil {
			t.Fatal(err)
		}
	}
	channels := []*mcap.Channel{
		{ID: 1, SchemaID: 1, Topic: "/slam/odom", MessageEncoding: "cdr"},
		{ID: 2, SchemaID: 1, Topic: "/external_nav/odom", MessageEncoding: "cdr"},
		{ID: 3, SchemaID: 3, Topic: "/navlab/fcu/local_position_pose", MessageEncoding: "cdr"},
		{ID: 4, SchemaID: 2, Topic: "/navlab/hover/status", MessageEncoding: "cdr"},
		{ID: 5, SchemaID: 2, Topic: "/external_nav/status", MessageEncoding: "cdr"},
		{ID: 6, SchemaID: 2, Topic: "/mavlink_external_nav/status", MessageEncoding: "cdr"},
		{ID: 7, SchemaID: 1, Topic: "/cartographer/odometry_input", MessageEncoding: "cdr"},
		{ID: 8, SchemaID: 4, Topic: "/scan", MessageEncoding: "cdr"},
		{ID: 9, SchemaID: 2, Topic: "/navlab/slam/status", MessageEncoding: "cdr"},
		{ID: 10, SchemaID: 1, Topic: "/gazebo/model/odometry", MessageEncoding: "cdr"},
		{ID: 11, SchemaID: 2, Topic: "/navlab/fcu/controller/status", MessageEncoding: "cdr"},
		{ID: 12, SchemaID: 2, Topic: "/navlab/fcu/setpoint/output", MessageEncoding: "cdr"},
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

	writeMsg(4, 1, gateTestStringCDR(`{"phase":"wait_ready","position":{"x":0,"y":0,"yaw_rad":0}}`))
	writeMsg(1, 1, gateTestOdometryPoseCDR(0.0, 0.0, 0.0, 0.0))
	writeMsg(5, 1, gateTestStringCDR(`{"ready":false,"state":"waiting"}`))
	writeMsg(6, 1, gateTestStringCDR(`{"ready":false,"state":"waiting","sent_count":0,"local_position_count":0}`))
	writeMsg(4, 2, gateTestStringCDR(`{"phase":"takeoff","position":{"x":0.1,"y":0,"yaw_rad":0.1}}`))
	writeMsg(1, 2, gateTestOdometryPoseCDR(0.1, 0.0, 0.0, 0.1))
	writeMsg(2, 2, gateTestOdometryPoseCDR(0.1, 0.0, 0.0, 0.1))
	writeMsg(5, 3, gateTestStringCDR(`{"ready":true,"state":"healthy"}`))
	writeMsg(1, 3, gateTestOdometryPoseCDR(0.4, 0.0, 0.0, 0.2))
	writeMsg(6, 3, gateTestStringCDR(`{"ready":false,"state":"sending","sent_count":1,"local_position_count":0}`))
	writeMsg(4, 4, gateTestStringCDR(`{"phase":"hover_settle","position":{"x":0.4,"y":0,"yaw_rad":0.2}}`))
	writeMsg(3, 4, gateTestPoseStampedPoseCDR(0.4, 0.0, 0.0, 0.2))
	writeMsg(6, 4, gateTestStringCDR(`{"ready":true,"state":"sending","sent_count":2,"local_position_count":1}`))
	writeMsg(4, 6, gateTestStringCDR(`{"phase":"hover_hold","position":{"x":0.4,"y":0,"yaw_rad":0.25,"hold_x":0.4,"hold_y":0,"hold_yaw_rad":0.25}}`))
	writeMsg(1, 6, gateTestOdometryPoseCDR(0.4, 0.0, 0.0, 0.25))
	writeMsg(2, 6, gateTestOdometryPoseCDR(0.4, 0.0, 0.0, 0.25))
	writeMsg(3, 6, gateTestPoseStampedPoseCDR(0.4, 0.0, 0.0, 0.25))
	writeMsg(10, 6, gateTestOdometryPoseCDR(0.4, 0.0, 0.0, 0.25))
	writeMsg(11, 6, gateTestStringCDR(`{"ready":true,"state":"hover_hold","pose_samples":1,"mavlink_setpoint_count":1,"mavlink_local_position_count":1}`))
	writeMsg(12, 6, gateTestStringCDR(`{"ready":true,"state":"hold_position","mavlink_setpoint_count":1,"mavlink_local_position_count":1,"path_length_m":0}`))
	writeMsg(7, 6, gateTestOdometryPoseCDR(0.0, 0.0, 0.0, 0.0))
	writeMsg(8, 6, gateTestLaserScanCDR(5.0, 0.0, 0.0))
	writeMsg(9, 6, gateTestStringCDR(`{"scan":{"count":10},"imu":{"count":100},"tf":{"count":20,"received_count":20,"rejected_count":0,"max_observed_jump_m":0.01,"max_accepted_jump_m":0.01,"max_rejected_jump_m":0,"rejection_ratio":0},"output":{"odom_count":3}}`))
	writeMsg(1, 7, gateTestOdometryPoseCDR(0.50, 0.02, 0.0, 0.25))
	writeMsg(2, 7, gateTestOdometryPoseCDR(0.48, 0.02, 0.0, 0.25))
	writeMsg(3, 7, gateTestPoseStampedPoseCDR(0.46, 0.01, 0.0, 0.25))
	writeMsg(10, 7, gateTestOdometryPoseCDR(0.47, 0.02, 0.0, 0.25))
	writeMsg(7, 7, gateTestOdometryPoseCDR(0.1, 0.0, 0.0, 0.0))
	writeMsg(8, 7, gateTestLaserScanCDR(5.0, 0.1, 0.0))
	writeMsg(4, 8, gateTestStringCDR(`{"phase":"hover_hold","position":{"x":0.42,"y":0,"yaw_rad":0.25,"hold_x":0.4,"hold_y":0,"hold_yaw_rad":0.25}}`))
	writeMsg(1, 8, gateTestOdometryPoseCDR(0.55, 0.05, 0.0, 0.25))
	writeMsg(2, 8, gateTestOdometryPoseCDR(0.53, 0.04, 0.0, 0.25))
	writeMsg(3, 8, gateTestPoseStampedPoseCDR(0.48, 0.02, 0.0, 0.25))
	writeMsg(10, 8, gateTestOdometryPoseCDR(0.52, 0.05, 0.0, 0.25))
	writeMsg(11, 8, gateTestStringCDR(`{"ready":true,"state":"hover_hold","pose_samples":3,"mavlink_setpoint_count":2,"mavlink_local_position_count":3}`))
	writeMsg(12, 8, gateTestStringCDR(`{"ready":true,"state":"hold_position","mavlink_setpoint_count":2,"mavlink_local_position_count":3,"path_length_m":0.12}`))
	writeMsg(7, 8, gateTestOdometryPoseCDR(0.2, 0.0, 0.0, 0.0))
	writeMsg(8, 8, gateTestLaserScanCDR(5.0, 0.2, 0.0))
	writeMsg(9, 8, gateTestStringCDR(`{"scan":{"count":24},"imu":{"count":300},"tf":{"count":35,"received_count":35,"rejected_count":1,"max_observed_jump_m":0.2,"max_accepted_jump_m":0.1,"max_rejected_jump_m":0.2,"rejection_ratio":0.03},"output":{"odom_count":5}}`))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeInitializationAuditSummary(t *testing.T, path string) {
	t.Helper()
	data := map[string]any{
		"status":  "TASK_STATUS_BLOCKED",
		"ok":      false,
		"blocked": true,
		"metrics": map[string]any{
			"gate": map[string]any{
				"hover_mission": map[string]any{
					"ok":                  false,
					"reason":              "hover_span_unstable",
					"mission_phase_state": "S12 landing_complete",
					"hover_body_ok":       false,
					"hover_drift": map[string]any{
						"horizontal_drift_m":                     0.07,
						"horizontal_span_m":                      0.3,
						"external_nav_loss_duration_sec":         0,
						"mavlink_external_nav_loss_duration_sec": 0,
					},
				},
			},
		},
	}
	encoded, err := json.Marshal(data)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, encoded, 0o644); err != nil {
		t.Fatal(err)
	}
}

func gateTestOdometryPoseCDR(x float64, y float64, z float64, yaw float64) []byte {
	builder := gateTestCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(1)
	builder.uint32(2)
	builder.string("map")
	builder.string("base_link")
	builder.float64(x)
	builder.float64(y)
	builder.float64(z)
	appendYawQuaternion(&builder, yaw)
	return builder.data
}

func gateTestPoseStampedPoseCDR(x float64, y float64, z float64, yaw float64) []byte {
	builder := gateTestCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(1)
	builder.uint32(2)
	builder.string("map")
	builder.float64(x)
	builder.float64(y)
	builder.float64(z)
	appendYawQuaternion(&builder, yaw)
	return builder.data
}

func appendYawQuaternion(builder *gateTestCDRBuilder, yaw float64) {
	builder.float64(0)
	builder.float64(0)
	builder.float64(math.Sin(yaw * 0.5))
	builder.float64(math.Cos(yaw * 0.5))
}
