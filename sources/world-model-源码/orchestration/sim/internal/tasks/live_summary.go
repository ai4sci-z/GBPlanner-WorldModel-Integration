package tasks

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"

	hoveraudit "navlab/orchestration-sim/internal/audits/hover"
)

type LiveRunSummary struct {
	SchemaVersion             string                          `json:"schemaVersion"`
	OK                        bool                            `json:"ok"`
	Blocked                   bool                            `json:"blocked"`
	Status                    string                          `json:"status"`
	ExitCode                  int                             `json:"exitCode"`
	SummaryPath               string                          `json:"summaryPath,omitempty"`
	Blockers                  []TaskResultBlocker             `json:"blockers"`
	BlockerCodes              []string                        `json:"blockerCodes"`
	Warnings                  []string                        `json:"warnings"`
	AcceptanceStage           string                          `json:"acceptance_stage"`
	TaskID                    string                          `json:"task_id"`
	RunID                     string                          `json:"run_id"`
	ArtifactDir               string                          `json:"artifact_dir"`
	SourceEvidence            map[string]any                  `json:"sourceEvidence"`
	Metrics                   map[string]any                  `json:"metrics"`
	Evidence                  map[string]any                  `json:"evidence"`
	Details                   map[string]any                  `json:"details"`
	StartedAt                 string                          `json:"startedAt"`
	FinishedAt                string                          `json:"finishedAt"`
	DurationSec               float64                         `json:"duration_sec"`
	SimulationProfile         string                          `json:"simulation_profile"`
	HoverSpanTargetM          float64                         `json:"hover_span_target_m,omitempty"`
	HoverSpanHardCapM         float64                         `json:"hover_span_hard_cap_m,omitempty"`
	HoverSLOPolicySource      string                          `json:"hover_slo_policy_source,omitempty"`
	StartupReadinessPolicy    map[string]any                  `json:"startup_readiness_policy,omitempty"`
	Stage1ProfileResult       Stage1ProfileResult             `json:"stage1_profile_result"`
	RuntimeMode               string                          `json:"runtime_mode"`
	Backend                   string                          `json:"backend"`
	GeneratedRuntimeArtifacts []GeneratedRuntimeArtifact      `json:"generated_runtime_artifacts"`
	RuntimeSpecCounts         RuntimeSpecCounts               `json:"runtime_spec_counts"`
	RuntimeExecution          RuntimeExecutionResult          `json:"runtime_execution"`
	FSMArtifacts              []FSMArtifactRef                `json:"fsm_artifacts,omitempty"`
	RuntimeError              string                          `json:"runtime_error,omitempty"`
	ResultGates               []ResultGateSummary             `json:"result_gates"`
	GateParity                GateParitySummary               `json:"gate_parity"`
	GateEvaluation            GateEvaluation                  `json:"gate_evaluation"`
	RuntimeHoverHealthFinal   map[string]any                  `json:"runtime_hover_health_final,omitempty"`
	PostrunHoverHealthAudit   *PostrunHoverHealthAudit        `json:"postrun_hover_health_audit,omitempty"`
	CohortHoverHealth         map[string]any                  `json:"cohort_hover_health,omitempty"`
	HoverHealthBand           string                          `json:"hover_health_band,omitempty"`
	HoverHealthHardBlockers   []hoveraudit.HoverHealthFinding `json:"hover_health_hard_blockers,omitempty"`
	HoverHealthWarnings       []hoveraudit.HoverHealthFinding `json:"hover_health_statistical_warnings,omitempty"`
	HoverHealthReviewOnly     []hoveraudit.HoverHealthFinding `json:"hover_health_review_only_findings,omitempty"`
	HoverHealthProceed        *hoveraudit.HoverHealthProceed  `json:"hover_health_proceed,omitempty"`
	CreatedAt                 string                          `json:"created_at"`
}

