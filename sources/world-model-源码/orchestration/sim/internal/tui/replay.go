package tui

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
	orchestrationv1 "navlab/contracts/gen/go/navlab/orchestration/v1"
	runtimev1 "navlab/contracts/gen/go/navlab/runtime/v1"
)

type ReplayState struct {
	ArtifactDir       string
	TaskID            string
	RunID             string
	Status            string
	SummaryKind       string
	SummaryPath       string
	RuntimeCounts     RuntimeCounts
	Blockers          []string
	Warnings          []string
	Artifacts         []ArtifactFile
	RuntimeComponents []RuntimeComponent
	Missing           []string
}

type RuntimeCounts struct {
	Services int
	Probes   int
	Rosbags  int
}

type ArtifactFile struct {
	Type          string
	Path          string
	Status        string
	SchemaVersion string
	Bytes         int64
}

type RuntimeComponent struct {
	Kind    string
	Name    string
	Role    string
	Status  string
	LogPath string
}

func LoadReplay(artifactDir string) (ReplayState, error) {
	cleanDir := filepath.Clean(artifactDir)
	info, err := os.Stat(cleanDir)
	if err != nil {
		return ReplayState{}, fmt.Errorf("artifact dir is not readable: %w", err)
	}
	if !info.IsDir() {
		return ReplayState{}, fmt.Errorf("artifact path is not a directory: %s", artifactDir)
	}

	state := ReplayState{
		ArtifactDir: cleanDir,
		Status:      "unknown",
	}

	manifest, ok, err := readProtoJSONFile(cleanDir, "manifest.json", &orchestrationv1.ArtifactManifest{})
	if err != nil {
		return ReplayState{}, err
	}
	if !ok {
		state.Missing = append(state.Missing, "manifest.json")
	} else {
		state.TaskID = manifest.GetTaskId()
		state.RunID = manifest.GetRunId()
		state.Artifacts = artifactFiles(cleanDir, manifest.GetArtifacts())
	}

	taskRequest, ok, err := readProtoJSONFile(cleanDir, "task_request.json", &orchestrationv1.TaskRequest{})
	if err != nil {
		return ReplayState{}, err
	}
	if !ok {
		state.Missing = append(state.Missing, "task_request.json")
	} else {
		state.TaskID = firstString(state.TaskID, taskRequest.GetTaskId())
		state.RunID = firstString(state.RunID, taskRequest.GetRunId())
	}

	runtimePlan, ok, err := readProtoJSONFile(cleanDir, "runtime_plan.json", &runtimev1.RuntimePlan{})
	if err != nil {
		return ReplayState{}, err
	}
	if !ok {
		state.Missing = append(state.Missing, "runtime_plan.json")
	} else {
		state.TaskID = firstString(state.TaskID, runtimePlan.GetTaskId())
		state.RunID = firstString(state.RunID, runtimePlan.GetRunId())
		state.RuntimeComponents = runtimeComponents(runtimePlan)
		state.RuntimeCounts = RuntimeCounts{
			Services: len(runtimePlan.GetServices()),
			Probes:   len(runtimePlan.GetProbes()),
			Rosbags:  len(runtimePlan.GetRosbags()),
		}
	}

	summary, summaryKind, ok, err := readSummary(cleanDir)
	if err != nil {
		return ReplayState{}, err
	}
	if !ok {
		state.Missing = append(state.Missing, "summary.json", "doctor_summary.json")
	} else {
		state.SummaryKind = summaryKind
		state.SummaryPath = filepath.Join(cleanDir, summaryKind+".json")
		state.TaskID = firstString(state.TaskID, stringMapValue(summary, "task_id"), stringMapValue(summary, "taskId"))
		state.RunID = firstString(state.RunID, stringMapValue(summary, "run_id"), stringMapValue(summary, "runId"))
		state.Status = summaryStatus(summary)
		state.Blockers = summaryBlockers(summary)
		state.Warnings = stringSlice(summary["warnings"])
		if counts, ok := summary["runtime_spec_counts"].(map[string]any); ok {
			state.RuntimeCounts = RuntimeCounts{
				Services: intValue(counts["services"], state.RuntimeCounts.Services),
				Probes:   intValue(counts["probes"], state.RuntimeCounts.Probes),
				Rosbags:  intValue(counts["rosbags"], state.RuntimeCounts.Rosbags),
			}
		}
	}

	return state, nil
}

func readProtoJSONFile[T proto.Message](artifactDir string, name string, value T) (T, bool, error) {
	path := filepath.Join(artifactDir, name)
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return value, false, nil
	}
	if err != nil {
		return value, false, fmt.Errorf("failed to read %s: %w", path, err)
	}
	if err := (protojson.UnmarshalOptions{DiscardUnknown: true}).Unmarshal(data, value); err != nil {
		return value, false, fmt.Errorf("failed to parse %s: %w", path, err)
	}
	return value, true, nil
}

func readJSONMap(artifactDir string, name string) (map[string]any, bool, error) {
	path := filepath.Join(artifactDir, name)
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("failed to read %s: %w", path, err)
	}
	var value map[string]any
	if err := json.Unmarshal(data, &value); err != nil {
		return nil, false, fmt.Errorf("failed to parse %s: %w", path, err)
	}
	return value, true, nil
}

