package hover

import (
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"

	"github.com/foxglove/mcap/go/mcap"
	"github.com/klauspost/compress/zstd"
)

var hoverRawSourceChain = []struct {
	key   string
	topic string
}{
	{key: "slam_odom", topic: "/slam/odom"},
	{key: "scan_reference_drift_odom", topic: "/navlab/scan_reference_drift/odom"},
	{key: "slam_odom_corrected", topic: "/slam/odom_corrected"},
	{key: "external_nav_odom_candidate", topic: "/external_nav/odom_candidate"},
}

// BuildHoverRawSourceAudit builds a diagnostic-only pairwise audit directly from the hover rosbag.
// It does not affect runtime control input or gate acceptance.
func BuildHoverRawSourceAudit(artifactDir string) (map[string]any, error) {
	path := filepath.Join(artifactDir, "rosbag", "hover_rosbag", "hover_rosbag_0.mcap.zstd")
	if _, err := os.Stat(path); err != nil {
		path = filepath.Join(artifactDir, "rosbag", "hover_rosbag", "hover_rosbag_0.mcap")
	}
	return summarizeHoverRawSourceAudit(path)
}

func summarizeHoverRawSourceAudit(path string) (map[string]any, error) {
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

	byTopic := map[string]string{"/navlab/hover/status": "hover_status"}
	rawSamples := map[string][]timedXYSample{}
	for _, source := range hoverRawSourceChain {
		byTopic[source.topic] = source.key
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
		key, ok := byTopic[channel.Topic]
		if !ok {
			continue
		}
		if key == "hover_status" {
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
		sample, err := parseGazeboModelOdomCDR(message.Data)
		if err != nil {
			return nil, fmt.Errorf("parse %s: %w", channel.Topic, err)
		}
		rawSamples[key] = append(rawSamples[key], timedXYSample{
			X:            sample.X,
			Y:            sample.Y,
			Z:            sample.Z,
			FrameID:      sample.FrameID,
			ChildFrameID: sample.ChildFrameID,
			LogTimeSec:   float64(message.LogTime) / 1e9,
		})
	}

	windowSource := "full_bag_fallback"
	sources := map[string]any{}
	vectors := map[string][2]float64{}
	for _, source := range hoverRawSourceChain {
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
		summary := summarizeTimedXYSamples(
			source.topic,
			rawSamples[source.key],
			windowed,
			hoverStartSec,
			hoverEndSec,
			windowSource,
		)
		summary["comparison_frame"] = "raw_topic_xy"
		summary["comparison_final_x_m"] = metricFloat(summary, "final_x_m")
		summary["comparison_final_y_m"] = metricFloat(summary, "final_y_m")
		sources[source.key] = summary
		vectors[source.key] = [2]float64{metricFloat(summary, "final_x_m"), metricFloat(summary, "final_y_m")}
	}

	pairwise := map[string]any{}
	for leftIdx := 0; leftIdx < len(hoverRawSourceChain); leftIdx++ {
		for rightIdx := leftIdx + 1; rightIdx < len(hoverRawSourceChain); rightIdx++ {
			left := hoverRawSourceChain[leftIdx]
			right := hoverRawSourceChain[rightIdx]
			leftSummary := mapFromAny(sources[left.key])
			rightSummary := mapFromAny(sources[right.key])
			pairwise[left.key+"__"+right.key] = summarizeXYVectorPair(
				vectors[left.key],
				vectors[right.key],
				metricInt(leftSummary, "sample_count"),
				metricInt(rightSummary, "sample_count"),
			)
		}
	}
	divergence := firstRawChainDivergence(pairwise)
	return map[string]any{
		"schema":                           "navlab.hover_raw_source_audit.v1",
		"diagnostic_only":                  true,
		"runtime_control_unchanged":        true,
		"rosbag_path":                      path,
		"window_source":                    windowSource,
		"window_start_sec":                 hoverStartSec,
		"window_end_sec":                   hoverEndSec,
		"window_duration_sec":              math.Max(0, hoverEndSec-hoverStartSec),
		"sources":                          sources,
		"pairwise":                         pairwise,
		"first_raw_chain_divergence":       divergence,
		"correction_stage_classification":  classifyCorrectionStage(pairwise),
		"selector_contract_classification": classifySelectorContract(pairwise),
	}, nil
}

func firstRawChainDivergence(pairwise map[string]any) map[string]any {
	for idx := 0; idx < len(hoverRawSourceChain)-1; idx++ {
		left := hoverRawSourceChain[idx].key
		right := hoverRawSourceChain[idx+1].key
		pair := mapFromAny(pairwise[left+"__"+right])
		if reason := rawPairDivergenceReason(pair); reason != "" {
			return rawDivergenceMap("found", left, right, reason, pair)
		}
	}
	return map[string]any{
		"status": "not_found",
		"scope":  "raw_bag_chain",
		"note":   "No adjacent raw chain direction/scale divergence was found.",
	}
}

func classifyCorrectionStage(pairwise map[string]any) map[string]any {
	slamToScan := mapFromAny(pairwise["slam_odom__scan_reference_drift_odom"])
	slamToCorrected := mapFromAny(pairwise["slam_odom__slam_odom_corrected"])
	correctedToCandidate := mapFromAny(pairwise["slam_odom_corrected__external_nav_odom_candidate"])
	if reason := rawPairDivergenceReason(slamToScan); reason != "" {
		return rawDivergenceMap("pre_correction_disagreement", "slam_odom", "scan_reference_drift_odom", reason, slamToScan)
	}
	if reason := rawPairDivergenceReason(slamToCorrected); reason != "" {
		return rawDivergenceMap("correction_stage_changes_slam", "slam_odom", "slam_odom_corrected", reason, slamToCorrected)
	}
	if reason := rawPairDivergenceReason(correctedToCandidate); reason != "" {
		return rawDivergenceMap("post_correction_selector_divergence", "slam_odom_corrected", "external_nav_odom_candidate", reason, correctedToCandidate)
	}
	return map[string]any{
		"status": "no_raw_chain_divergence",
		"scope":  "raw_bag_chain",
	}
}

func classifySelectorContract(pairwise map[string]any) map[string]any {
	scanToCandidate := mapFromAny(pairwise["scan_reference_drift_odom__external_nav_odom_candidate"])
	correctedToCandidate := mapFromAny(pairwise["slam_odom_corrected__external_nav_odom_candidate"])
	scanDirectionOK := metricFloat(scanToCandidate, "direction_cosine") >= 0.50
	correctedDirectionOK := metricFloat(correctedToCandidate, "direction_cosine") >= 0.50
	if scanDirectionOK && !correctedDirectionOK {
		return map[string]any{
			"status":                          "candidate_direction_follows_scan_reference_not_corrected_slam",
			"scope":                           "raw_bag_chain",
			"scan_candidate_direction_cosine": metricFloat(scanToCandidate, "direction_cosine"),
			"scan_candidate_scale_ratio":      metricFloat(scanToCandidate, "scale_ratio"),
			"slam_candidate_direction_cosine": metricFloat(correctedToCandidate, "direction_cosine"),
			"slam_candidate_scale_ratio":      metricFloat(correctedToCandidate, "scale_ratio"),
			"note": "ExternalNav candidate direction is closer to scan-reference drift than to corrected SLAM. " +
				"This indicates the selector/candidate path is following scan-reference frame/sign semantics.",
		}
	}
	if correctedDirectionOK && !scanDirectionOK {
		return map[string]any{
			"status":                          "candidate_direction_follows_corrected_slam_not_scan_reference",
			"scope":                           "raw_bag_chain",
			"scan_candidate_direction_cosine": metricFloat(scanToCandidate, "direction_cosine"),
			"scan_candidate_scale_ratio":      metricFloat(scanToCandidate, "scale_ratio"),
			"slam_candidate_direction_cosine": metricFloat(correctedToCandidate, "direction_cosine"),
			"slam_candidate_scale_ratio":      metricFloat(correctedToCandidate, "scale_ratio"),
		}
	}
	if scanDirectionOK && correctedDirectionOK {
		return map[string]any{
			"status": "candidate_direction_agrees_with_both_scan_reference_and_corrected_slam",
			"scope":  "raw_bag_chain",
		}
	}
	return map[string]any{
		"status":                          "candidate_direction_disagrees_with_both_scan_reference_and_corrected_slam",
		"scope":                           "raw_bag_chain",
		"scan_candidate_direction_cosine": metricFloat(scanToCandidate, "direction_cosine"),
		"slam_candidate_direction_cosine": metricFloat(correctedToCandidate, "direction_cosine"),
	}
}

func rawPairDivergenceReason(pair map[string]any) string {
	if len(pair) == 0 {
		return "missing_pairwise"
	}
	if ok, _ := pair["sample_count_ok"].(bool); !ok {
		return "sample_count_not_ok"
	}
	if metricFloat(pair, "direction_cosine") < 0.50 {
		return "direction_mismatch"
	}
	if metricFloat(pair, "scale_ratio") < 0.50 {
		return "scale_mismatch"
	}
	return ""
}

func rawDivergenceMap(status string, left string, right string, reason string, pair map[string]any) map[string]any {
	return map[string]any{
		"status":            status,
		"scope":             "raw_bag_chain",
		"left":              left,
		"right":             right,
		"reason":            reason,
		"direction_cosine":  metricFloat(pair, "direction_cosine"),
		"scale_ratio":       metricFloat(pair, "scale_ratio"),
		"left_magnitude_m":  metricFloat(pair, "left_magnitude_m"),
		"right_magnitude_m": metricFloat(pair, "right_magnitude_m"),
	}
}
