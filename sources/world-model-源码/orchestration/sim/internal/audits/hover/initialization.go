package hover

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"sort"

	"github.com/foxglove/mcap/go/mcap"
	"github.com/klauspost/compress/zstd"
)

type timedPoseSample struct {
	X            float64
	Y            float64
	Z            float64
	YawRad       *float64
	FrameID      string
	ChildFrameID string
	LogTimeSec   float64
}

type timedStatusSample struct {
	Payload    map[string]any
	LogTimeSec float64
}

type timedMessageSample struct {
	LogTimeSec     float64
	HeaderStampSec *float64
}

// BuildHoverInitializationAudit builds a diagnostic-only timing and pose audit
// for one hover run. It does not affect runtime control or gate acceptance.
func BuildHoverInitializationAudit(artifactDir string) (map[string]any, error) {
	path := filepath.Join(artifactDir, "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd")
	if _, err := os.Stat(path); err != nil {
		path = filepath.Join(artifactDir, "rosbag", "hover_rosbag", "hover_rosbag_0.mcap")
	}
	return summarizeHoverInitializationAudit(path, filepath.Join(artifactDir, "summary.json"))
}

func summarizeHoverInitializationAudit(path string, summaryPath string) (map[string]any, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()

	var stream io.Reader = file
	var decoder *zstd.Decoder
	if filepath.Ext(path) == ".zstd" {
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

	poseTopics := map[string]struct {
		key  string
		kind string
	}{
		"/slam/odom":                      {key: "slam_odom", kind: "odometry"},
		"/slam/odom_corrected":            {key: "slam_odom_corrected", kind: "odometry"},
		"/cartographer/odometry_input":    {key: "cartographer_odometry_input", kind: "odometry"},
		"/external_nav/odom_candidate":    {key: "external_nav_odom_candidate", kind: "odometry"},
		"/external_nav/odom":              {key: "external_nav_odom", kind: "odometry"},
		"/navlab/fcu/local_position_pose": {key: "fcu_local_position_pose", kind: "pose_stamped"},
		"/gazebo/model/odometry":          {key: "gazebo_model_odometry", kind: "odometry"},
	}
	statusTopics := map[string]string{
		"/navlab/hover/status":         "hover_status",
		"/external_nav/status":         "external_nav_status",
		"/mavlink_external_nav/status": "mavlink_external_nav_status",
		"/navlab/slam/status":          "slam_status",
	}
	timingTopics := map[string]struct {
		key        string
		parseStamp bool
	}{
		"/scan":                        {key: "scan", parseStamp: true},
		"/navlab/slam/imu":             {key: "slam_imu", parseStamp: true},
		"/navlab/slam/tf":              {key: "slam_tf", parseStamp: false},
		"/cartographer/odometry_input": {key: "cartographer_odometry_input", parseStamp: true},
	}
	poses := map[string][]timedPoseSample{}
	for _, spec := range poseTopics {
		poses[spec.key] = []timedPoseSample{}
	}
	statuses := map[string][]timedStatusSample{}
	for _, key := range statusTopics {
		statuses[key] = []timedStatusSample{}
	}
	timingSamples := map[string][]timedMessageSample{}
	for _, spec := range timingTopics {
		timingSamples[spec.key] = []timedMessageSample{}
	}

	bagStartSec := 0.0
	bagEndSec := 0.0
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errorsIsEOF(err) {
			break
		}
		if err != nil {
			return nil, err
		}
		stampSec := float64(message.LogTime) / 1e9
		if bagStartSec == 0 || stampSec < bagStartSec {
			bagStartSec = stampSec
		}
		if stampSec > bagEndSec {
			bagEndSec = stampSec
		}
		if spec, ok := poseTopics[channel.Topic]; ok {
			var sample timedPoseSample
			switch spec.kind {
			case "pose_stamped":
				sample, err = parsePoseStampedPoseCDR(message.Data)
			default:
				sample, err = parseOdometryPoseCDR(message.Data)
			}
			if err != nil {
				return nil, fmt.Errorf("parse %s: %w", channel.Topic, err)
			}
			sample.LogTimeSec = stampSec
			poses[spec.key] = append(poses[spec.key], sample)
			if timingSpec, ok := timingTopics[channel.Topic]; ok {
				var headerStamp *float64
				if timingSpec.parseStamp {
					if parsed, err := parseHeaderStampSecCDR(message.Data); err == nil {
						headerStamp = &parsed
					}
				}
				timingSamples[timingSpec.key] = append(timingSamples[timingSpec.key], timedMessageSample{
					LogTimeSec:     stampSec,
					HeaderStampSec: headerStamp,
				})
			}
			continue
		}
		if key, ok := statusTopics[channel.Topic]; ok {
			payload, err := parseJSONStatusCDR(message.Data)
			if err != nil {
				return nil, fmt.Errorf("parse %s: %w", channel.Topic, err)
			}
			statuses[key] = append(statuses[key], timedStatusSample{Payload: payload, LogTimeSec: stampSec})
			continue
		}
		if spec, ok := timingTopics[channel.Topic]; ok {
			var headerStamp *float64
			if spec.parseStamp {
				if parsed, err := parseHeaderStampSecCDR(message.Data); err == nil {
					headerStamp = &parsed
				}
			}
			timingSamples[spec.key] = append(timingSamples[spec.key], timedMessageSample{
				LogTimeSec:     stampSec,
				HeaderStampSec: headerStamp,
			})
		}
	}

	phaseTimes, anchor := summarizeHoverStatusTiming(statuses["hover_status"], bagStartSec)
	eventTimes := map[string]any{
		"mission_start":      relTime(firstStatusTime(statuses["hover_status"]), bagStartSec),
		"takeoff_start":      relTime(phaseTimes["takeoff"], bagStartSec),
		"hover_settle_start": relTime(phaseTimes["hover_settle"], bagStartSec),
		"hover_hold_start":   relTime(phaseTimes["hover_hold"], bagStartSec),
	}
	sourceRows := map[string]any{}
	sourceOrder := []string{
		"slam_odom",
		"slam_odom_corrected",
		"cartographer_odometry_input",
		"external_nav_odom_candidate",
		"external_nav_odom",
		"fcu_local_position_pose",
		"gazebo_model_odometry",
	}
	for _, key := range sourceOrder {
		sourceRows[key] = summarizeInitializationSource(poses[key], bagStartSec, phaseTimes)
	}

	navTiming := summarizeExternalNavStatusTiming(statuses["external_nav_status"], bagStartSec)
	mavTiming := summarizeMAVLinkExternalNavTiming(statuses["mavlink_external_nav_status"], bagStartSec)
	windowStart := phaseTimes["takeoff"]
	windowEnd := phaseTimes["hover_hold"]
	if windowStart == 0 {
		windowStart = phaseTimes["hover_settle"]
	}
	jumpRows := map[string]any{}
	for _, key := range []string{"slam_odom", "slam_odom_corrected", "cartographer_odometry_input", "external_nav_odom_candidate", "external_nav_odom"} {
		jumpRows[key] = summarizePoseJumps(poses[key], windowStart, windowEnd, bagStartSec)
	}
	hoverHoldWindow := map[string]any{}
	for _, key := range sourceOrder {
		hoverHoldWindow[key] = summarizePoseWindow(poses[key], phaseTimes["hover_hold"], lastHoverHoldTime(statuses["hover_status"]), bagStartSec)
	}
	hoverStart := phaseTimes["hover_hold"]
	hoverEnd := lastHoverHoldTime(statuses["hover_status"])
	sensorTiming := map[string]any{}
	for _, key := range []string{"scan", "slam_imu", "slam_tf", "cartographer_odometry_input"} {
		sensorTiming[key] = summarizeMessageTiming(timingSamples[key], hoverStart, hoverEnd, bagStartSec)
	}

	result := map[string]any{
		"schema":                    "navlab.hover_initialization_audit.v1",
		"diagnostic_only":           true,
		"runtime_control_unchanged": true,
		"rosbag_path":               path,
		"summary_path":              summaryPath,
		"bag": map[string]any{
			"start_sec":    bagStartSec,
			"end_sec":      bagEndSec,
			"duration_sec": math.Max(0, bagEndSec-bagStartSec),
		},
		"event_times_sec_from_bag_start": eventTimes,
		"phase_times_sec_from_bag_start": relPhaseTimes(phaseTimes, bagStartSec),
		"hover_anchor":                   anchor,
		"sources":                        sourceRows,
		"external_nav_status_timing":     navTiming,
		"mavlink_external_nav_timing":    mavTiming,
		"slam_status_window":             summarizeSlamStatusWindow(statuses["slam_status"], hoverStart, hoverEnd, bagStartSec),
		"sensor_timing":                  sensorTiming,
		"takeoff_to_hover_hold_jumps":    jumpRows,
		"hover_hold_window":              hoverHoldWindow,
		"mission_summary":                initializationMissionSummary(summaryPath),
	}
	return result, nil
}

