package hover

import (
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"sort"

	"github.com/foxglove/mcap/go/mcap"
	"github.com/klauspost/compress/zstd"
)

var hoverTrajectoryPoseTopics = []struct {
	key   string
	topic string
	kind  string
}{
	{key: "slam_odom", topic: "/slam/odom", kind: "odometry"},
	{key: "slam_odom_corrected", topic: "/slam/odom_corrected", kind: "odometry"},
	{key: "cartographer_odometry_input", topic: "/cartographer/odometry_input", kind: "odometry"},
	{key: "external_nav_odom_candidate", topic: "/external_nav/odom_candidate", kind: "odometry"},
	{key: "external_nav_odom", topic: "/external_nav/odom", kind: "odometry"},
	{key: "fcu_local_position_pose", topic: "/navlab/fcu/local_position_pose", kind: "pose_stamped"},
	{key: "gazebo_model_odometry", topic: "/gazebo/model/odometry", kind: "odometry"},
	{key: "scan_reference_drift_odom", topic: "/navlab/scan_reference_drift/odom", kind: "odometry"},
}

var hoverTrajectoryStatusTopics = map[string]string{
	"/navlab/hover/status":          "hover_status",
	"/navlab/fcu/controller/status": "fcu_controller_status",
	"/navlab/fcu/setpoint/output":   "fcu_setpoint_output",
	"/navlab/slam/status":           "slam_status",
}

// BuildHoverTrajectoryAudit builds a diagnostic-only time-aligned hover trajectory audit.
// It reads existing rosbag artifacts and never changes runtime control or gate behavior.
func BuildHoverTrajectoryAudit(artifactDir string) (map[string]any, error) {
	path := filepath.Join(artifactDir, "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd")
	if _, err := os.Stat(path); err != nil {
		path = filepath.Join(artifactDir, "rosbag", "hover_rosbag", "hover_rosbag_0.mcap")
	}
	return summarizeHoverTrajectoryAudit(path)
}

