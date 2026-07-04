package tasks

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	hoveraudit "navlab/orchestration-sim/internal/audits/hover"
)

func TestAttachHoverHealthToLiveRunSummaryAddsGatePayloadFields(t *testing.T) {
	dir := t.TempDir()
	health := &hoveraudit.HoverHealthSummary{
		Schema:             "navlab.hover_health_summary.v1",
		DiagnosticOnly:     true,
		ArtifactDir:        dir,
		HealthBand:         hoveraudit.HoverHealthYellow,
		HardBlockers:       []hoveraudit.HoverHealthFinding{},
		ReviewOnlyFindings: []hoveraudit.HoverHealthFinding{{Code: "hover_gazebo_model_horizontal_drift"}},
		Proceed: hoveraudit.HoverHealthProceed{
			Reason: "yellow_wait_for_green",
		},
	}
	summary := LiveRunSummary{ArtifactDir: dir, Metrics: map[string]any{}, Evidence: map[string]any{}}

	AttachHoverHealthToLiveRunSummary(&summary, health)

	if summary.HoverHealthBand != string(hoveraudit.HoverHealthYellow) {
		t.Fatalf("summary hover health band = %q", summary.HoverHealthBand)
	}
	if summary.HoverHealthProceed == nil || summary.HoverHealthProceed.SimAutoContinueAllowed {
		t.Fatalf("hover health proceed = %#v", summary.HoverHealthProceed)
	}
	if summary.PostrunHoverHealthAudit == nil || summary.PostrunHoverHealthAudit.ControlsRuntimeProceed {
		t.Fatalf("postrun hover health audit missing/says it controls runtime: %#v", summary.PostrunHoverHealthAudit)
	}
	if summary.GateEvaluation.Metrics.HoverHealth["band"] != hoveraudit.HoverHealthYellow {
		t.Fatalf("gate hover health metric missing: %#v", summary.GateEvaluation.Metrics.HoverHealth)
	}
	if summary.Metrics["hover_health"] == nil || summary.Evidence["hoverHealth"] == nil {
		t.Fatalf("summary hover health fields missing: metrics=%#v evidence=%#v", summary.Metrics, summary.Evidence)
	}
}

func TestAttachRuntimeHoverHealthFromMissionSummaryAddsRuntimeSchema(t *testing.T) {
	dir := t.TempDir()
	mission := map[string]any{
		"runtime_hover_health_final": map[string]any{
			"schema":                    "navlab.runtime_hover_health.v1",
			"phase":                     "sim_auto_continue",
			"band":                      "green",
			"sim_auto_continue_allowed": true,
		},
	}
	data, err := json.Marshal(mission)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "mission_summary.json"), data, 0o644); err != nil {
		t.Fatal(err)
	}
	summary := LiveRunSummary{ArtifactDir: dir, Metrics: map[string]any{}, Evidence: map[string]any{}}

	AttachRuntimeHoverHealthFromMissionSummary(&summary)

	if summary.RuntimeHoverHealthFinal["phase"] != "sim_auto_continue" {
		t.Fatalf("runtime hover health final missing: %#v", summary.RuntimeHoverHealthFinal)
	}
	if summary.Metrics["runtime_hover_health"] == nil || summary.Evidence["runtimeHoverHealth"] == nil {
		t.Fatalf("runtime health summary fields missing: metrics=%#v evidence=%#v", summary.Metrics, summary.Evidence)
	}
}