func summarizeHoverStatusTiming(samples []timedStatusSample, bagStartSec float64) (map[string]float64, map[string]any) {
	phaseTimes := map[string]float64{}
	anchor := map[string]any{"status": "not_found"}
	for _, sample := range samples {
		phase, _ := sample.Payload["phase"].(string)
		if phase != "" {
			if _, exists := phaseTimes[phase]; !exists {
				phaseTimes[phase] = sample.LogTimeSec
			}
		}
		position := mapFromAny(sample.Payload["position"])
		if anchor["status"] == "not_found" && position["hold_x"] != nil && position["hold_y"] != nil {
			anchor = map[string]any{
				"status":                  "found",
				"time_sec_from_bag_start": relTime(sample.LogTimeSec, bagStartSec),
				"phase":                   phase,
				"hold_x_m":                position["hold_x"],
				"hold_y_m":                position["hold_y"],
				"hold_yaw_rad":            position["hold_yaw_rad"],
				"current_x_m":             position["x"],
				"current_y_m":             position["y"],
				"current_yaw_rad":         position["yaw_rad"],
			}
		}
	}
	return phaseTimes, anchor
}

func summarizeInitializationSource(samples []timedPoseSample, bagStartSec float64, phaseTimes map[string]float64) map[string]any {
	row := map[string]any{
		"sample_count": len(samples),
	}
	if len(samples) == 0 {
		row["status"] = "missing"
		return row
	}
	row["status"] = "available"
	row["first"] = poseAtTimeRow(samples[0], samples[0], bagStartSec)
	for _, event := range []string{"takeoff", "hover_settle", "hover_hold"} {
		if eventTime := phaseTimes[event]; eventTime > 0 {
			row["at_"+event+"_start"] = nearestPoseRow(samples, eventTime, bagStartSec)
		}
	}
	return row
}

