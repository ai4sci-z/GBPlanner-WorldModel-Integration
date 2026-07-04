package artifacts

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	toml "github.com/pelletier/go-toml/v2"

	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks"
)

type Writer struct {
	root string
}

type RunArtifact struct {
	Type          string `json:"type"`
	Path          string `json:"path"`
	Producer      string `json:"producer,omitempty"`
	SchemaVersion string `json:"schemaVersion,omitempty"`
	SHA256        string `json:"sha256"`
	Bytes         int64  `json:"bytes"`
	CreatedAt     string `json:"createdAt,omitempty"`
}

type GeneratedArtifact struct {
	Type string
	Path string
}

type Manifest struct {
	SchemaVersion   string        `json:"schemaVersion"`
	ContractVersion string        `json:"contract_version"`
	Family          string        `json:"family"`
	Implementation  string        `json:"implementation"`
	RuntimeMode     string        `json:"runtime_mode"`
	Backend         string        `json:"backend"`
	TaskID          string        `json:"task_id"`
	RunID           string        `json:"run_id"`
	CreatedAt       string        `json:"created_at"`
	Artifacts       []RunArtifact `json:"artifacts"`
}

type DryRunResult struct {
	RunID           string
	ArtifactDir     string
	PlanPath        string
	TaskRequestPath string
	ManifestPath    string
}

type RunPlanOptions struct {
	DryRun bool
}

func NewWriter(root string) Writer {
	return Writer{root: root}
}

func NewRunID(now time.Time) string {
	return now.UTC().Format("20060102T150405.000000000Z")
}

func (writer Writer) WriteRunPlan(
	project config.ProjectConfig,
	plan tasks.Plan,
	now time.Time,
	options RunPlanOptions,
) (DryRunResult, error) {
	runID := NewRunID(now)
	taskDir := filepath.Join(writer.root, sanitizePathSegment(plan.TaskID), runID)
	if err := os.MkdirAll(taskDir, 0o755); err != nil {
		return DryRunResult{}, err
	}

	planPath := filepath.Join(taskDir, "task_plan.json")
	if err := writeJSON(planPath, map[string]any{
		"contract_version": project.Orchestration.ContractVersion,
		"family":           project.Orchestration.Family,
		"implementation":   project.Orchestration.Implementation,
		"runtime_mode":     project.Runtime.Mode,
		"backend":          project.Runtime.Backend,
		"dry_run":          options.DryRun,
		"run_id":           runID,
		"created_at":       now.UTC().Format(time.RFC3339),
		"plan":             plan,
	}); err != nil {
		return DryRunResult{}, err
	}
	planHash, err := fileSHA256(planPath)
	if err != nil {
		return DryRunResult{}, err
	}
	taskRequestPath := filepath.Join(taskDir, "task_request.json")
	if err := writeJSON(taskRequestPath, taskRequestPayload(project, plan, runID, taskDir, now)); err != nil {
		return DryRunResult{}, err
	}
	taskRequestHash, err := fileSHA256(taskRequestPath)
	if err != nil {
		return DryRunResult{}, err
	}

	manifest := Manifest{
		SchemaVersion:   "navlab.orchestration.artifact_manifest.v1",
		ContractVersion: project.Orchestration.ContractVersion,
		Family:          project.Orchestration.Family,
		Implementation:  project.Orchestration.Implementation,
		RuntimeMode:     project.Runtime.Mode,
		Backend:         project.Runtime.Backend,
		TaskID:          plan.TaskID,
		RunID:           runID,
		CreatedAt:       now.UTC().Format(time.RFC3339),
		Artifacts: []RunArtifact{
			newManifestArtifact("task_plan", "task_plan.json", planHash, planPath),
			newManifestArtifact("task_request", "task_request.json", taskRequestHash, taskRequestPath),
		},
	}
	manifestPath := filepath.Join(taskDir, "manifest.json")
	if err := writeJSON(manifestPath, manifest); err != nil {
		return DryRunResult{}, err
	}

	return DryRunResult{
		RunID:           runID,
		ArtifactDir:     taskDir,
		PlanPath:        planPath,
		TaskRequestPath: taskRequestPath,
		ManifestPath:    manifestPath,
	}, nil
}