func summarizeHoverTrajectoryAudit(path string) (map[string]any, error) {
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

	poseTopicByName := map[string]struct {
		key  string
		kind string
	}{}
	poses := map[string][]timedPoseSample{}
	for _, spec := range hoverTrajectoryPoseTopics {
		poseTopicByName[spec.topic] = struct {
			key  string
			kind string
		}{key: spec.key, kind: spec.kind}
		poses[spec.key] = []timedPoseSample{}
	}
	statuses := map[string][]timedStatusSample{}
	for _, key := range hoverTrajectoryStatusTopics {
		statuses[key] = []timedStatusSample{}
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
		if spec, ok := poseTopicByName[channel.Topic]; ok {
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
			continue
		}
		if key, ok := hoverTrajectoryStatusTopics[channel.Topic]; ok {
			payload, err := parseJSONStatusCDR(message.Data)
			if err != nil {
				return nil, fmt.Errorf("parse %s: %w", channel.Topic, err)
			}
			statuses[key] = append(statuses[key], timedStatusSample{Payload: payload, LogTimeSec: stampSec})
		}
	}

	phaseTimes, hoverAnchor := summarizeHoverStatusTiming(statuses["hover_status"], bagStartSec)
	hoverStartSec := phaseTimes["hover_hold"]
	hoverEndSec := lastHoverHoldTime(statuses["hover_status"])
	windowSource := "hover_status_phase_hover_hold"
	if hoverStartSec == 0 || hoverEndSec <= hoverStartSec {
		hoverStartSec = bagStartSec
		hoverEndSec = bagEndSec
		windowSource = "full_bag_fallback"
	}

	references := map[string]timedPoseSample{}
	sourceSummaries := map[string]any{}
	for _, spec := range hoverTrajectoryPoseTopics {
		windowed := filterPoseWindow(poses[spec.key], hoverStartSec, hoverEndSec)
		sourceSummaries[spec.key] = summarizeTrajectorySource(spec.topic, poses[spec.key], windowed, hoverStartSec, hoverEndSec, bagStartSec, windowSource)
		if len(windowed) > 0 {
			references[spec.key] = windowed[0]
		} else if len(poses[spec.key]) > 0 {
			references[spec.key] = poses[spec.key][0]
		}
	}

	const binStepSec = 0.5
	const maxNearestAgeSec = 0.35
	timeline := buildTrajectoryTimeline(poses, references, statuses, hoverStartSec, hoverEndSec, bagStartSec, binStepSec, maxNearestAgeSec)
	peaks := map[string]any{}
	alignedAtPeaks := map[string]any{}
	for _, spec := range hoverTrajectoryPoseTopics {
		peak := trajectoryPeak(poses[spec.key], references[spec.key], hoverStartSec, hoverEndSec, bagStartSec)
		peaks[spec.key] = peak
		if metricFloat(peak, "time_sec_from_bag_start") > 0 {
			absPeakTime := bagStartSec + metricFloat(peak, "time_sec_from_bag_start")
			alignedAtPeaks[spec.key] = alignedTrajectoryRow(absPeakTime, poses, references, statuses, bagStartSec, maxNearestAgeSec)
		}
	}
	peakTimeAlignment := summarizePeakTimeAlignment(peaks, maxNearestAgeSec)

	pairwise := map[string]any{}
	for _, pair := range [][2]string{
		{"slam_odom", "gazebo_model_odometry"},
		{"external_nav_odom", "gazebo_model_odometry"},
		{"fcu_local_position_pose", "gazebo_model_odometry"},
		{"slam_odom", "external_nav_odom"},
		{"slam_odom", "fcu_local_position_pose"},
		{"external_nav_odom", "fcu_local_position_pose"},
	} {
		pairwise[pair[0]+"__"+pair[1]] = summarizeAlignedTrajectoryPair(
			poses[pair[0]],
			references[pair[0]],
			poses[pair[1]],
			references[pair[1]],
			hoverStartSec,
			hoverEndSec,
			binStepSec,
			maxNearestAgeSec,
		)
	}

	return map[string]any{
		"schema":                    "navlab.hover_trajectory_audit.v1",
		"diagnostic_only":           true,
		"runtime_control_unchanged": true,
		"rosbag_path":               path,
		"limitations": []string{
			"Cartographer local scan matching score is not present in the current rosbag/runtime log artifacts.",
			"Pose comparisons are time-aligned relative displacements inside the hover_hold window; they are not a frame-origin proof by themselves.",
		},
		"bag": map[string]any{
			"start_sec":    bagStartSec,
			"end_sec":      bagEndSec,
			"duration_sec": math.Max(0, bagEndSec-bagStartSec),
		},
		"window_source":                    windowSource,
		"hover_window_sec_from_bag_start":  map[string]any{"start": relTime(hoverStartSec, bagStartSec), "end": relTime(hoverEndSec, bagStartSec), "duration": math.Max(0, hoverEndSec-hoverStartSec)},
		"hover_anchor":                     hoverAnchor,
		"sources":                          sourceSummaries,
		"peaks":                            peaks,
		"peak_time_alignment":              peakTimeAlignment,
		"aligned_at_each_source_peak":      alignedAtPeaks,
		"pairwise_aligned_relative_motion": pairwise,
		"timeline_step_sec":                binStepSec,
		"timeline_max_nearest_age_sec":     maxNearestAgeSec,
		"timeline":                         timeline,
	}, nil
}

