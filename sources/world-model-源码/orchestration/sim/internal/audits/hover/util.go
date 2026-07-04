package hover

import (
	"encoding/binary"
	"encoding/json"
	"io"
	"math"
	"os"
	"regexp"
	"sort"
	"strings"
)

type gazeboOdomSample struct {
	X            float64
	Y            float64
	Z            float64
	FrameID      string
	ChildFrameID string
}

type timedXYSample struct {
	X            float64
	Y            float64
	Z            float64
	FrameID      string
	ChildFrameID string
	LogTimeSec   float64
}

type gateCDRCursor struct {
	data []byte
	off  int
}

func mapFromAny(value any) map[string]any {
	if value == nil {
		return nil
	}
	if typed, ok := value.(map[string]any); ok {
		return typed
	}
	return nil
}

func sliceFromAny(value any) []any {
	switch typed := value.(type) {
	case []any:
		return typed
	case []map[string]any:
		out := make([]any, 0, len(typed))
		for _, row := range typed {
			out = append(out, row)
		}
		return out
	default:
		return nil
	}
}

func subsetMap(source map[string]any, keys ...string) map[string]any {
	out := map[string]any{}
	for _, key := range keys {
		if value, ok := source[key]; ok {
			out[key] = value
		}
	}
	return out
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

func errorsIsEOF(err error) bool {
	return err == io.EOF
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

func cosine2D(ax float64, ay float64, bx float64, by float64) float64 {
	amag := math.Hypot(ax, ay)
	bmag := math.Hypot(bx, by)
	if amag < 1e-9 || bmag < 1e-9 {
		return 1.0
	}
	return ((ax * bx) + (ay * by)) / (amag * bmag)
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
