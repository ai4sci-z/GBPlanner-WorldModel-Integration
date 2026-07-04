package tasks

import (
	"path/filepath"
	"testing"
	"time"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	simruntime "navlab/orchestration-sim/internal/runtime"
)

func TestBuildRosbagRecorderFSMSummaryCompletedWithMetadata(t *testing.T) {
	exitCode := 0
	handle := simruntime.RuntimeHandle{
		Backend:             "docker_sdk",
		ServiceName:         "hover_rosbag",
		Identifier:          "container-1",
		StartedAt:           time.Date(2026, 6, 27, 1, 2, 3, 0, time.UTC),
		StopRequestedAt:     "2026-06-27T01:02:10Z",
		StoppedAt:           "2026-06-27T01:02:11Z",
		StopSignal:          "SIGINT",
		StopTimeoutSec:      10,
		WaitExitCode:        &exitCode,
		FinalizeOK:          true,
		FinalizeStatus:      "metadata_ready",
		MetadataPath:        "rosbag/hover_rosbag/metadata.yaml",
		MessageCountsSource: "metadata",
	}
	gate := RosbagGateSummary{
		Name:                "hover_rosbag",
		OK:                  true,
		RequiredTopics:      []string{"/scan"},
		MessageCountsSource: "metadata",
	}

	summary, dot := BuildRosbagRecorderFSMSummary("hover", "run-1", handle, &gate, "runtime/rosbag_hover_rosbag_fsm.json", "runtime/rosbag_hover_rosbag_fsm.dot")
	if summary.SchemaVersion != "navlab.fsm.v1" {
		t.Fatalf("schema version = %q", summary.SchemaVersion)
	}
	if summary.State != "completed" {
		t.Fatalf("state = %q, want completed", summary.State)
	}
	if !summary.OK || summary.Blocked {
		t.Fatalf("ok/blocked = %v/%v, want true/false", summary.OK, summary.Blocked)
	}
	if len(summary.Transitions) != 8 {
		t.Fatalf("transitions = %d, want 8", len(summary.Transitions))
	}
	if got := summary.Transitions[5].ReasonCode; got != rosbagReasonMetadataReady {
		t.Fatalf("verify reason = %q, want %q", got, rosbagReasonMetadataReady)
	}
	if dot == "" {
		t.Fatal("dot graph is empty")
	}
}

func TestBuildRosbagRecorderFSMSummaryBlocksMissingRequiredTopics(t *testing.T) {
	exitCode := 0
	handle := simruntime.RuntimeHandle{
		Backend:         "docker_sdk",
		ServiceName:     "hover_rosbag",
		StartedAt:       time.Date(2026, 6, 27, 1, 2, 3, 0, time.UTC),
		StopRequestedAt: "2026-06-27T01:02:10Z",
		StoppedAt:       "2026-06-27T01:02:11Z",
		StopSignal:      "SIGINT",
		WaitExitCode:    &exitCode,
		FinalizeOK:      true,
		FinalizeStatus:  "mcap_readable",
		MCAPPaths:       []string{"rosbag/hover_rosbag/hover_rosbag_0.mcap"},
	}
	gate := RosbagGateSummary{
		Name:                  "hover_rosbag",
		OK:                    false,
		RequiredTopics:        []string{"/scan", "/tf"},
		MissingRequiredTopics: []string{"/tf"},
		MessageCountsSource:   "mcap_stream",
	}

	summary, _ := BuildRosbagRecorderFSMSummary("hover", "run-1", handle, &gate, "runtime/rosbag_hover_rosbag_fsm.json", "runtime/rosbag_hover_rosbag_fsm.dot")
	if summary.State != "required_topics_missing" {
		t.Fatalf("state = %q, want required_topics_missing", summary.State)
	}
	if summary.OK || !summary.Blocked {
		t.Fatalf("ok/blocked = %v/%v, want false/true", summary.OK, summary.Blocked)
	}
	if summary.FailureReasonCode != rosbagReasonRequiredTopicsMissing {
		t.Fatalf("failure reason = %q, want %q", summary.FailureReasonCode, rosbagReasonRequiredTopicsMissing)
	}
	if summary.FailedTrigger != "fail_required_topics_missing" {
		t.Fatalf("failed trigger = %q", summary.FailedTrigger)
	}
}