func taskRequestPayload(project config.ProjectConfig, plan tasks.Plan, runID string, artifactDir string, now time.Time) map[string]any {
	return map[string]any{
		"schemaVersion": "navlab.orchestration.task_request.v1",
		"taskId":        plan.TaskID,
		"runId":         runID,
		"runtimeMode":   runtimeMode(project),
		"artifactDir":   artifactDir,
		"capabilities":  append([]string(nil), plan.Capabilities...),
		"parameters": map[string]any{
			"duration_sec":       plan.DurationSec,
			"simulation_profile": plan.SimulationProfile,
		},
		"sourceClaims": map[string]any{
			"runtimeDomain":                 runtimeDomain(project),
			"scanSource":                    contractScanSource(project.Sensor.ScanSource),
			"imuSource":                     defaultString(project.RangefinderIMU.IMUSourceRoute, "official_gazebo_imu_bridge"),
			"rangefinderSource":             "ardupilot_serial7_benewake_tfmini",
			"rangefinderSimulationFidelity": "benewake_serial_emulated",
			"slamSource":                    defaultString(project.Slam.Backend, "cartographer"),
			"usesTruthAsControlInput":       false,
		},
		"createdAt": now.UTC().Format(time.RFC3339),
	}
}

func runtimeMode(project config.ProjectConfig) string {
	switch project.Runtime.Mode {
	case "real":
		return "RUNTIME_MODE_REAL"
	default:
		return "RUNTIME_MODE_SIM"
	}
}

func runtimeDomain(project config.ProjectConfig) string {
	switch project.Runtime.Mode {
	case "real":
		return "RUNTIME_DOMAIN_REAL"
	default:
		return "RUNTIME_DOMAIN_SIM"
	}
}

func defaultString(value string, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func contractScanSource(value string) string {
	switch strings.TrimSpace(value) {
	case "", "x2_virtual_serial":
		return "gazebo_x2_virtual_serial"
	default:
		return value
	}
}

func WriteJSONArtifact(path string, value any) error {
	return writeJSON(path, value)
}

func FinalizeRunArtifacts(
	project config.ProjectConfig,
	plan tasks.Plan,
	result DryRunResult,
	stageLabel string,
	controlMode string,
) ([]GeneratedArtifact, error) {
	runConfigPath := filepath.Join(result.ArtifactDir, "run_config.toml")
	runConfig := map[string]any{
		"run": map[string]any{
			"session_id":    project.SessionID,
			"run_id":        result.RunID,
			"artifact_dir":  result.ArtifactDir,
			"stage_id":      "NavLab",
			"stage_label":   stageLabel,
			"stage_gate":    plan.TaskID,
			"duration_sec":  plan.DurationSec,
			"ros_domain_id": project.RosDomainID,
		},
		"inputs": map[string]any{
			"task_id":              plan.TaskID,
			"simulation_profile":   plan.SimulationProfile,
			"control_mode":         controlMode,
			"control_authority":    "docker_simulation",
			"gazebo_direct_pose":   false,
			"task_config_format":   "yaml",
			"orchestration_impl":   project.Orchestration.Implementation,
			"orchestration_family": project.Orchestration.Family,
		},
		"outputs": map[string]any{
			"summary_json": filepath.Join(result.ArtifactDir, "summary.json"),
			"summary_md":   filepath.Join(result.ArtifactDir, "summary.md"),
			"manifest":     result.ManifestPath,
			"task_plan":    result.PlanPath,
			"rosbag":       filepath.Join(result.ArtifactDir, "rosbag", "rosbag_0.mcap"),
		},
	}
	if policy := startupReadinessPolicyFromPlan(plan); policy != nil {
		runConfig["startup_readiness_policy"] = policy
	}
	if err := writeTOML(runConfigPath, runConfig); err != nil {
		return nil, err
	}
	summaryMDPath := filepath.Join(result.ArtifactDir, "summary.md")
	if err := writeSummaryMarkdown(summaryMDPath, result.ArtifactDir); err != nil {
		return nil, err
	}
	return []GeneratedArtifact{
		{Type: "run_config", Path: runConfigPath},
		{Type: "summary_markdown", Path: summaryMDPath},
	}, nil
}

func startupReadinessPolicyFromPlan(plan tasks.Plan) map[string]any {
	raw, ok := plan.Execution.TaskParameters["runtime_config"]
	if !ok {
		return nil
	}
	runtimeConfig, ok := raw.(config.TaskRuntimeConfig)
	if !ok {
		return nil
	}
	policy := runtimeConfig.SlamHover.StartupReadinessPolicy
	if policy.TimeoutSec <= 0 && policy.GraceSec <= 0 && policy.ProgressWindowSec <= 0 && policy.RestartLimit == 0 {
		return nil
	}
	return map[string]any{
		"owner":               "go_runtime_config",
		"timeout_sec":         policy.TimeoutSec,
		"grace_sec":           policy.GraceSec,
		"progress_window_sec": policy.ProgressWindowSec,
		"restart_limit":       policy.RestartLimit,
	}
}

func AppendManifestArtifacts(manifestPath string, artifactDir string, generated []GeneratedArtifact) error {
	if len(generated) == 0 {
		return nil
	}
	data, err := os.ReadFile(manifestPath)
	if err != nil {
		return err
	}
	var manifest Manifest
	if err := json.Unmarshal(data, &manifest); err != nil {
		return err
	}
	for _, artifact := range generated {
		hash, err := fileSHA256(artifact.Path)
		if err != nil {
			return err
		}
		relativePath, err := filepath.Rel(artifactDir, artifact.Path)
		if err != nil {
			return err
		}
		if strings.HasPrefix(relativePath, "..") {
			relativePath = artifact.Path
		}
		manifest.Artifacts = append(manifest.Artifacts, RunArtifact{
			Type:          artifact.Type,
			Path:          filepath.ToSlash(relativePath),
			Producer:      "orchestration/sim",
			SchemaVersion: artifactSchemaVersion(artifact.Type),
			SHA256:        hash,
			Bytes:         fileSize(artifact.Path),
			CreatedAt:     fileCreatedAt(artifact.Path),
		})
	}
	return writeJSON(manifestPath, manifest)
}

func newManifestArtifact(artifactType string, path string, sha256 string, fullPath string) RunArtifact {
	return RunArtifact{
		Type:          artifactType,
		Path:          path,
		Producer:      "orchestration/sim",
		SchemaVersion: artifactSchemaVersion(artifactType),
		SHA256:        sha256,
		Bytes:         fileSize(fullPath),
		CreatedAt:     fileCreatedAt(fullPath),
	}
}

func artifactSchemaVersion(artifactType string) string {
	switch artifactType {
	case "task_request":
		return "navlab.orchestration.task_request.v1"
	case "runtime_plan":
		return "navlab.runtime.runtime_plan.v1"
	case "summary":
		return "navlab.orchestration.task_result.v1"
	default:
		return ""
	}
}

func fileSize(path string) int64 {
	info, err := os.Stat(path)
	if err != nil {
		return 0
	}
	return info.Size()
}

func fileCreatedAt(path string) string {
	info, err := os.Stat(path)
	if err != nil {
		return ""
	}
	return info.ModTime().UTC().Format(time.RFC3339)
}

func writeJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o644)
}