type PostrunHoverHealthAudit struct {
	Schema                   string                          `json:"schema"`
	Artifact                 string                          `json:"artifact"`
	HealthBand               hoveraudit.HoverHealthBand      `json:"health_band"`
	Proceed                  hoveraudit.HoverHealthProceed   `json:"proceed"`
	HardBlockers             []hoveraudit.HoverHealthFinding `json:"hard_blockers"`
	StatisticalWarnings      []hoveraudit.HoverHealthFinding `json:"statistical_warnings"`
	ReviewOnlyFindings       []hoveraudit.HoverHealthFinding `json:"review_only_findings"`
	DiagnosticOnly           bool                            `json:"diagnostic_only"`
	ControlsRuntimeProceed   bool                            `json:"controls_runtime_proceed"`
	RuntimeProceedTruth      bool                            `json:"runtime_proceed_truth"`
	RuntimeHealthArtifactKey string                          `json:"runtime_health_artifact_key"`
}

type TaskResultBlocker struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Source  string `json:"source"`
}

type RuntimeSpecCounts struct {
	Services int `json:"services"`
	Probes   int `json:"probes"`
	Rosbags  int `json:"rosbags"`
}

type ResultGateSummary struct {
	HelperID string   `json:"helper_id"`
	Name     string   `json:"name"`
	Inputs   []string `json:"inputs"`
	Outputs  []string `json:"outputs"`
	Status   string   `json:"status"`
}

type GateParitySummary struct {
	Status string   `json:"status"`
	Notes  []string `json:"notes"`
}

func BuildLiveRunSummary(
	project config.ProjectConfig,
	runtimeConfig config.TaskRuntimeConfig,
	plan Plan,
	runID string,
	artifactDir string,
	generatedArtifacts []GeneratedRuntimeArtifact,
	runtimeSpecs RuntimeSpecBundle,
	execution RuntimeExecutionResult,
	executionErr error,
) LiveRunSummary {
	blockers := []string{}
	runtimeError := ""
	if executionErr != nil {
		runtimeError = executionErr.Error()
		blockers = append(blockers, fmt.Sprintf("runtime_execution_failed:%s", executionErr.Error()))
	}
	resultGates := make([]ResultGateSummary, 0, len(plan.Execution.ResultGates))
	for _, gate := range plan.Execution.ResultGates {
		resultGates = append(resultGates, ResultGateSummary{
			HelperID: gate.HelperID,
			Name:     gate.Name,
			Inputs:   append([]string(nil), gate.Inputs...),
			Outputs:  append([]string(nil), gate.Outputs...),
			Status:   gate.Status,
		})
	}
	gateEvaluation := EvaluateResultGates(project, runtimeConfig, plan, artifactDir, runtimeSpecs, execution, executionErr)
	blockers = append(blockers, gateEvaluation.Blockers...)
	blockers = uniqueStrings(blockers)
	ok := len(blockers) == 0
	now := time.Now().UTC().Format(time.RFC3339)
	gateParity := GateParitySummary{
		Status: "evaluated_from_runtime_artifacts",
		Notes: []string{
			"Go sim live runner executes runtime service/probe/rosbag specs.",
			"Go sim evaluates runtime errors, probe outputs, rosbag metadata, task config checks, and landing acceptance from artifacts.",
		},
	}
	summary := LiveRunSummary{
		SchemaVersion:             "navlab.orchestration.task_result.v1",
		OK:                        ok,
		Blocked:                   !ok,
		Status:                    taskStatus(ok, executionErr),
		ExitCode:                  taskExitCode(ok, executionErr),
		Blockers:                  taskResultBlockers(blockers),
		BlockerCodes:              append([]string(nil), blockers...),
		Warnings:                  []string{},
		AcceptanceStage:           "simulation",
		TaskID:                    plan.TaskID,
		RunID:                     runID,
		ArtifactDir:               artifactDir,
		SourceEvidence:            simSourceEvidence(project),
		Metrics:                   liveMetrics(gateEvaluation),
		Evidence:                  liveEvidence(gateEvaluation, execution),
		Details:                   map[string]any{},
		StartedAt:                 now,
		FinishedAt:                now,
		DurationSec:               plan.DurationSec,
		SimulationProfile:         plan.SimulationProfile,
		RuntimeMode:               project.Runtime.Mode,
		Backend:                   project.Runtime.Backend,
		GeneratedRuntimeArtifacts: append([]GeneratedRuntimeArtifact(nil), generatedArtifacts...),
		RuntimeSpecCounts: RuntimeSpecCounts{
			Services: len(runtimeSpecs.Services),
			Probes:   len(runtimeSpecs.Probes),
			Rosbags:  len(runtimeSpecs.Rosbags),
		},
		RuntimeExecution: execution,
		RuntimeError:     runtimeError,
		ResultGates:      resultGates,
		GateParity:       gateParity,
		GateEvaluation:   gateEvaluation,
		CreatedAt:        now,
	}
	if isHoverSLAMProfileTask(plan.TaskID) {
		summary.HoverSpanTargetM = runtimeConfig.SlamHover.HoverSpanTargetM
		summary.HoverSpanHardCapM = runtimeConfig.SlamHover.HoverSpanHardCapM
		summary.HoverSLOPolicySource = "go_runtime_config"
		summary.StartupReadinessPolicy = startupReadinessPolicySummary(runtimeConfig.SlamHover.StartupReadinessPolicy)
	}
	summary.Stage1ProfileResult = Stage1ProfileResultFromSummary(summary)
	return summary
}

