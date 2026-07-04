package hover

import (
	"math"
	"os"
	"path/filepath"
	"testing"

	"github.com/foxglove/mcap/go/mcap"
)

func TestSummarizeHoverRawSourceAuditClassifiesPreCorrectionDisagreement(t *testing.T) {
	path := filepath.Join(t.TempDir(), "hover_rosbag_0.mcap")
	writeRawSourceAuditMCAP(t, path)

	audit, err := summarizeHoverRawSourceAudit(path)
	if err != nil {
		t.Fatal(err)
	}
	if diagnosticOnly, _ := audit["diagnostic_only"].(bool); !diagnosticOnly {
		t.Fatalf("audit must be diagnostic-only: %#v", audit)
	}
	sources := mapFromAny(audit["sources"])
	for _, key := range []string{
		"slam_odom",
		"scan_reference_drift_odom",
		"slam_odom_corrected",
		"external_nav_odom_candidate",
	} {
		source := mapFromAny(sources[key])
		if got := metricInt(source, "sample_count"); got != 3 {
			t.Fatalf("%s sample_count = %d, want 3: %#v", key, got, source)
		}
	}
	pairwise := mapFromAny(audit["pairwise"])
	preCorrection := mapFromAny(pairwise["slam_odom__scan_reference_drift_odom"])
	if got := metricFloat(preCorrection, "direction_cosine"); math.Abs(got+1.0) > 1e-9 {
		t.Fatalf("slam vs scan cosine = %v, want -1: %#v", got, preCorrection)
	}
	correctionToCandidate := mapFromAny(pairwise["slam_odom_corrected__external_nav_odom_candidate"])
	if got := metricFloat(correctionToCandidate, "direction_cosine"); math.Abs(got+1.0) > 1e-9 {
		t.Fatalf("corrected vs candidate cosine = %v, want -1: %#v", got, correctionToCandidate)
	}
	classification := mapFromAny(audit["correction_stage_classification"])
	if got, _ := classification["status"].(string); got != "pre_correction_disagreement" {
		t.Fatalf("classification = %#v, want pre_correction_disagreement", classification)
	}
	if got, _ := classification["left"].(string); got != "slam_odom" {
		t.Fatalf("classification left = %q, want slam_odom", got)
	}
	if got, _ := classification["right"].(string); got != "scan_reference_drift_odom" {
		t.Fatalf("classification right = %q, want scan_reference_drift_odom", got)
	}
	selectorContract := mapFromAny(audit["selector_contract_classification"])
	if got, _ := selectorContract["status"].(string); got != "candidate_direction_follows_scan_reference_not_corrected_slam" {
		t.Fatalf(
			"selector contract = %#v, want candidate_direction_follows_scan_reference_not_corrected_slam",
			selectorContract,
		)
	}
}

func writeRawSourceAuditMCAP(t *testing.T, path string) {
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
	odomSchema := &mcap.Schema{
		ID:       1,
		Name:     "nav_msgs/msg/Odometry",
		Encoding: "ros2msg",
		Data:     []byte("std_msgs/Header header\nstring child_frame_id\n"),
	}
	stringSchema := &mcap.Schema{ID: 2, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}
	for _, schema := range []*mcap.Schema{odomSchema, stringSchema} {
		if err := writer.WriteSchema(schema); err != nil {
			t.Fatal(err)
		}
	}
	channels := []*mcap.Channel{
		{ID: 1, SchemaID: 1, Topic: "/slam/odom", MessageEncoding: "cdr"},
		{ID: 2, SchemaID: 1, Topic: "/navlab/scan_reference_drift/odom", MessageEncoding: "cdr"},
		{ID: 3, SchemaID: 1, Topic: "/slam/odom_corrected", MessageEncoding: "cdr"},
		{ID: 4, SchemaID: 1, Topic: "/external_nav/odom_candidate", MessageEncoding: "cdr"},
		{ID: 5, SchemaID: 2, Topic: "/navlab/hover/status", MessageEncoding: "cdr"},
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
	writeMsg(5, 10, gateTestStringCDR(`{"phase":"hover_hold"}`))
	for idx := 10; idx <= 12; idx++ {
		dx := 0.1 * float64(idx-10)
		writeMsg(1, uint64(idx), gateTestOdometryCDR(dx, 0, 0))
		writeMsg(2, uint64(idx), gateTestOdometryCDR(-dx, 0, 0))
		writeMsg(3, uint64(idx), gateTestOdometryCDR(dx, 0, 0))
		writeMsg(4, uint64(idx), gateTestOdometryCDR(-dx, 0, 0))
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}