func TestWriteRosbagRecorderFSMArtifactsWritesJSONAndDOT(t *testing.T) {
	exitCode := 0
	artifactDir := t.TempDir()
	if err := artifactlayout.Ensure(artifactDir); err != nil {
		t.Fatalf("Ensure() error = %v", err)
	}
	execution := RuntimeExecutionResult{
		RosbagHandles: []simruntime.RuntimeHandle{{
			Backend:             "docker_sdk",
			ServiceName:         "hover_rosbag",
			StartedAt:           time.Now().UTC(),
			StopRequestedAt:     "2026-06-27T01:02:10Z",
			StoppedAt:           "2026-06-27T01:02:11Z",
			StopSignal:          "SIGINT",
			WaitExitCode:        &exitCode,
			FinalizeOK:          true,
			FinalizeStatus:      "metadata_ready",
			MetadataPath:        filepath.Join(artifactDir, "rosbag/hover_rosbag/metadata.yaml"),
			MessageCountsSource: "metadata",
		}},
	}
	gate := GateEvaluation{
		RosbagProfiles: []RosbagGateSummary{{
			Name:                "hover_rosbag",
			OK:                  true,
			RequiredTopics:      []string{"/scan"},
			MessageCountsSource: "metadata",
		}},
	}

	refs, generated, err := WriteRosbagRecorderFSMArtifacts(artifactDir, "hover", "run-1", execution, gate)
	if err != nil {
		t.Fatalf("WriteRosbagRecorderFSMArtifacts() error = %v", err)
	}
	if len(refs) != 1 || len(generated) != 2 {
		t.Fatalf("refs/generated = %d/%d, want 1/2", len(refs), len(generated))
	}
	if refs[0].ArtifactPath != artifactlayout.RuntimeRel("rosbag_hover_rosbag_fsm.json") {
		t.Fatalf("artifact ref path = %q", refs[0].ArtifactPath)
	}
	for _, artifact := range generated {
		if artifact.Path == "" {
			t.Fatal("generated artifact path is empty")
		}
	}
}

func TestBuildHoverTaskFSMSummaryLinksRuntimeSubFSM(t *testing.T) {
	gate := GateEvaluation{
		OK: true,
		Metrics: MetricSummary{
			HoverMission: map[string]any{
				"mission_phase_state": "S13 task_success",
			},
		},
	}
	subFSMs := []FSMArtifactRef{{
		FSMName:      "rosbag_recorder",
		Scope:        "rosbag",
		ArtifactPath: "runtime/rosbag_hover_rosbag_fsm.json",
		State:        "completed",
		OK:           true,
		Blocked:      false,
	}}

	summary := BuildTaskFSMSummary("hover", "run-1", "actual", true, nil, &gate, subFSMs, "runtime/task_hover_fsm.json")
	if summary.SchemaVersion != "navlab.fsm.v1" {
		t.Fatalf("schema version = %q", summary.SchemaVersion)
	}
	if summary.State != "completed" {
		t.Fatalf("state = %q, want completed", summary.State)
	}
	if len(summary.SubFSMs) != 1 {
		t.Fatalf("sub fsms = %d, want 1", len(summary.SubFSMs))
	}
	if len(summary.Transitions) != 8 {
		t.Fatalf("transitions = %d, want 8", len(summary.Transitions))
	}
	if summary.Transitions[3].ToState != "hover_health_hold" {
		t.Fatalf("transition[3].to = %q", summary.Transitions[3].ToState)
	}
}

func TestBuildDefaultTaskFSMSummaryBlocksWithReasonCode(t *testing.T) {
	summary := BuildTaskFSMSummary("navigation", "run-1", "actual", false, []string{"nav_goal_missing:frontier"}, nil, nil, "runtime/task_navigation_fsm.json")
	if summary.State != "blocked" {
		t.Fatalf("state = %q, want blocked", summary.State)
	}
	if summary.FailureReasonCode != "nav_goal_missing" {
		t.Fatalf("failure reason = %q, want nav_goal_missing", summary.FailureReasonCode)
	}
	if summary.Transitions[0].Trigger != "block" {
		t.Fatalf("trigger = %q, want block", summary.Transitions[0].Trigger)
	}
}
