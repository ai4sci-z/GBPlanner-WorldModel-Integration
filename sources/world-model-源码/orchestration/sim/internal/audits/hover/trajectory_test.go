package hover

import "testing"

func TestSummarizePeakTimeAlignmentDetectsOppositeDirectionPeaks(t *testing.T) {
	peaks := map[string]any{
		"slam_odom": map[string]any{
			"status":                  "evaluated",
			"sample_count":            5,
			"time_sec_from_bag_start": 12.0,
			"dx_m":                    0.12,
			"dy_m":                    0.01,
			"horizontal_m":            0.1204,
		},
		"gazebo_model_odometry": map[string]any{
			"status":                  "evaluated",
			"sample_count":            5,
			"time_sec_from_bag_start": 12.2,
			"dx_m":                    -0.11,
			"dy_m":                    -0.01,
			"horizontal_m":            0.1104,
		},
	}

	alignment := summarizePeakTimeAlignment(peaks, 0.35)
	pairs := mapFromAny(alignment["pairwise_peak_delta"])
	pair := mapFromAny(pairs["slam_odom__gazebo_model_odometry"])
	if pair["status"] != "evaluated" {
		t.Fatalf("pair status = %#v", pair)
	}
	if pair["within_tolerance"] != true {
		t.Fatalf("expected peak times to be aligned within tolerance: %#v", pair)
	}
	if pair["opposite_direction_suspected"] != true {
		t.Fatalf("expected opposite-direction suspicion: %#v", pair)
	}
	if pair["sign_agreement"] != false {
		t.Fatalf("expected sign disagreement: %#v", pair)
	}
	if got := metricFloat(pair, "direction_cosine"); got > -0.9 {
		t.Fatalf("direction cosine = %v, want strong negative; pair=%#v", got, pair)
	}

	sources := mapFromAny(alignment["sources"])
	scanReference := mapFromAny(sources["scan_reference_drift_odom"])
	if scanReference["has_evaluated_peak"] != false {
		t.Fatalf("missing scan-reference peak should remain explicit: %#v", scanReference)
	}
}