func readSummary(artifactDir string) (map[string]any, string, bool, error) {
	summary, ok, err := readProtoJSONFile(artifactDir, "summary.json", &orchestrationv1.TaskResult{})
	if err != nil {
		return nil, "summary", false, err
	}
	if ok {
		rawSummary, _, _ := readJSONMap(artifactDir, "summary.json")
		return taskResultMap(summary, rawSummary), "summary", true, nil
	}
	doctorSummary, ok, err := readJSONMap(artifactDir, "doctor_summary.json")
	return doctorSummary, "doctor_summary", ok, err
}

func artifactFiles(artifactDir string, entries []*orchestrationv1.Artifact) []ArtifactFile {
	files := make([]ArtifactFile, 0, len(entries))
	for _, entry := range entries {
		path := entry.GetPath()
		fullPath := path
		if !filepath.IsAbs(path) {
			fullPath = filepath.Join(artifactDir, filepath.FromSlash(path))
		}
		status := "ok"
		if _, err := os.Stat(fullPath); err != nil {
			status = "missing"
		}
		files = append(files, ArtifactFile{
			Type:          entry.GetType(),
			Path:          path,
			Status:        status,
			SchemaVersion: entry.GetSchemaVersion(),
			Bytes:         entry.GetBytes(),
		})
	}
	return files
}

func runtimeComponents(runtimePlan *runtimev1.RuntimePlan) []RuntimeComponent {
	components := []RuntimeComponent{}
	for _, spec := range runtimePlan.GetServices() {
		components = append(components, RuntimeComponent{
			Kind:    "service",
			Name:    spec.GetName(),
			Role:    spec.GetRole(),
			Status:  "planned",
			LogPath: spec.GetLogPath(),
		})
	}
	for _, spec := range runtimePlan.GetProbes() {
		components = append(components, RuntimeComponent{
			Kind:    "probe",
			Name:    spec.GetName(),
			Role:    spec.GetRole(),
			Status:  "planned",
			LogPath: spec.GetLogPath(),
		})
	}
	for _, spec := range runtimePlan.GetRosbags() {
		components = append(components, RuntimeComponent{
			Kind:    "rosbag",
			Name:    spec.GetName(),
			Role:    spec.GetRole(),
			Status:  "planned",
			LogPath: spec.GetLogPath(),
		})
	}
	return components
}

func summaryStatus(summary map[string]any) string {
	if status := stringMapValue(summary, "status"); status != "" {
		return status
	}
	if ok, exists := summary["ok"].(bool); exists {
		if ok {
			return "ok"
		}
		return "blocked"
	}
	return "unknown"
}

func summaryBlockers(summary map[string]any) []string {
	blockers := stringSlice(summary["blockerCodes"])
	if len(blockers) > 0 {
		return blockers
	}
	return stringSlice(summary["blockers"])
}

func stringSlice(value any) []string {
	values, ok := value.([]any)
	if !ok {
		return nil
	}
	result := make([]string, 0, len(values))
	for _, raw := range values {
		switch item := raw.(type) {
		case string:
			result = append(result, item)
		case map[string]any:
			if code := stringMapValue(item, "code"); code != "" {
				result = append(result, code)
			} else if message := stringMapValue(item, "message"); message != "" {
				result = append(result, message)
			}
		default:
			text := strings.TrimSpace(fmt.Sprint(item))
			if text != "" {
				result = append(result, text)
			}
		}
	}
	return result
}

func stringMapValue(values map[string]any, key string) string {
	value, _ := values[key].(string)
	return value
}

func firstString(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func intValue(value any, fallback int) int {
	switch typed := value.(type) {
	case float64:
		return int(typed)
	case int:
		return typed
	default:
		return fallback
	}
}

func taskResultMap(result *orchestrationv1.TaskResult, raw map[string]any) map[string]any {
	values := map[string]any{
		"ok":           result.GetOk(),
		"blocked":      result.GetBlocked(),
		"status":       result.GetStatus().String(),
		"exitCode":     result.GetExitCode(),
		"task_id":      result.GetTaskId(),
		"run_id":       result.GetRunId(),
		"artifact_dir": result.GetArtifactDir(),
		"summaryPath":  result.GetSummaryPath(),
		"warnings":     append([]string(nil), result.GetWarnings()...),
	}
	blockers := make([]map[string]any, 0, len(result.GetBlockers()))
	for _, blocker := range result.GetBlockers() {
		blockers = append(blockers, map[string]any{
			"code":    blocker.GetCode(),
			"message": blocker.GetMessage(),
			"source":  blocker.GetSource(),
		})
	}
	values["blockers"] = blockers
	if len(blockers) == 0 && raw != nil {
		if blockerCodes, ok := raw["blockerCodes"]; ok {
			values["blockerCodes"] = blockerCodes
		}
	}
	if counts, ok := raw["runtime_spec_counts"]; ok {
		values["runtime_spec_counts"] = counts
	}
	return values
}
