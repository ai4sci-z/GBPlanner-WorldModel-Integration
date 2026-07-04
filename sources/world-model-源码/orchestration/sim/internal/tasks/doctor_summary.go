package tasks

import (
	"time"

	"navlab/orchestration-sim/internal/config"
)

type StaticDoctorSummary struct {
	OK                        bool                       `json:"ok"`
	Blocked                   bool                       `json:"blocked"`
	Blockers                  []string                   `json:"blockers"`
	DoctorStage               string                     `json:"doctor_stage"`
	TaskID                    string                     `json:"task_id"`
	RunID                     string                     `json:"run_id"`
	ArtifactDir               string                     `json:"artifact_dir"`
	RuntimeMode               string                     `json:"runtime_mode"`
	Backend                   string                     `json:"backend"`
	GeneratedRuntimeArtifacts []GeneratedRuntimeArtifact `json:"generated_runtime_artifacts"`
	RuntimeSpecCounts         RuntimeSpecCounts          `json:"runtime_spec_counts"`
	ResultGates               []ResultGateSummary        `json:"result_gates"`
	Checks                    map[string]bool            `json:"checks"`
	CreatedAt                 string                     `json:"created_at"`
}

func BuildStaticDoctorSummary(
	project config.ProjectConfig,
	plan Plan,
	runID string,
	artifactDir string,
	generatedArtifacts []GeneratedRuntimeArtifact,
	runtimeSpecs RuntimeSpecBundle,
) StaticDoctorSummary {
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
	return StaticDoctorSummary{
		OK:                        true,
		Blocked:                   false,
		Blockers:                  []string{},
		DoctorStage:               "static_sim_task_doctor",
		TaskID:                    plan.TaskID,
		RunID:                     runID,
		ArtifactDir:               artifactDir,
		RuntimeMode:               project.Runtime.Mode,
		Backend:                   project.Runtime.Backend,
		GeneratedRuntimeArtifacts: append([]GeneratedRuntimeArtifact(nil), generatedArtifacts...),
		RuntimeSpecCounts: RuntimeSpecCounts{
			Services: len(runtimeSpecs.Services),
			Probes:   len(runtimeSpecs.Probes),
			Rosbags:  len(runtimeSpecs.Rosbags),
		},
		ResultGates: resultGates,
		Checks: map[string]bool{
			"project_config_loaded":       true,
			"task_config_loaded":          true,
			"task_registry_configured":    true,
			"runtime_artifacts_generated": true,
			"runtime_specs_valid":         true,
		},
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}
}