func summarizeExternalNavStatusTiming(samples []timedStatusSample, bagStartSec float64) map[string]any {
	return map[string]any{
		"sample_count":            len(samples),
		"first_sample_sec":        relTime(firstStatusTime(samples), bagStartSec),
		"first_ready_true_sec":    relTime(firstStatusWhere(samples, func(payload map[string]any) bool { ready, _ := payload["ready"].(bool); return ready }), bagStartSec),
		"first_healthy_state_sec": relTime(firstStatusWhere(samples, func(payload map[string]any) bool { state, _ := payload["state"].(string); return state == "healthy" }), bagStartSec),
		"latest":                  latestStatusPayload(samples),
	}
}

func summarizeMAVLinkExternalNavTiming(samples []timedStatusSample, bagStartSec float64) map[string]any {
	return map[string]any{
		"sample_count":                 len(samples),
		"first_sample_sec":             relTime(firstStatusTime(samples), bagStartSec),
		"first_sent_sec":               relTime(firstStatusWhere(samples, func(payload map[string]any) bool { return metricInt(payload, "sent_count") > 0 }), bagStartSec),
		"first_ready_true_sec":         relTime(firstStatusWhere(samples, func(payload map[string]any) bool { ready, _ := payload["ready"].(bool); return ready }), bagStartSec),
		"first_fcu_local_position_sec": relTime(firstStatusWhere(samples, func(payload map[string]any) bool { return metricInt(payload, "local_position_count") > 0 }), bagStartSec),
		"latest":                       latestStatusPayload(samples),
	}
}

