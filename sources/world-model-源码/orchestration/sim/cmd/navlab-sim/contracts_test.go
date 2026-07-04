package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func TestPrepareTaskRunEmitsGoldenCompatibleContractJSON(t *testing.T) {
	prepared, err := prepareTaskRun(
		config.NewLoader(filepath.Join("..", "..", "config.toml")),
		tasks.DefaultRegistry(),
		helpers.DefaultRegistry(),
		"hover",
		true,
		t.TempDir(),
		tasks.PlanOptions{},
		false,
	)
	if err != nil {
		t.Fatal(err)
	}

	request := readJSONFile(t, prepared.Result.TaskRequestPath)
	goldenRequest := readContractExample(t, "orchestration", "sim_task_request.json")
	assertEqualField(t, request, goldenRequest, "schemaVersion")
	assertEqualField(t, request, goldenRequest, "taskId")
	assertEqualField(t, request, goldenRequest, "runtimeMode")
	assertEqualField(t, request, goldenRequest, "capabilities")
	assertNestedEqualField(t, request, goldenRequest, "sourceClaims", "runtimeDomain")
	assertNestedEqualField(t, request, goldenRequest, "sourceClaims", "scanSource")
	assertNestedEqualField(t, request, goldenRequest, "sourceClaims", "usesTruthAsControlInput")

	runtimePlan := readJSONFile(t, filepath.Join(prepared.Result.ArtifactDir, "runtime_plan.json"))
	goldenRuntimePlan := readContractExample(t, "runtime", "sim_runtime_plan.json")
	assertEqualField(t, runtimePlan, goldenRuntimePlan, "schemaVersion")
	assertEqualField(t, runtimePlan, goldenRuntimePlan, "taskId")
	assertFirstNamedObjectField(t, runtimePlan, "services", "official_baseline", "backend", "RUNTIME_BACKEND_DOCKER")
	assertFirstNamedObjectField(t, runtimePlan, "probes", "slam_hover_probe", "backend", "RUNTIME_BACKEND_DOCKER")
	assertFirstNamedObjectField(t, runtimePlan, "probes", "slam_hover_probe", "outputPath", artifactlayout.Probe(prepared.Result.ArtifactDir, "slam_hover_probe.json"))
	assertFirstNamedObjectField(t, runtimePlan, "rosbags", "hover_rosbag", "storage", "mcap")
	startupPolicy, ok := runtimePlan["startupReadinessPolicy"].(map[string]any)
	if !ok || startupPolicy["owner"] != "go_runtime_config" || startupPolicy["restart_limit"] != float64(0) {
		t.Fatalf("startup readiness policy = %#v", runtimePlan["startupReadinessPolicy"])
	}

	manifest := readJSONFile(t, prepared.Result.ManifestPath)
	if manifest["schemaVersion"] != "navlab.orchestration.artifact_manifest.v1" {
		t.Fatalf("manifest schemaVersion = %#v", manifest["schemaVersion"])
	}
	if !artifactTypeExists(manifest, "runtime_plan") {
		t.Fatalf("manifest missing runtime_plan artifact: %#v", manifest["artifacts"])
	}
	for _, artifactType := range []string{"preflight_summary", "prepare_summary", "common_doctor_summary", "task_doctor_summary", "workflow_summary", "doctor_result"} {
		path := artifactTypePath(t, manifest, artifactType)
		if !strings.HasPrefix(filepath.ToSlash(path), "dag/") {
			t.Fatalf("%s path = %s, want dag directory", artifactType, path)
		}
		if _, err := os.Stat(filepath.Join(prepared.Result.ArtifactDir, path)); err != nil {
			t.Fatalf("%s path %s stat error = %v", artifactType, path, err)
		}
	}
}

func TestRunTaskTUILiveRequiresTTYBeforePreparingArtifacts(t *testing.T) {
	artifactRoot := t.TempDir()
	err := runTask(
		config.NewLoader(filepath.Join("..", "..", "config.toml")),
		tasks.DefaultRegistry(),
		helpers.DefaultRegistry(),
		"hover",
		false,
		true,
		false,
		artifactRoot,
		tasks.PlanOptions{},
	)
	if err == nil || !strings.Contains(err.Error(), "interactive terminal") {
		t.Fatalf("runTask() error = %v, want TTY error", err)
	}
	entries, readErr := os.ReadDir(artifactRoot)
	if readErr != nil {
		t.Fatal(readErr)
	}
	if len(entries) != 0 {
		t.Fatalf("artifact root should stay empty before TTY check, got %d entries", len(entries))
	}
}

func readContractExample(t *testing.T, parts ...string) map[string]any {
	t.Helper()
	pathParts := append([]string{"..", "..", "..", "..", "contracts", "examples"}, parts...)
	return readJSONFile(t, filepath.Join(pathParts...))
}

func readJSONFile(t *testing.T, path string) map[string]any {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile(%s) error = %v", path, err)
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		t.Fatalf("Unmarshal(%s) error = %v", path, err)
	}
	return payload
}

func assertEqualField(t *testing.T, actual map[string]any, expected map[string]any, field string) {
	t.Helper()
	actualJSON, err := json.Marshal(actual[field])
	if err != nil {
		t.Fatal(err)
	}
	expectedJSON, err := json.Marshal(expected[field])
	if err != nil {
		t.Fatal(err)
	}
	if string(actualJSON) != string(expectedJSON) {
		t.Fatalf("%s = %s, want %s", field, actualJSON, expectedJSON)
	}
}

func assertNestedEqualField(t *testing.T, actual map[string]any, expected map[string]any, parent string, field string) {
	t.Helper()
	actualParent, ok := actual[parent].(map[string]any)
	if !ok {
		t.Fatalf("%s = %#v", parent, actual[parent])
	}
	expectedParent, ok := expected[parent].(map[string]any)
	if !ok {
		t.Fatalf("golden %s = %#v", parent, expected[parent])
	}
	assertEqualField(t, actualParent, expectedParent, field)
}

func assertFirstNamedObjectField(t *testing.T, payload map[string]any, collection string, name string, field string, expected any) {
	t.Helper()
	for _, raw := range payload[collection].([]any) {
		item := raw.(map[string]any)
		if item["name"] != name {
			continue
		}
		if item[field] != expected {
			t.Fatalf("%s[%s].%s = %#v, want %#v", collection, name, field, item[field], expected)
		}
		return
	}
	t.Fatalf("%s missing item %q: %#v", collection, name, payload[collection])
}

func artifactTypeExists(manifest map[string]any, artifactType string) bool {
	for _, raw := range manifest["artifacts"].([]any) {
		item := raw.(map[string]any)
		if item["type"] == artifactType {
			return true
		}
	}
	return false
}

func artifactTypePath(t *testing.T, manifest map[string]any, artifactType string) string {
	t.Helper()
	for _, raw := range manifest["artifacts"].([]any) {
		item := raw.(map[string]any)
		if item["type"] == artifactType {
			path, ok := item["path"].(string)
			if !ok || path == "" {
				t.Fatalf("%s path = %#v", artifactType, item["path"])
			}
			return path
		}
	}
	t.Fatalf("manifest missing %s artifact: %#v", artifactType, manifest["artifacts"])
	return ""
}
