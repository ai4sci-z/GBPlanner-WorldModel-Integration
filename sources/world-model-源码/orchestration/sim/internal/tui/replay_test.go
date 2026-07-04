package tui

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"navlab/orchestration-sim/internal/tasks"
)

func TestLoadReplayReadsCoreArtifacts(t *testing.T) {
	artifactDir := t.TempDir()
	writeJSON(t, filepath.Join(artifactDir, "task_request.json"), map[string]any{
		"taskId": "hover",
		"runId":  "20260612T010203Z",
	})
	writeJSON(t, filepath.Join(artifactDir, "runtime_plan.json"), map[string]any{
		"taskId": "hover",
		"runId":  "20260612T010203Z",
		"services": []map[string]any{{
			"name":    "official_baseline",
			"role":    "sitl",
			"logPath": "logs/official_baseline.log",
		}},
		"probes": []map[string]any{{
			"name":       "slam_hover_probe",
			"role":       "slam",
			"outputPath": "slam_hover_probe.json",
		}},
		"rosbags": []map[string]any{{
			"name":       "hover_rosbag",
			"role":       "rosbag",
			"outputPath": "rosbag/hover.mcap",
		}},
	})
	writeJSON(t, filepath.Join(artifactDir, "summary.json"), map[string]any{
		"ok":           false,
		"status":       "TASK_STATUS_BLOCKED",
		"task_id":      "hover",
		"run_id":       "20260612T010203Z",
		"blockerCodes": []string{"landing_not_evaluated"},
		"runtime_spec_counts": map[string]any{
			"services": 1,
			"probes":   1,
			"rosbags":  1,
		},
	})
	writeJSON(t, filepath.Join(artifactDir, "manifest.json"), map[string]any{
		"schemaVersion":  "navlab.orchestration.artifact_manifest.v1",
		"task_id":        "hover",
		"run_id":         "20260612T010203Z",
		"runtime_mode":   "simulation",
		"implementation": "go",
		"artifacts": []map[string]any{{
			"type":          "task_request",
			"path":          "task_request.json",
			"schemaVersion": "navlab.orchestration.task_request.v1",
			"bytes":         1,
		}},
	})

	state, err := LoadReplay(artifactDir)
	if err != nil {
		t.Fatalf("LoadReplay() error = %v", err)
	}
	if state.TaskID != "hover" || state.RunID != "20260612T010203Z" {
		t.Fatalf("loaded task/run = %q/%q", state.TaskID, state.RunID)
	}
	if state.Status != "TASK_STATUS_BLOCKED" {
		t.Fatalf("Status = %q", state.Status)
	}
	if state.RuntimeCounts != (RuntimeCounts{Services: 1, Probes: 1, Rosbags: 1}) {
		t.Fatalf("RuntimeCounts = %#v", state.RuntimeCounts)
	}
	if len(state.Blockers) != 1 || state.Blockers[0] != "landing_not_evaluated" {
		t.Fatalf("Blockers = %#v", state.Blockers)
	}
	if len(state.RuntimeComponents) != 3 {
		t.Fatalf("RuntimeComponents len = %d", len(state.RuntimeComponents))
	}
	if len(state.Missing) != 0 {
		t.Fatalf("Missing = %#v", state.Missing)
	}
}

