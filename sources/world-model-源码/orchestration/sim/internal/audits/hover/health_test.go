package hover

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
)

func TestHoverMetricSpecClassifyUsesTargetHardCapAndReviewOnly(t *testing.T) {
	spec := HoverMetricSpec{Key: "pair.slam_vs_external_nav.p95_error_m", Unit: "m", Tier: HoverTierARealFlightSafety, TargetMax: 0.10, HardMax: 0.15}
	if got := spec.Classify(0.08); got.Band != HoverHealthGreen || got.Severity != HoverMetricInfo {
		t.Fatalf("green classify = %#v", got)
	}
	if got := spec.Classify(0.12); got.Band != HoverHealthYellow || got.Severity != HoverMetricWarning {
		t.Fatalf("yellow classify = %#v", got)
	}
	if got := spec.Classify(0.16); got.Band != HoverHealthRed || got.Severity != HoverMetricHard {
		t.Fatalf("red classify = %#v", got)
	}

	reviewSpec := spec
	reviewSpec.Key = "pair.gazebo_vs_slam.p95_error_m"
	reviewSpec.Tier = HoverTierBReviewOnly
	reviewSpec.ReviewOnly = true
	if got := reviewSpec.Classify(0.16); got.Band != HoverHealthYellow || got.Severity != HoverMetricWarning || !got.ReviewOnly {
		t.Fatalf("review-only classify = %#v", got)
	}
}

func TestBuildHoverHealthAuditClassifiesGazeboOnlyBlockerAsYellow(t *testing.T) {
	dir := writeHoverHealthArtifact(t, []map[string]any{{"code": "hover_gazebo_model_horizontal_drift", "message": "review drift high"}})
	audit, err := BuildHoverHealthAudit(dir)
	if err != nil {
		t.Fatal(err)
	}
	if audit.HealthBand != HoverHealthYellow {
		t.Fatalf("health band = %s, want yellow; audit=%#v", audit.HealthBand, audit)
	}
	if len(audit.HardBlockers) != 0 {
		t.Fatalf("hard blockers = %#v, want none", audit.HardBlockers)
	}
	if len(audit.ReviewOnlyFindings) == 0 {
		t.Fatalf("review-only findings missing; audit=%#v", audit)
	}
	if audit.Proceed.SimAutoContinueAllowed || audit.Proceed.RealOperatorConfirmAllowed {
		t.Fatalf("yellow proceed should not continue/confirm: %#v", audit.Proceed)
	}
}

func TestBuildHoverHealthAuditClassifiesSafetyBlockerAsRed(t *testing.T) {
	dir := writeHoverHealthArtifact(t, []map[string]any{{"code": "external_nav_loss_after_airborne", "message": "loss exceeded grace"}})
	audit, err := BuildHoverHealthAudit(dir)
	if err != nil {
		t.Fatal(err)
	}
	if audit.HealthBand != HoverHealthRed {
		t.Fatalf("health band = %s, want red; audit=%#v", audit.HealthBand, audit)
	}
	if len(audit.HardBlockers) == 0 {
		t.Fatalf("hard blockers missing; audit=%#v", audit)
	}
	if audit.Proceed.SimAutoContinueAllowed || audit.Proceed.RealOperatorConfirmAllowed {
		t.Fatalf("red proceed should not continue/confirm: %#v", audit.Proceed)
	}
}

func TestBuildHoverHealthCohortAggregatesRunBandsAndMetrics(t *testing.T) {
	greenish := writeHoverHealthArtifact(t, nil)
	yellow := writeHoverHealthArtifact(t, []map[string]any{{"code": "hover_gazebo_model_horizontal_drift"}})
	cohort, err := BuildHoverHealthCohort([]string{greenish, yellow})
	if err != nil {
		t.Fatal(err)
	}
	if cohort.SampleSize != 2 || cohort.SampleSizeRule != "case_study_only" {
		t.Fatalf("sample metadata = %#v", cohort)
	}
	if cohort.BandCounts[string(HoverHealthYellow)] == 0 {
		t.Fatalf("yellow band count missing: %#v", cohort.BandCounts)
	}
	if len(cohort.Metrics) == 0 {
		t.Fatalf("cohort metrics missing: %#v", cohort)
	}
}

func TestBuildHoverHealthCohortAggregatesMissionHoverSpanPercentiles(t *testing.T) {
	runA := writeHoverHealthArtifact(t, nil)
	writeMissionHoverSpan(t, runA, 0.103)
	runB := writeHoverHealthArtifact(t, nil)
	writeMissionHoverSpan(t, runB, 0.118)
	runC := writeHoverHealthArtifact(t, nil)
	writeMissionHoverSpan(t, runC, 0.034)

	cohort, err := BuildHoverHealthCohort([]string{runA, runB, runC})
	if err != nil {
		t.Fatal(err)
	}
	metric := mapFromAny(cohort.Metrics["mission_hover_horizontal_span_m"])
	if metric == nil {
		t.Fatalf("mission hover span metric missing: %#v", cohort.Metrics)
	}
	if got := metricInt(metric, "target_exceed_count"); got != 2 {
		t.Fatalf("target_exceed_count = %d, want 2; metric=%#v", got, metric)
	}
	if got := metricInt(metric, "hard_cap_exceed_count"); got != 0 {
		t.Fatalf("hard_cap_exceed_count = %d, want 0; metric=%#v", got, metric)
	}
	if got := metricFloat(metric, "target_exceed_rate"); got < 0.66 || got > 0.67 {
		t.Fatalf("target_exceed_rate = %v, want 2/3; metric=%#v", got, metric)
	}
}