func summarizePeakTimeAlignment(peaks map[string]any, toleranceSec float64) map[string]any {
	sourceKeys := []string{
		"slam_odom",
		"external_nav_odom",
		"fcu_local_position_pose",
		"gazebo_model_odometry",
		"scan_reference_drift_odom",
	}
	sources := map[string]any{}
	for _, key := range sourceKeys {
		peak := mapFromAny(peaks[key])
		status := "missing"
		if peak != nil {
			status, _ = peak["status"].(string)
		}
		sources[key] = map[string]any{
			"status":                         status,
			"sample_count":                   metricInt(peak, "sample_count"),
			"peak_time_sec_from_bag_start":   metricFloat(peak, "time_sec_from_bag_start"),
			"peak_dx_m":                      metricFloat(peak, "dx_m"),
			"peak_dy_m":                      metricFloat(peak, "dy_m"),
			"peak_horizontal_m":              metricFloat(peak, "horizontal_m"),
			"has_evaluated_peak":             status == "evaluated",
			"time_basis":                     "rosbag_log_time_sec",
			"relative_vector_reference_rule": "first sample in hover window, or first available source sample when the hover window is empty",
		}
	}

	pairs := map[string]any{}
	for leftIdx := 0; leftIdx < len(sourceKeys); leftIdx++ {
		for rightIdx := leftIdx + 1; rightIdx < len(sourceKeys); rightIdx++ {
			leftKey := sourceKeys[leftIdx]
			rightKey := sourceKeys[rightIdx]
			pairs[leftKey+"__"+rightKey] = summarizePeakTimePair(peaks, leftKey, rightKey, toleranceSec)
		}
	}
	return map[string]any{
		"schema":              "navlab.hover_peak_time_alignment.v1",
		"diagnostic_only":     true,
		"tolerance_sec":       toleranceSec,
		"sign_deadband_m":     0.02,
		"time_basis":          "rosbag_log_time_sec",
		"sources":             sources,
		"pairwise_peak_delta": pairs,
		"interpretation":      "Peak-time and direction disagreement is observation-contract evidence only; it is not a runtime gate by itself.",
	}
}

func summarizePeakTimePair(peaks map[string]any, leftKey string, rightKey string, toleranceSec float64) map[string]any {
	left := mapFromAny(peaks[leftKey])
	right := mapFromAny(peaks[rightKey])
	leftStatus, _ := left["status"].(string)
	rightStatus, _ := right["status"].(string)
	if leftStatus != "evaluated" || rightStatus != "evaluated" {
		return map[string]any{
			"status":       "insufficient_peak_evidence",
			"left_status":  leftStatus,
			"right_status": rightStatus,
		}
	}
	leftTime := metricFloat(left, "time_sec_from_bag_start")
	rightTime := metricFloat(right, "time_sec_from_bag_start")
	leftVec := [2]float64{metricFloat(left, "dx_m"), metricFloat(left, "dy_m")}
	rightVec := [2]float64{metricFloat(right, "dx_m"), metricFloat(right, "dy_m")}
	row := summarizeXYVectorPair(leftVec, rightVec, metricInt(left, "sample_count"), metricInt(right, "sample_count"))
	peakDelta := math.Abs(leftTime - rightTime)
	row["status"] = "evaluated"
	row["left_source"] = leftKey
	row["right_source"] = rightKey
	row["left_peak_time_sec_from_bag_start"] = leftTime
	row["right_peak_time_sec_from_bag_start"] = rightTime
	row["peak_time_delta_sec"] = peakDelta
	row["within_tolerance"] = peakDelta <= toleranceSec
	row["left_peak_dx_m"] = leftVec[0]
	row["left_peak_dy_m"] = leftVec[1]
	row["right_peak_dx_m"] = rightVec[0]
	row["right_peak_dy_m"] = rightVec[1]
	row["sign_agreement"] = row["x_sign_agreement"] == true && row["y_sign_agreement"] == true
	row["opposite_direction_suspected"] = metricFloat(row, "direction_cosine") < -0.5
	return row
}

func filterPoseWindow(samples []timedPoseSample, startSec float64, endSec float64) []timedPoseSample {
	if startSec == 0 || endSec == 0 || endSec <= startSec {
		return nil
	}
	windowed := make([]timedPoseSample, 0, len(samples))
	for _, sample := range samples {
		if sample.LogTimeSec >= startSec && sample.LogTimeSec <= endSec {
			windowed = append(windowed, sample)
		}
	}
	return windowed
}