func summarizeSlamStatusWindow(samples []timedStatusSample, startSec float64, endSec float64, bagStartSec float64) map[string]any {
	windowed := filterStatusWindow(samples, startSec, endSec)
	if len(windowed) == 0 {
		return map[string]any{
			"status":                          "missing_window_samples",
			"sample_count":                    0,
			"window_start_sec_from_bag_start": relTime(startSec, bagStartSec),
			"window_end_sec_from_bag_start":   relTime(endSec, bagStartSec),
		}
	}
	first := windowed[0].Payload
	last := windowed[len(windowed)-1].Payload
	return map[string]any{
		"status":                          "evaluated",
		"sample_count":                    len(windowed),
		"window_start_sec_from_bag_start": relTime(startSec, bagStartSec),
		"window_end_sec_from_bag_start":   relTime(endSec, bagStartSec),
		"first":                           first,
		"last":                            last,
		"scan_count_delta":                nestedMetricInt(last, "scan", "count") - nestedMetricInt(first, "scan", "count"),
		"imu_count_delta":                 nestedMetricInt(last, "imu", "count") - nestedMetricInt(first, "imu", "count"),
		"tf_count_delta":                  nestedMetricInt(last, "tf", "count") - nestedMetricInt(first, "tf", "count"),
		"tf_received_delta":               nestedMetricInt(last, "tf", "received_count") - nestedMetricInt(first, "tf", "received_count"),
		"tf_rejected_delta":               nestedMetricInt(last, "tf", "rejected_count") - nestedMetricInt(first, "tf", "rejected_count"),
		"odom_count_delta":                nestedMetricInt(last, "output", "odom_count") - nestedMetricInt(first, "output", "odom_count"),
		"last_tf_max_observed_jump_m":     nestedMetricFloat(last, "tf", "max_observed_jump_m"),
		"last_tf_max_accepted_jump_m":     nestedMetricFloat(last, "tf", "max_accepted_jump_m"),
		"last_tf_max_rejected_jump_m":     nestedMetricFloat(last, "tf", "max_rejected_jump_m"),
		"last_tf_rejection_ratio":         nestedMetricFloat(last, "tf", "rejection_ratio"),
	}
}

func summarizeMessageTiming(samples []timedMessageSample, startSec float64, endSec float64, bagStartSec float64) map[string]any {
	windowed := filterMessageWindow(samples, startSec, endSec)
	row := map[string]any{
		"sample_count":                    len(windowed),
		"raw_sample_count":                len(samples),
		"window_start_sec_from_bag_start": relTime(startSec, bagStartSec),
		"window_end_sec_from_bag_start":   relTime(endSec, bagStartSec),
	}
	if len(windowed) == 0 {
		row["status"] = "missing_window_samples"
		return row
	}
	row["status"] = "evaluated"
	duration := math.Max(0, endSec-startSec)
	row["duration_sec"] = duration
	if duration > 0 {
		row["rate_hz"] = float64(len(windowed)) / duration
	}
	row["first_sec_from_bag_start"] = relTime(windowed[0].LogTimeSec, bagStartSec)
	row["last_sec_from_bag_start"] = relTime(windowed[len(windowed)-1].LogTimeSec, bagStartSec)
	logIntervals := make([]float64, 0, len(windowed)-1)
	headerIntervals := make([]float64, 0, len(windowed)-1)
	headerStampCount := 0
	for idx, sample := range windowed {
		if sample.HeaderStampSec != nil {
			headerStampCount++
		}
		if idx == 0 {
			continue
		}
		logIntervals = append(logIntervals, sample.LogTimeSec-windowed[idx-1].LogTimeSec)
		if sample.HeaderStampSec != nil && windowed[idx-1].HeaderStampSec != nil {
			headerIntervals = append(headerIntervals, *sample.HeaderStampSec-*windowed[idx-1].HeaderStampSec)
		}
	}
	row["header_stamp_count"] = headerStampCount
	row["log_interval_sec"] = numberStats(logIntervals)
	if len(headerIntervals) > 0 {
		row["header_interval_sec"] = numberStats(headerIntervals)
	}
	return row
}

func summarizePoseJumps(samples []timedPoseSample, startSec float64, endSec float64, bagStartSec float64) map[string]any {
	if len(samples) < 2 || startSec == 0 || endSec == 0 || endSec <= startSec {
		return map[string]any{"sample_count": len(samples), "status": "insufficient_window"}
	}
	windowed := make([]timedPoseSample, 0, len(samples))
	for _, sample := range samples {
		if sample.LogTimeSec >= startSec && sample.LogTimeSec <= endSec {
			windowed = append(windowed, sample)
		}
	}
	if len(windowed) < 2 {
		return map[string]any{"sample_count": len(windowed), "status": "insufficient_samples"}
	}
	maxStep := 0.0
	maxYawStep := 0.0
	maxStepTime := 0.0
	maxYawTime := 0.0
	for idx := 1; idx < len(windowed); idx++ {
		prev := windowed[idx-1]
		cur := windowed[idx]
		step := math.Hypot(cur.X-prev.X, cur.Y-prev.Y)
		if step > maxStep {
			maxStep = step
			maxStepTime = cur.LogTimeSec
		}
		if prev.YawRad != nil && cur.YawRad != nil {
			yawStep := math.Abs(shortestAngleDeltaRadGo(*cur.YawRad, *prev.YawRad))
			if yawStep > maxYawStep {
				maxYawStep = yawStep
				maxYawTime = cur.LogTimeSec
			}
		}
	}
	return map[string]any{
		"status":                               "evaluated",
		"sample_count":                         len(windowed),
		"window_start_sec_from_bag_start":      relTime(startSec, bagStartSec),
		"window_end_sec_from_bag_start":        relTime(endSec, bagStartSec),
		"max_step_m":                           maxStep,
		"max_step_time_sec_from_bag_start":     relTime(maxStepTime, bagStartSec),
		"max_yaw_step_rad":                     maxYawStep,
		"max_yaw_step_time_sec_from_bag_start": relTime(maxYawTime, bagStartSec),
	}
}