func taskStatus(ok bool, executionErr error) string {
	if ok {
		return "TASK_STATUS_OK"
	}
	if executionErr != nil {
		return "TASK_STATUS_ERROR"
	}
	return "TASK_STATUS_BLOCKED"
}

func taskExitCode(ok bool, executionErr error) int {
	if ok {
		return 0
	}
	if executionErr != nil {
		return 1
	}
	return 20
}

func taskResultBlockers(blockers []string) []TaskResultBlocker {
	result := make([]TaskResultBlocker, 0, len(blockers))
	for _, blocker := range blockers {
		code := blockerCode(blocker)
		result = append(result, TaskResultBlocker{
			Code:    code,
			Message: blocker,
			Source:  blockerSource(code),
		})
	}
	return result
}

func blockerCode(blocker string) string {
	code := blocker
	if index := strings.Index(code, ":"); index >= 0 {
		code = code[:index]
	}
	code = strings.TrimSpace(code)
	if code == "" {
		return "unknown_blocker"
	}
	return code
}

func blockerSource(code string) string {
	switch {
	case strings.HasPrefix(code, "runtime_"):
		return "runtime"
	case strings.HasPrefix(code, "probe_"):
		return "probe"
	case strings.HasPrefix(code, "rosbag_"):
		return "rosbag"
	case strings.Contains(code, "landing"):
		return "landing"
	default:
		return "gate"
	}
}

func simSourceEvidence(project config.ProjectConfig) map[string]any {
	return map[string]any{
		"runtimeDomain":                 "RUNTIME_DOMAIN_SIM",
		"scanSource":                    simContractScanSource(project.Sensor.ScanSource),
		"imuSource":                     fallbackString(project.RangefinderIMU.IMUSourceRoute, "official_gazebo_imu_bridge"),
		"rangefinderSource":             "ardupilot_serial7_benewake_tfmini",
		"rangefinderSimulationFidelity": "benewake_serial_emulated",
		"slamSource":                    fallbackString(project.Slam.Backend, "cartographer"),
		"usesTruthAsControlInput":       false,
	}
}

func fallbackString(value string, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func simContractScanSource(value string) string {
	switch strings.TrimSpace(value) {
	case "", "x2_virtual_serial":
		return "gazebo_x2_virtual_serial"
	default:
		return value
	}
}

func liveMetrics(gateEvaluation GateEvaluation) map[string]any {
	return map[string]any{
		"gate": gateEvaluation.Metrics,
	}
}

func liveEvidence(gateEvaluation GateEvaluation, execution RuntimeExecutionResult) map[string]any {
	return map[string]any{
		"probeOutputs":    gateEvaluation.ProbeOutputs,
		"rosbagProfiles":  gateEvaluation.RosbagProfiles,
		"runtimeHandles":  execution.ServiceHandles,
		"rosbagHandles":   execution.RosbagHandles,
		"runtimeProbes":   execution.ProbeResults,
		"landingEvidence": gateEvaluation.Landing,
	}
}

func BuildAndWriteHoverHealthSummaryArtifact(artifactDir string) (*hoveraudit.HoverHealthSummary, string, error) {
	health, err := hoveraudit.BuildHoverHealthAudit(artifactDir)
	if err != nil {
		return nil, "", err
	}
	path := artifactlayout.Audit(artifactDir, "hover_health_summary.json")
	data, err := json.MarshalIndent(health, "", "  ")
	if err != nil {
		return nil, "", err
	}
	data = append(data, '\n')
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, "", err
	}
	if err := os.WriteFile(path, data, 0o644); err != nil {
		return nil, "", err
	}
	return health, path, nil
}