func summarizeTrajectorySource(topic string, raw []timedPoseSample, windowed []timedPoseSample, startSec float64, endSec float64, bagStartSec float64, windowSource string) map[string]any {
	row := summarizePoseWindow(raw, startSec, endSec, bagStartSec)
	row["source_topic"] = topic
	row["raw_sample_count"] = len(raw)
	row["window_source"] = windowSource
	row["window_start_sec_from_bag_start"] = relTime(startSec, bagStartSec)
	row["window_end_sec_from_bag_start"] = relTime(endSec, bagStartSec)
	if len(windowed) > 0 {
		row["first_time_sec_from_bag_start"] = relTime(windowed[0].LogTimeSec, bagStartSec)
		row["last_time_sec_from_bag_start"] = relTime(windowed[len(windowed)-1].LogTimeSec, bagStartSec)
	}
	return row
}

func buildTrajectoryTimeline(
	poses map[string][]timedPoseSample,
	references map[string]timedPoseSample,
	statuses map[string][]timedStatusSample,
	startSec float64,
	endSec float64,
	bagStartSec float64,
	stepSec float64,
	maxAgeSec float64,
) []map[string]any {
	if startSec == 0 || endSec <= startSec || stepSec <= 0 {
		return nil
	}
	rows := []map[string]any{}
	for t := startSec; t <= endSec+1e-6; t += stepSec {
		row := alignedTrajectoryRow(t, poses, references, statuses, bagStartSec, maxAgeSec)
		row["time_sec_from_hover_start"] = t - startSec
		rows = append(rows, row)
	}
	return rows
}

func alignedTrajectoryRow(
	timeSec float64,
	poses map[string][]timedPoseSample,
	references map[string]timedPoseSample,
	statuses map[string][]timedStatusSample,
	bagStartSec float64,
	maxAgeSec float64,
) map[string]any {
	row := map[string]any{
		"time_sec_from_bag_start": relTime(timeSec, bagStartSec),
		"sources":                 map[string]any{},
		"statuses":                map[string]any{},
	}
	sourceRows := mapFromAny(row["sources"])
	for _, spec := range hoverTrajectoryPoseTopics {
		sourceRows[spec.key] = nearestRelativePoseRow(poses[spec.key], references[spec.key], timeSec, bagStartSec, maxAgeSec)
	}
	statusRows := mapFromAny(row["statuses"])
	for _, spec := range []struct {
		key    string
		fields []string
	}{
		{key: "hover_status", fields: []string{"phase", "reason", "setpoints_sent_count", "local_position_count", "position"}},
		{key: "fcu_controller_status", fields: []string{"ready", "state", "pose_samples", "control_route", "cmd_vel_publish_count", "mavlink_setpoint_count", "mavlink_setpoint_error", "mavlink_local_position_count"}},
		{key: "fcu_setpoint_output", fields: []string{"ready", "state", "setpoint_intent_samples", "cmd_vel_publish_count", "mavlink_setpoint_count", "mavlink_setpoint_error", "mavlink_local_position_count", "path_length_m", "min_path_length_m"}},
		{key: "slam_status", fields: []string{"state", "ready", "reason", "scan", "imu", "tf", "output"}},
	} {
		statusRows[spec.key] = nearestStatusSubsetRow(statuses[spec.key], timeSec, bagStartSec, maxAgeSec, spec.fields...)
	}
	return row
}