func summarizePoseWindow(samples []timedPoseSample, startSec float64, endSec float64, bagStartSec float64) map[string]any {
	if len(samples) == 0 || startSec == 0 || endSec == 0 || endSec <= startSec {
		return map[string]any{"sample_count": 0, "status": "insufficient_window"}
	}
	windowed := make([]timedPoseSample, 0, len(samples))
	for _, sample := range samples {
		if sample.LogTimeSec >= startSec && sample.LogTimeSec <= endSec {
			windowed = append(windowed, sample)
		}
	}
	if len(windowed) == 0 {
		return map[string]any{
			"sample_count":                    0,
			"status":                          "missing_window_samples",
			"window_start_sec_from_bag_start": relTime(startSec, bagStartSec),
			"window_end_sec_from_bag_start":   relTime(endSec, bagStartSec),
		}
	}
	first := windowed[0]
	minX, maxX := math.Inf(1), math.Inf(-1)
	minY, maxY := math.Inf(1), math.Inf(-1)
	minZ, maxZ := math.Inf(1), math.Inf(-1)
	minYaw, maxYaw := math.Inf(1), math.Inf(-1)
	maxHorizontalDrift := 0.0
	yawCount := 0
	for _, sample := range windowed {
		dx := sample.X - first.X
		dy := sample.Y - first.Y
		maxHorizontalDrift = math.Max(maxHorizontalDrift, math.Hypot(dx, dy))
		minX, maxX = math.Min(minX, sample.X), math.Max(maxX, sample.X)
		minY, maxY = math.Min(minY, sample.Y), math.Max(maxY, sample.Y)
		minZ, maxZ = math.Min(minZ, sample.Z), math.Max(maxZ, sample.Z)
		if first.YawRad != nil && sample.YawRad != nil {
			yaw := shortestAngleDeltaRadGo(*sample.YawRad, *first.YawRad)
			minYaw, maxYaw = math.Min(minYaw, yaw), math.Max(maxYaw, yaw)
			yawCount++
		}
	}
	final := windowed[len(windowed)-1]
	row := map[string]any{
		"status":                          "evaluated",
		"sample_count":                    len(windowed),
		"window_start_sec_from_bag_start": relTime(startSec, bagStartSec),
		"window_end_sec_from_bag_start":   relTime(endSec, bagStartSec),
		"max_horizontal_drift_m":          maxHorizontalDrift,
		"x_span_m":                        maxX - minX,
		"y_span_m":                        maxY - minY,
		"z_span_m":                        maxZ - minZ,
		"final_x_delta_m":                 final.X - first.X,
		"final_y_delta_m":                 final.Y - first.Y,
		"final_horizontal_delta_m":        math.Hypot(final.X-first.X, final.Y-first.Y),
		"frame_id":                        first.FrameID,
		"child_frame_id":                  first.ChildFrameID,
	}
	if yawCount > 0 {
		row["yaw_span_rad"] = maxYaw - minYaw
	}
	return row
}