func AttachHoverHealthToLiveRunSummary(summary *LiveRunSummary, health *hoveraudit.HoverHealthSummary) {
	if summary == nil || health == nil {
		return
	}
	summary.HoverHealthBand = string(health.HealthBand)
	summary.HoverHealthHardBlockers = append([]hoveraudit.HoverHealthFinding(nil), health.HardBlockers...)
	summary.HoverHealthWarnings = append([]hoveraudit.HoverHealthFinding(nil), health.StatisticalWarnings...)
	summary.HoverHealthReviewOnly = append([]hoveraudit.HoverHealthFinding(nil), health.ReviewOnlyFindings...)
	proceed := health.Proceed
	summary.HoverHealthProceed = &proceed
	summary.PostrunHoverHealthAudit = &PostrunHoverHealthAudit{
		Schema:                   health.Schema,
		Artifact:                 artifactlayout.Audit(summary.ArtifactDir, "hover_health_summary.json"),
		HealthBand:               health.HealthBand,
		Proceed:                  proceed,
		HardBlockers:             append([]hoveraudit.HoverHealthFinding{}, health.HardBlockers...),
		StatisticalWarnings:      append([]hoveraudit.HoverHealthFinding{}, health.StatisticalWarnings...),
		ReviewOnlyFindings:       append([]hoveraudit.HoverHealthFinding{}, health.ReviewOnlyFindings...),
		DiagnosticOnly:           health.DiagnosticOnly,
		ControlsRuntimeProceed:   false,
		RuntimeProceedTruth:      false,
		RuntimeHealthArtifactKey: "runtime_hover_health_final",
	}

	healthMetrics := map[string]any{
		"band":                          health.HealthBand,
		"hard_blocker_count":            len(health.HardBlockers),
		"statistical_warning_count":     len(health.StatisticalWarnings),
		"review_only_finding_count":     len(health.ReviewOnlyFindings),
		"sim_auto_continue_allowed":     health.Proceed.SimAutoContinueAllowed,
		"real_operator_confirm_allowed": health.Proceed.RealOperatorConfirmAllowed,
		"proceed_reason":                health.Proceed.Reason,
	}
	summary.GateEvaluation.Metrics.HoverHealth = healthMetrics
	if summary.Metrics == nil {
		summary.Metrics = map[string]any{}
	}
	summary.Metrics["hover_health"] = healthMetrics
	if gate, ok := summary.Metrics["gate"].(MetricSummary); ok {
		gate.HoverHealth = healthMetrics
		summary.Metrics["gate"] = gate
	}
	if summary.Evidence == nil {
		summary.Evidence = map[string]any{}
	}
	summary.Evidence["hoverHealth"] = map[string]any{
		"schema":         health.Schema,
		"artifact":       artifactlayout.Audit(summary.ArtifactDir, "hover_health_summary.json"),
		"diagnosticOnly": health.DiagnosticOnly,
	}
}

func AttachRuntimeHoverHealthFromMissionSummary(summary *LiveRunSummary) {
	if summary == nil || summary.ArtifactDir == "" {
		return
	}
	data, err := os.ReadFile(filepath.Join(summary.ArtifactDir, "mission_summary.json"))
	if err != nil {
		return
	}
	var mission map[string]any
	if err := json.Unmarshal(data, &mission); err != nil {
		return
	}
	health, ok := mission["runtime_hover_health_final"].(map[string]any)
	if !ok || len(health) == 0 {
		return
	}
	summary.RuntimeHoverHealthFinal = health
	if summary.Metrics == nil {
		summary.Metrics = map[string]any{}
	}
	summary.Metrics["runtime_hover_health"] = health
	if summary.Evidence == nil {
		summary.Evidence = map[string]any{}
	}
	summary.Evidence["runtimeHoverHealth"] = map[string]any{
		"schema":              health["schema"],
		"artifact":            filepath.Join(summary.ArtifactDir, "mission_summary.json"),
		"controlsTaskProceed": true,
		"postrunAudit":        false,
	}
}