func nearestRelativePoseRow(samples []timedPoseSample, reference timedPoseSample, timeSec float64, bagStartSec float64, maxAgeSec float64) map[string]any {
	if len(samples) == 0 || reference.LogTimeSec == 0 {
		return map[string]any{"status": "missing"}
	}
	sample, age, ok := nearestPoseSample(samples, timeSec)
	if !ok {
		return map[string]any{"status": "missing"}
	}
	row := map[string]any{
		"status":                         "nearest",
		"sample_time_sec_from_bag_start": relTime(sample.LogTimeSec, bagStartSec),
		"sample_age_sec":                 age,
		"fresh":                          math.Abs(age) <= maxAgeSec,
		"x_m":                            sample.X,
		"y_m":                            sample.Y,
		"z_m":                            sample.Z,
		"dx_m":                           sample.X - reference.X,
		"dy_m":                           sample.Y - reference.Y,
		"dz_m":                           sample.Z - reference.Z,
		"horizontal_m":                   math.Hypot(sample.X-reference.X, sample.Y-reference.Y),
		"frame_id":                       sample.FrameID,
		"child_frame_id":                 sample.ChildFrameID,
	}
	if sample.YawRad != nil {
		row["yaw_rad"] = *sample.YawRad
	}
	if reference.YawRad != nil && sample.YawRad != nil {
		row["yaw_delta_rad"] = shortestAngleDeltaRadGo(*sample.YawRad, *reference.YawRad)
	}
	return row
}

func nearestPoseSample(samples []timedPoseSample, timeSec float64) (timedPoseSample, float64, bool) {
	if len(samples) == 0 {
		return timedPoseSample{}, 0, false
	}
	best := samples[0]
	bestAbsDelta := math.Abs(best.LogTimeSec - timeSec)
	for _, sample := range samples[1:] {
		delta := math.Abs(sample.LogTimeSec - timeSec)
		if delta < bestAbsDelta {
			best = sample
			bestAbsDelta = delta
		}
	}
	return best, best.LogTimeSec - timeSec, true
}

func nearestStatusSubsetRow(samples []timedStatusSample, timeSec float64, bagStartSec float64, maxAgeSec float64, fields ...string) map[string]any {
	if len(samples) == 0 {
		return map[string]any{"status": "missing"}
	}
	best := samples[0]
	bestAbsDelta := math.Abs(best.LogTimeSec - timeSec)
	for _, sample := range samples[1:] {
		delta := math.Abs(sample.LogTimeSec - timeSec)
		if delta < bestAbsDelta {
			best = sample
			bestAbsDelta = delta
		}
	}
	age := best.LogTimeSec - timeSec
	row := subsetMap(best.Payload, fields...)
	row["status"] = "nearest"
	row["sample_time_sec_from_bag_start"] = relTime(best.LogTimeSec, bagStartSec)
	row["sample_age_sec"] = age
	row["fresh"] = math.Abs(age) <= maxAgeSec
	return row
}

func trajectoryPeak(samples []timedPoseSample, reference timedPoseSample, startSec float64, endSec float64, bagStartSec float64) map[string]any {
	if len(samples) == 0 || reference.LogTimeSec == 0 || startSec == 0 || endSec <= startSec {
		return map[string]any{"status": "missing"}
	}
	peakSample := timedPoseSample{}
	peak := -1.0
	count := 0
	for _, sample := range samples {
		if sample.LogTimeSec < startSec || sample.LogTimeSec > endSec {
			continue
		}
		count++
		dx := sample.X - reference.X
		dy := sample.Y - reference.Y
		horizontal := math.Hypot(dx, dy)
		if horizontal > peak {
			peak = horizontal
			peakSample = sample
		}
	}
	if count == 0 {
		return map[string]any{"status": "missing_window_samples"}
	}
	return map[string]any{
		"status":                  "evaluated",
		"sample_count":            count,
		"time_sec_from_bag_start": relTime(peakSample.LogTimeSec, bagStartSec),
		"dx_m":                    peakSample.X - reference.X,
		"dy_m":                    peakSample.Y - reference.Y,
		"horizontal_m":            peak,
	}
}