func poseAtTimeRow(reference timedPoseSample, sample timedPoseSample, bagStartSec float64) map[string]any {
	row := map[string]any{
		"time_sec_from_bag_start": relTime(sample.LogTimeSec, bagStartSec),
		"x_m":                     sample.X,
		"y_m":                     sample.Y,
		"z_m":                     sample.Z,
		"dx_from_first_m":         sample.X - reference.X,
		"dy_from_first_m":         sample.Y - reference.Y,
		"horizontal_from_first_m": math.Hypot(sample.X-reference.X, sample.Y-reference.Y),
		"frame_id":                sample.FrameID,
		"child_frame_id":          sample.ChildFrameID,
	}
	if sample.YawRad != nil {
		row["yaw_rad"] = *sample.YawRad
	}
	if reference.YawRad != nil && sample.YawRad != nil {
		row["yaw_delta_from_first_rad"] = shortestAngleDeltaRadGo(*sample.YawRad, *reference.YawRad)
	}
	return row
}

func nearestPoseRow(samples []timedPoseSample, eventTimeSec float64, bagStartSec float64) map[string]any {
	if len(samples) == 0 {
		return map[string]any{"status": "missing"}
	}
	best := samples[0]
	bestDelta := math.Abs(best.LogTimeSec - eventTimeSec)
	for _, sample := range samples[1:] {
		delta := math.Abs(sample.LogTimeSec - eventTimeSec)
		if delta < bestDelta {
			best = sample
			bestDelta = delta
		}
	}
	row := poseAtTimeRow(samples[0], best, bagStartSec)
	row["status"] = "nearest"
	row["event_time_sec_from_bag_start"] = relTime(eventTimeSec, bagStartSec)
	row["sample_time_delta_sec"] = best.LogTimeSec - eventTimeSec
	return row
}

func relPhaseTimes(phaseTimes map[string]float64, bagStartSec float64) map[string]any {
	out := map[string]any{}
	keys := make([]string, 0, len(phaseTimes))
	for key := range phaseTimes {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		out[key] = relTime(phaseTimes[key], bagStartSec)
	}
	return out
}

func relTime(value float64, bagStartSec float64) any {
	if value <= 0 || bagStartSec <= 0 {
		return nil
	}
	return value - bagStartSec
}

func firstStatusTime(samples []timedStatusSample) float64 {
	if len(samples) == 0 {
		return 0
	}
	return samples[0].LogTimeSec
}

func firstStatusWhere(samples []timedStatusSample, predicate func(map[string]any) bool) float64 {
	for _, sample := range samples {
		if predicate(sample.Payload) {
			return sample.LogTimeSec
		}
	}
	return 0
}

func filterStatusWindow(samples []timedStatusSample, startSec float64, endSec float64) []timedStatusSample {
	if startSec == 0 || endSec == 0 || endSec <= startSec {
		return nil
	}
	windowed := make([]timedStatusSample, 0, len(samples))
	for _, sample := range samples {
		if sample.LogTimeSec >= startSec && sample.LogTimeSec <= endSec {
			windowed = append(windowed, sample)
		}
	}
	return windowed
}

func filterMessageWindow(samples []timedMessageSample, startSec float64, endSec float64) []timedMessageSample {
	if startSec == 0 || endSec == 0 || endSec <= startSec {
		return nil
	}
	windowed := make([]timedMessageSample, 0, len(samples))
	for _, sample := range samples {
		if sample.LogTimeSec >= startSec && sample.LogTimeSec <= endSec {
			windowed = append(windowed, sample)
		}
	}
	return windowed
}

func lastHoverHoldTime(samples []timedStatusSample) float64 {
	last := 0.0
	for _, sample := range samples {
		phase, _ := sample.Payload["phase"].(string)
		if phase == "hover_hold" {
			last = sample.LogTimeSec
		}
	}
	return last
}

func latestStatusPayload(samples []timedStatusSample) map[string]any {
	if len(samples) == 0 {
		return nil
	}
	return samples[len(samples)-1].Payload
}

func nestedMetricInt(root map[string]any, key string, field string) int {
	return metricInt(mapFromAny(root[key]), field)
}

func nestedMetricFloat(root map[string]any, key string, field string) float64 {
	return metricFloat(mapFromAny(root[key]), field)
}

