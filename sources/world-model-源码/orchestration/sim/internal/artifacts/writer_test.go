package artifacts

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks"
)

func TestWriteRunPlanCanMarkDryRun(t *testing.T) {
	root := t.TempDir()
	writer := NewWriter(root)
	result, err := writer.WriteRunPlan(
		config.ProjectConfig{
			Orchestration: config.OrchestrationConfig{
				Family:          "sim",
				Implementation:  "go",
				ContractVersion: "navlab.orchestration.v1",
			},
			Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"},
		},
		tasks.Plan{
			TaskID:            "hover",
			Description:       "hover",
			DurationSec:       10,
			SimulationProfile: "ideal",
			Capabilities:      []string{"needs_gazebo"},
			Steps:             []string{"load task YAML config"},
		},
		time.Date(2026, 6, 12, 1, 2, 3, 0, time.UTC),
		RunPlanOptions{DryRun: true},
	)
	if err != nil {
		t.Fatalf("WriteRunPlan(dry-run) error = %v", err)
	}
	if result.RunID != "20260612T010203.000000000Z" {
		t.Fatalf("RunID = %q, want 20260612T010203.000000000Z", result.RunID)
	}
	for _, path := range []string{result.PlanPath, result.TaskRequestPath, result.ManifestPath} {
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("artifact %s missing: %v", path, err)
		}
		if filepath.Dir(path) != result.ArtifactDir {
			t.Fatalf("artifact dir mismatch for %s", path)
		}
	}
	requestData, err := os.ReadFile(result.TaskRequestPath)
	if err != nil {
		t.Fatalf("ReadFile(task_request) error = %v", err)
	}
	var request map[string]any
	if err := json.Unmarshal(requestData, &request); err != nil {
		t.Fatalf("Unmarshal(task_request) error = %v", err)
	}
	if request["schemaVersion"] != "navlab.orchestration.task_request.v1" {
		t.Fatalf("schemaVersion = %#v", request["schemaVersion"])
	}
	if request["runtimeMode"] != "RUNTIME_MODE_SIM" {
		t.Fatalf("runtimeMode = %#v", request["runtimeMode"])
	}
}

func TestWriteRunPlanCanMarkLiveRun(t *testing.T) {
	root := t.TempDir()
	writer := NewWriter(root)
	result, err := writer.WriteRunPlan(
		config.ProjectConfig{
			Orchestration: config.OrchestrationConfig{
				Family:          "sim",
				Implementation:  "go",
				ContractVersion: "navlab.orchestration.v1",
			},
			Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"},
		},
		tasks.Plan{TaskID: "hover"},
		time.Date(2026, 6, 12, 1, 2, 3, 0, time.UTC),
		RunPlanOptions{DryRun: false},
	)
	if err != nil {
		t.Fatalf("WriteRunPlan() error = %v", err)
	}
	data, err := os.ReadFile(result.PlanPath)
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		t.Fatalf("Unmarshal() error = %v", err)
	}
	if payload["dry_run"] != false {
		t.Fatalf("dry_run = %#v, want false", payload["dry_run"])
	}
}

func TestAppendManifestArtifacts(t *testing.T) {
	root := t.TempDir()
	writer := NewWriter(root)
	result, err := writer.WriteRunPlan(
		config.ProjectConfig{
			Orchestration: config.OrchestrationConfig{
				Family:          "sim",
				Implementation:  "go",
				ContractVersion: "navlab.orchestration.v1",
			},
			Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"},
		},
		tasks.Plan{TaskID: "hover"},
		time.Date(2026, 6, 12, 1, 2, 3, 0, time.UTC),
		RunPlanOptions{DryRun: true},
	)
	if err != nil {
		t.Fatalf("WriteRunPlan(dry-run) error = %v", err)
	}
	runtimePath := filepath.Join(result.ArtifactDir, "slam_runtime.toml")
	if err := os.WriteFile(runtimePath, []byte("backend = \"cartographer\"\n"), 0o644); err != nil {
		t.Fatalf("WriteFile() error = %v", err)
	}

	err = AppendManifestArtifacts(result.ManifestPath, result.ArtifactDir, []GeneratedArtifact{
		{Type: "slam_runtime_config", Path: runtimePath},
	})
	if err != nil {
		t.Fatalf("AppendManifestArtifacts() error = %v", err)
	}
	data, err := os.ReadFile(result.ManifestPath)
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	var manifest Manifest
	if err := json.Unmarshal(data, &manifest); err != nil {
		t.Fatalf("Unmarshal() error = %v", err)
	}
	if manifest.SchemaVersion != "navlab.orchestration.artifact_manifest.v1" {
		t.Fatalf("manifest schemaVersion = %q", manifest.SchemaVersion)
	}
	if len(manifest.Artifacts) != 3 {
		t.Fatalf("Artifacts len = %d, want 3", len(manifest.Artifacts))
	}
	got := manifest.Artifacts[2]
	if got.Type != "slam_runtime_config" || got.Path != "slam_runtime.toml" || got.SHA256 == "" || got.Producer != "orchestration/sim" || got.Bytes == 0 {
		t.Fatalf("appended artifact = %#v", got)
	}
}

func TestFinalizeRunArtifactsWritesRunConfigAndSummaryMarkdown(t *testing.T) {
	root := t.TempDir()
	writer := NewWriter(root)
	result, err := writer.WriteRunPlan(
		config.ProjectConfig{
			SessionID:   "session",
			RosDomainID: "85",
			Orchestration: config.OrchestrationConfig{
				Family:          "sim",
				Implementation:  "go",
				ContractVersion: "navlab.orchestration.v1",
			},
			Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"},
		},
		tasks.Plan{TaskID: "hover", DurationSec: 90, SimulationProfile: "ideal"},
		time.Date(2026, 6, 12, 1, 2, 3, 0, time.UTC),
		RunPlanOptions{DryRun: false},
	)
	if err != nil {
		t.Fatalf("WriteRunPlan() error = %v", err)
	}
	summaryPath := filepath.Join(result.ArtifactDir, "summary.json")
	if err := WriteJSONArtifact(summaryPath, map[string]any{
		"ok":       false,
		"task_id":  "hover",
		"run_id":   result.RunID,
		"blockers": []string{"landing_not_evaluated"},
		"runtime_spec_counts": map[string]any{
			"services": 1,
			"probes":   2,
			"rosbags":  1,
		},
	}); err != nil {
		t.Fatalf("WriteJSONArtifact() error = %v", err)
	}

	generated, err := FinalizeRunArtifacts(
		config.ProjectConfig{SessionID: "session", RosDomainID: "85", Orchestration: config.OrchestrationConfig{Family: "sim", Implementation: "go"}},
		tasks.Plan{TaskID: "hover", DurationSec: 90, SimulationProfile: "ideal"},
		result,
		"Hover",
		"hover_ideal",
	)
	if err != nil {
		t.Fatalf("FinalizeRunArtifacts() error = %v", err)
	}
	if len(generated) != 2 {
		t.Fatalf("generated = %#v", generated)
	}
	for _, name := range []string{"run_config.toml", "summary.md"} {
		if _, err := os.Stat(filepath.Join(result.ArtifactDir, name)); err != nil {
			t.Fatalf("%s missing: %v", name, err)
		}
	}
	summaryMD, err := os.ReadFile(filepath.Join(result.ArtifactDir, "summary.md"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(summaryMD), "landing_not_evaluated") {
		t.Fatalf("summary.md missing blocker:\n%s", string(summaryMD))
	}
}