func summarizeAlignedTrajectoryPair(
	left []timedPoseSample,
	leftReference timedPoseSample,
	right []timedPoseSample,
	rightReference timedPoseSample,
	startSec float64,
	endSec float64,
	stepSec float64,
	maxAgeSec float64,
) map[string]any {
	if len(left) == 0 || len(right) == 0 || leftReference.LogTimeSec == 0 || rightReference.LogTimeSec == 0 || startSec == 0 || endSec <= startSec {
		return map[string]any{"status": "insufficient_samples"}
	}
	count := 0
	maxDifference := 0.0
	sumDifference := 0.0
	sumSquaredDifference := 0.0
	differences := []float64{}
	leftPath := 0.0
	rightPath := 0.0
	var previousLeft [2]float64
	var previousRight [2]float64
	hasPrevious := false
	var finalLeft [2]float64
	var finalRight [2]float64
	for t := startSec; t <= endSec+1e-6; t += stepSec {
		leftSample, leftAge, leftOK := nearestPoseSample(left, t)
		rightSample, rightAge, rightOK := nearestPoseSample(right, t)
		if !leftOK || !rightOK || math.Abs(leftAge) > maxAgeSec || math.Abs(rightAge) > maxAgeSec {
			continue
		}
		leftVec := [2]float64{leftSample.X - leftReference.X, leftSample.Y - leftReference.Y}
		rightVec := [2]float64{rightSample.X - rightReference.X, rightSample.Y - rightReference.Y}
		diff := math.Hypot(leftVec[0]-rightVec[0], leftVec[1]-rightVec[1])
		maxDifference = math.Max(maxDifference, diff)
		sumDifference += diff
		sumSquaredDifference += diff * diff
		differences = append(differences, diff)
		if hasPrevious {
			leftPath += math.Hypot(leftVec[0]-previousLeft[0], leftVec[1]-previousLeft[1])
			rightPath += math.Hypot(rightVec[0]-previousRight[0], rightVec[1]-previousRight[1])
		}
		previousLeft = leftVec
		previousRight = rightVec
		finalLeft = leftVec
		finalRight = rightVec
		hasPrevious = true
		count++
	}
	if count == 0 {
		return map[string]any{"status": "no_aligned_samples"}
	}
	row := summarizeXYVectorPair(finalLeft, finalRight, count, count)
	row["status"] = "evaluated"
	row["aligned_sample_count"] = count
	row["p50_relative_vector_difference_m"] = percentileFloat64(differences, 0.50)
	row["p90_relative_vector_difference_m"] = percentileFloat64(differences, 0.90)
	row["p95_relative_vector_difference_m"] = percentileFloat64(differences, 0.95)
	row["p99_relative_vector_difference_m"] = percentileFloat64(differences, 0.99)
	row["mean_relative_vector_difference_m"] = sumDifference / float64(count)
	row["rms_relative_vector_difference_m"] = math.Sqrt(sumSquaredDifference / float64(count))
	row["max_relative_vector_difference_m"] = maxDifference
	row["final_signed_x_error_m"] = finalLeft[0] - finalRight[0]
	row["final_signed_y_error_m"] = finalLeft[1] - finalRight[1]
	row["left_relative_path_length_m"] = leftPath
	row["right_relative_path_length_m"] = rightPath
	row["relative_path_length_ratio"] = 0.0
	if leftPath > 1e-9 && rightPath > 1e-9 {
		row["relative_path_length_ratio"] = math.Min(leftPath, rightPath) / math.Max(leftPath, rightPath)
	}
	return row
}

func percentileFloat64(values []float64, percentile float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sorted := append([]float64(nil), values...)
	sort.Float64s(sorted)
	if percentile <= 0 {
		return sorted[0]
	}
	if percentile >= 1 {
		return sorted[len(sorted)-1]
	}
	position := percentile * float64(len(sorted)-1)
	lower := int(math.Floor(position))
	upper := int(math.Ceil(position))
	if lower == upper {
		return sorted[lower]
	}
	weight := position - float64(lower)
	return sorted[lower]*(1-weight) + sorted[upper]*weight
}