func TestLoadReplayFallsBackToDoctorSummary(t *testing.T) {
	artifactDir := t.TempDir()
	writeJSON(t, filepath.Join(artifactDir, "manifest.json"), map[string]any{
		"schemaVersion": "navlab.orchestration.artifact_manifest.v1",
		"task_id":       "hover",
		"run_id":        "20260612T010203Z",
		"artifacts":     []map[string]any{},
	})
	writeJSON(t, filepath.Join(artifactDir, "task_request.json"), map[string]any{
		"taskId": "hover",
		"runId":  "20260612T010203Z",
	})
	writeJSON(t, filepath.Join(artifactDir, "runtime_plan.json"), map[string]any{
		"services": []map[string]any{},
		"probes":   []map[string]any{},
		"rosbags":  []map[string]any{},
	})
	writeJSON(t, filepath.Join(artifactDir, "doctor_summary.json"), map[string]any{
		"ok":       true,
		"task_id":  "hover",
		"run_id":   "20260612T010203Z",
		"blockers": []string{},
	})

	state, err := LoadReplay(artifactDir)
	if err != nil {
		t.Fatalf("LoadReplay() error = %v", err)
	}
	if state.SummaryKind != "doctor_summary" {
		t.Fatalf("SummaryKind = %q", state.SummaryKind)
	}
	if state.Status != "ok" {
		t.Fatalf("Status = %q", state.Status)
	}
	if strings.Contains(strings.Join(state.Missing, ","), "summary") {
		t.Fatalf("Missing unexpectedly includes summary: %#v", state.Missing)
	}
}

func TestRenderReplayIncludesDashboardSections(t *testing.T) {
	state := ReplayState{
		ArtifactDir: "/tmp/navlab",
		TaskID:      "hover",
		RunID:       "run",
		Status:      "ok",
		RuntimeCounts: RuntimeCounts{
			Services: 1,
			Probes:   2,
			Rosbags:  1,
		},
		Artifacts: []ArtifactFile{{Type: "task_request", Status: "ok"}},
	}

	model := NewReplayModel(state)
	model.width = 100
	view := model.View()
	for _, want := range []string{"NavLab Sim TUI", "Runtime", "Gates / Blockers", "Artifacts", "services=1 probes=2 rosbags=1"} {
		if !strings.Contains(view, want) {
			t.Fatalf("ReplayModel.View() missing %q:\n%s", want, view)
		}
	}
}

func TestLiveModelAppliesRuntimeEventsAndFocusesBlockers(t *testing.T) {
	model := NewLiveModel(ReplayState{
		ArtifactDir: t.TempDir(),
		TaskID:      "hover",
		RunID:       "run",
		RuntimeComponents: []RuntimeComponent{{
			Kind:   "probe",
			Name:   "slam_hover_probe",
			Status: "planned",
		}},
	}, nil, nil)

	updated, _ := model.Update(runtimeEventMsg{ok: true, event: tasks.RuntimeEvent{
		TaskID:      "hover",
		RunID:       "run",
		Phase:       "probe.failed",
		Component:   "probe",
		ComponentID: "slam_hover_probe",
		Message:     "missing /slam/odom",
	}})
	next := updated.(ReplayModel)
	if next.state.RuntimeComponents[0].Status != "failed" {
		t.Fatalf("component status = %q", next.state.RuntimeComponents[0].Status)
	}
	if next.panel != 1 {
		t.Fatalf("panel = %d, want blockers panel", next.panel)
	}
	if len(next.state.Blockers) != 1 || next.state.Blockers[0] != "missing /slam/odom" {
		t.Fatalf("blockers = %#v", next.state.Blockers)
	}
}

func TestLiveModelLogLinesTailsSelectedComponentLog(t *testing.T) {
	artifactDir := t.TempDir()
	logPath := filepath.Join(artifactDir, "slam.log")
	if err := os.WriteFile(logPath, []byte("line1\nline2\nline3\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	model := NewReplayModel(ReplayState{
		ArtifactDir: artifactDir,
		RuntimeComponents: []RuntimeComponent{{
			Kind:    "service",
			Name:    "slam_backend",
			Status:  "running",
			LogPath: logPath,
		}},
	})

	lines := strings.Join(model.logLines(), "\n")
	for _, want := range []string{"selected=service/slam_backend", "line1", "line3"} {
		if !strings.Contains(lines, want) {
			t.Fatalf("log lines missing %q:\n%s", want, lines)
		}
	}
}

func writeJSON(t *testing.T, path string, value any) {
	t.Helper()
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, append(data, '\n'), 0o644); err != nil {
		t.Fatal(err)
	}
}