func initializationMissionSummary(summaryPath string) map[string]any {
	data, err := os.ReadFile(summaryPath)
	if err != nil {
		return map[string]any{"status": "missing_summary"}
	}
	var summary map[string]any
	if err := json.Unmarshal(data, &summary); err != nil {
		return map[string]any{"status": "invalid_summary"}
	}
	hoverMission := mapFromAny(mapFromAny(mapFromAny(summary["metrics"])["gate"])["hover_mission"])
	hoverDrift := mapFromAny(hoverMission["hover_drift"])
	return map[string]any{
		"status":                        summary["status"],
		"ok":                            summary["ok"],
		"blocked":                       summary["blocked"],
		"blocker_codes":                 summary["blockerCodes"],
		"mission_ok":                    hoverMission["ok"],
		"mission_reason":                hoverMission["reason"],
		"mission_phase_state":           hoverMission["mission_phase_state"],
		"hover_body_ok":                 hoverMission["hover_body_ok"],
		"horizontal_drift_m":            hoverDrift["horizontal_drift_m"],
		"horizontal_span_m":             hoverDrift["horizontal_span_m"],
		"external_nav_loss_sec":         hoverDrift["external_nav_loss_duration_sec"],
		"mavlink_external_nav_loss_sec": hoverDrift["mavlink_external_nav_loss_duration_sec"],
	}
}

func parseJSONStatusCDR(data []byte) (map[string]any, error) {
	payload, err := parseStdStringCDR(data)
	if err != nil {
		return nil, err
	}
	var status map[string]any
	if err := json.Unmarshal([]byte(payload), &status); err != nil {
		return nil, err
	}
	return status, nil
}

func parseHeaderStampSecCDR(data []byte) (float64, error) {
	cursor := gateCDRCursor{data: data}
	if err := cursor.skip(4); err != nil {
		return 0, err
	}
	sec, err := cursor.int32()
	if err != nil {
		return 0, err
	}
	nsec, err := cursor.uint32()
	if err != nil {
		return 0, err
	}
	return float64(sec) + (float64(nsec) / 1e9), nil
}

func parseOdometryPoseCDR(data []byte) (timedPoseSample, error) {
	cursor := gateCDRCursor{data: data}
	if err := cursor.skip(4); err != nil {
		return timedPoseSample{}, err
	}
	if _, err := cursor.int32(); err != nil {
		return timedPoseSample{}, err
	}
	if _, err := cursor.uint32(); err != nil {
		return timedPoseSample{}, err
	}
	frameID, err := cursor.stringValue()
	if err != nil {
		return timedPoseSample{}, err
	}
	childFrameID, err := cursor.stringValue()
	if err != nil {
		return timedPoseSample{}, err
	}
	x, err := cursor.float64()
	if err != nil {
		return timedPoseSample{}, err
	}
	y, err := cursor.float64()
	if err != nil {
		return timedPoseSample{}, err
	}
	z, err := cursor.float64()
	if err != nil {
		return timedPoseSample{}, err
	}
	yaw := parseOptionalYaw(&cursor)
	return timedPoseSample{X: x, Y: y, Z: z, YawRad: yaw, FrameID: frameID, ChildFrameID: childFrameID}, nil
}

func parsePoseStampedPoseCDR(data []byte) (timedPoseSample, error) {
	cursor := gateCDRCursor{data: data}
	if err := cursor.skip(4); err != nil {
		return timedPoseSample{}, err
	}
	if _, err := cursor.int32(); err != nil {
		return timedPoseSample{}, err
	}
	if _, err := cursor.uint32(); err != nil {
		return timedPoseSample{}, err
	}
	frameID, err := cursor.stringValue()
	if err != nil {
		return timedPoseSample{}, err
	}
	x, err := cursor.float64()
	if err != nil {
		return timedPoseSample{}, err
	}
	y, err := cursor.float64()
	if err != nil {
		return timedPoseSample{}, err
	}
	z, err := cursor.float64()
	if err != nil {
		return timedPoseSample{}, err
	}
	yaw := parseOptionalYaw(&cursor)
	return timedPoseSample{X: x, Y: y, Z: z, YawRad: yaw, FrameID: frameID}, nil
}

func parseOptionalYaw(cursor *gateCDRCursor) *float64 {
	x, err := cursor.float64()
	if err != nil {
		return nil
	}
	y, err := cursor.float64()
	if err != nil {
		return nil
	}
	z, err := cursor.float64()
	if err != nil {
		return nil
	}
	w, err := cursor.float64()
	if err != nil {
		return nil
	}
	yaw := math.Atan2(2.0*((w*z)+(x*y)), 1.0-(2.0*((y*y)+(z*z))))
	return &yaw
}

func shortestAngleDeltaRadGo(targetRad float64, currentRad float64) float64 {
	delta := targetRad - currentRad
	for delta > math.Pi {
		delta -= 2.0 * math.Pi
	}
	for delta < -math.Pi {
		delta += 2.0 * math.Pi
	}
	return delta
}