func TestBuildHoverHealthCohortKeepsTraceLinksAndExcludesPreflightFromSpan(t *testing.T) {
	validA := writeHoverHealthArtifact(t, nil)
	writeMissionHoverSpan(t, validA, 0.05)
	validB := writeHoverHealthArtifact(t, nil)
	writeMissionHoverSpan(t, validB, 0.12)
	preflight := writeHoverHealthArtifact(t, []map[string]any{{"code": "preflight_timeout", "message": "rangefinder not ready"}})
	if err := os.Remove(filepath.Join(preflight, "mission_summary.json")); err != nil {
		t.Fatal(err)
	}
	writeStartupReadinessRuntimeArtifact(t, preflight, "fail_fast", "startup_readiness_no_progress")

	cohort, err := BuildHoverHealthCohort([]string{validA, validB, preflight})
	if err != nil {
		t.Fatal(err)
	}
	metric := mapFromAny(cohort.Metrics["mission_hover_horizontal_span_m"])
	if metric == nil {
		t.Fatalf("mission hover span metric missing: %#v", cohort.Metrics)
	}
	if got := metricInt(metric, "count"); got != 2 {
		t.Fatalf("span metric count = %d, want only valid mission span samples; metric=%#v", got, metric)
	}
	if got := metricInt(metric, "target_exceed_count"); got != 1 {
		t.Fatalf("target_exceed_count = %d, want 1; metric=%#v", got, metric)
	}
	if len(cohort.Runs) != 3 {
		t.Fatalf("run count = %d, want 3", len(cohort.Runs))
	}
	preflightRow := mapFromAny(cohort.Runs[2])
	if _, ok := preflightRow["mission_hover_span"]; ok {
		t.Fatalf("preflight row should not carry mission hover span: %#v", preflightRow)
	}
	for _, key := range []string{
		"summary_artifact",
		"mission_summary_artifact",
		"hover_health_artifact",
		"contract_audit_artifact",
		"trajectory_audit_artifact",
	} {
		if preflightRow[key] == "" {
			t.Fatalf("run row missing trace link %s: %#v", key, preflightRow)
		}
	}
	if preflightRow["startup_readiness_policy_outcome"] != "fail_fast:startup_readiness_no_progress" {
		t.Fatalf("preflight startup readiness outcome = %#v", preflightRow)
	}
	outcomes := mapFromAny(cohort.Metrics["startup_readiness_policy_outcomes"])
	counts, _ := outcomes["counts"].(map[string]int)
	if counts["fail_fast:startup_readiness_no_progress"] != 1 {
		t.Fatalf("startup policy outcome counts = %#v", outcomes)
	}
}

func writeHoverHealthArtifact(t *testing.T, blockers []map[string]any) string {
	t.Helper()
	dir := t.TempDir()
	bagDir := filepath.Join(dir, "rosbag", "hover_rosbag")
	if err := os.MkdirAll(bagDir, 0o755); err != nil {
		t.Fatal(err)
	}
	writeHoverInitializationAuditMCAP(t, filepath.Join(bagDir, "hover_rosbag_0.mcap"))
	summary := map[string]any{"ok": len(blockers) == 0, "status": "TASK_STATUS_OK", "blockers": blockers}
	if len(blockers) > 0 {
		summary["ok"] = false
		summary["status"] = "TASK_STATUS_BLOCKED"
	}
	data, err := json.Marshal(summary)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "summary.json"), data, 0o644); err != nil {
		t.Fatal(err)
	}
	writeMissionHoverSpan(t, dir, 0.03)
	return dir
}

func writeMissionHoverSpan(t *testing.T, dir string, span float64) {
	t.Helper()
	tier := "green"
	if span > 0.15 {
		tier = "red"
	} else if span > 0.10 {
		tier = "yellow"
	}
	payload := map[string]any{
		"ok":                    span <= 0.15,
		"reason":                "hover_complete",
		"hover_span_target_m":   0.10,
		"hover_span_hard_cap_m": 0.15,
		"hover_drift": map[string]any{
			"horizontal_span_m":           span,
			"hover_span_target_m":         0.10,
			"hover_span_hard_cap_m":       0.15,
			"horizontal_span_tier":        tier,
			"horizontal_span_target_ok":   span <= 0.10,
			"horizontal_span_hard_cap_ok": span <= 0.15,
		},
	}
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "mission_summary.json"), data, 0o644); err != nil {
		t.Fatal(err)
	}
}

func writeStartupReadinessRuntimeArtifact(t *testing.T, dir string, action string, reason string) {
	t.Helper()
	path := artifactlayout.Audit(dir, "startup_readiness_runtime.json")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	payload := map[string]any{
		"schemaVersion": "navlab.startup_readiness_runtime.v1",
		"final_decision": map[string]any{
			"action": action,
			"reason": reason,
		},
	}
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
}