func writeTOML(path string, value any) error {
	data, err := toml.Marshal(value)
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

func writeSummaryMarkdown(path string, artifactDir string) error {
	data, err := os.ReadFile(filepath.Join(artifactDir, "summary.json"))
	if err != nil {
		return err
	}
	var summary map[string]any
	if err := json.Unmarshal(data, &summary); err != nil {
		return err
	}
	lines := []string{
		"# NavLab Simulation Task",
		"",
		fmt.Sprintf("- Result: `%s`", status(summary["ok"])),
		fmt.Sprintf("- Task: `%s`", stringValue(summary["task_id"])),
		fmt.Sprintf("- Run ID: `%s`", stringValue(summary["run_id"])),
		fmt.Sprintf("- Artifact dir: `%s`", artifactDir),
		fmt.Sprintf("- Summary JSON: `%s`", filepath.Join(artifactDir, "summary.json")),
		fmt.Sprintf("- Run config: `%s`", filepath.Join(artifactDir, "run_config.toml")),
		fmt.Sprintf("- Manifest: `%s`", filepath.Join(artifactDir, "manifest.json")),
		"",
		"## Blockers",
		"",
	}
	blockers, _ := summary["blockers"].([]any)
	if len(blockers) == 0 {
		lines = append(lines, "- none")
	} else {
		for _, blocker := range blockers {
			lines = append(lines, fmt.Sprintf("- `%v`", blocker))
		}
	}
	lines = append(lines, "", "## Runtime", "")
	if counts, ok := summary["runtime_spec_counts"].(map[string]any); ok {
		lines = append(lines,
			fmt.Sprintf("- Services: `%v`", counts["services"]),
			fmt.Sprintf("- Probes: `%v`", counts["probes"]),
			fmt.Sprintf("- Rosbags: `%v`", counts["rosbags"]),
		)
	}
	if gate, ok := summary["gate_evaluation"].(map[string]any); ok {
		lines = append(lines, "", "## Gate Evaluation", "")
		lines = append(lines, fmt.Sprintf("- Result: `%s`", status(gate["ok"])))
		if landing, ok := gate["landing_acceptance"].(map[string]any); ok {
			lines = append(lines, fmt.Sprintf("- Landing: `%s`", status(landing["ok"])))
		}
	}
	return os.WriteFile(path, []byte(strings.Join(lines, "\n")+"\n"), 0o644)
}

func status(value any) string {
	if ok, _ := value.(bool); ok {
		return "PASS"
	}
	if value == nil {
		return "UNKNOWN"
	}
	return "FAIL"
}

func stringValue(value any) string {
	if text, _ := value.(string); text != "" {
		return text
	}
	return fmt.Sprintf("%v", value)
}

func fileSHA256(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}

func sanitizePathSegment(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "unknown"
	}
	replacer := strings.NewReplacer("/", "-", "\\", "-", " ", "-")
	return replacer.Replace(value)
}
