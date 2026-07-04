package tasks

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"time"

	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

const Stage1ProfileMatrixSchemaVersion = "navlab.orchestration.stage1_profile_matrix.v1"

type Stage1ProfileMatrix struct {
	SchemaVersion    string                `json:"schemaVersion"`
	OK               bool                  `json:"ok"`
	Blocked          bool                  `json:"blocked"`
	TaskID           string                `json:"task_id"`
	AcceptanceStage  string                `json:"acceptance_stage"`
	RequiredProfiles []string              `json:"required_profiles"`
	Profiles         []Stage1ProfileResult `json:"profiles"`
	MissingProfiles  []string              `json:"missing_profiles,omitempty"`
	FailedProfiles   []string              `json:"failed_profiles,omitempty"`
	Blockers         []string              `json:"blockers"`
	CreatedAt        string                `json:"created_at"`
}

type Stage1ProfileResult struct {
	Profile                string            `json:"profile"`
	OK                     bool              `json:"ok"`
	TaskID                 string            `json:"task_id"`
	RunID                  string            `json:"run_id,omitempty"`
	ArtifactDir            string            `json:"artifact_dir,omitempty"`
	SummaryPath            string            `json:"summary_path,omitempty"`
	LandingPolicy          string            `json:"landing_policy,omitempty"`
	LandingClaim           string            `json:"landing_claim"`
	SimulationLandingClaim string            `json:"simulation_landing_claim"`
	LandingOK              bool              `json:"landing_ok"`
	Blockers               []string          `json:"blockers,omitempty"`
	MetricEvidenceSources  map[string]string `json:"metric_evidence_sources,omitempty"`
}

func RequiredStage1Profiles(taskID string, runtimeConfig config.TaskRuntimeConfig) []string {
	_ = taskID
	_ = runtimeConfig
	return []string{"ideal", "realistic"}
}

func ReadLiveRunSummary(path string) (LiveRunSummary, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return LiveRunSummary{}, err
	}
	var summary LiveRunSummary
	if err := json.Unmarshal(data, &summary); err != nil {
		return LiveRunSummary{}, err
	}
	if summary.SummaryPath == "" {
		summary.SummaryPath = path
	}
	if summary.Stage1ProfileResult.Profile == "" {
		summary.Stage1ProfileResult = Stage1ProfileResultFromSummary(summary)
	}
	return summary, nil
}

func Stage1ProfileResultFromSummary(summary LiveRunSummary) Stage1ProfileResult {
	landing := summary.GateEvaluation.Landing
	landingOK := landing.OK &&
		landing.SimulationLandingAcceptance.OK &&
		landing.LandingClaim == helpers.ClaimEvaluated &&
		landing.SimulationLandingClaim == helpers.ClaimEvaluated
	blockers := append([]string(nil), summary.BlockerCodes...)
	blockers = append(blockers, landing.Blockers...)
	if !landingOK {
		blockers = append(blockers, helpers.SimulationLandingRequiredBlocker)
	}
	blockers = uniqueStrings(blockers)
	return Stage1ProfileResult{
		Profile:                fallbackProfile(summary.SimulationProfile),
		OK:                     summary.OK && landingOK,
		TaskID:                 summary.TaskID,
		RunID:                  summary.RunID,
		ArtifactDir:            summary.ArtifactDir,
		SummaryPath:            summary.SummaryPath,
		LandingPolicy:          landing.Landing.Policy,
		LandingClaim:           landing.LandingClaim,
		SimulationLandingClaim: landing.SimulationLandingClaim,
		LandingOK:              landingOK,
		Blockers:               blockers,
		MetricEvidenceSources:  summary.GateEvaluation.Metrics.MetricEvidenceSources,
	}
}

func BuildStage1ProfileMatrix(taskID string, requiredProfiles []string, summaries []LiveRunSummary, now time.Time) Stage1ProfileMatrix {
	requiredProfiles = uniqueStage1Profiles(requiredProfiles)
	resultsByProfile := map[string]Stage1ProfileResult{}
	blockers := []string{}

	for _, summary := range summaries {
		result := Stage1ProfileResultFromSummary(summary)
		if summary.TaskID != "" && summary.TaskID != taskID {
			blockers = append(blockers, fmt.Sprintf("stage1_summary_task_mismatch:%s:%s", result.Profile, summary.TaskID))
			continue
		}
		existing, exists := resultsByProfile[result.Profile]
		if !exists || (!existing.OK && result.OK) {
			resultsByProfile[result.Profile] = result
		}
	}

	missingProfiles := []string{}
	failedProfiles := []string{}
	for _, profile := range requiredProfiles {
		result, exists := resultsByProfile[profile]
		if !exists {
			missingProfiles = append(missingProfiles, profile)
			blockers = append(blockers, "stage1_profile_missing:"+profile)
			continue
		}
		if !result.OK {
			failedProfiles = append(failedProfiles, profile)
			blockers = append(blockers, "stage1_profile_failed:"+profile)
		}
	}

	profiles := make([]Stage1ProfileResult, 0, len(resultsByProfile))
	for _, result := range resultsByProfile {
		profiles = append(profiles, result)
	}
	sort.Slice(profiles, func(i, j int) bool {
		return profiles[i].Profile < profiles[j].Profile
	})

	blockers = uniqueStrings(blockers)
	return Stage1ProfileMatrix{
		SchemaVersion:    Stage1ProfileMatrixSchemaVersion,
		OK:               len(blockers) == 0,
		Blocked:          len(blockers) > 0,
		TaskID:           taskID,
		AcceptanceStage:  "simulation",
		RequiredProfiles: requiredProfiles,
		Profiles:         profiles,
		MissingProfiles:  missingProfiles,
		FailedProfiles:   failedProfiles,
		Blockers:         blockers,
		CreatedAt:        now.UTC().Format(time.RFC3339),
	}
}

func fallbackProfile(profile string) string {
	if profile == "" {
		return "ideal"
	}
	return profile
}

func uniqueStage1Profiles(profiles []string) []string {
	seen := map[string]bool{}
	result := make([]string, 0, len(profiles))
	for _, profile := range profiles {
		if profile == "" || seen[profile] {
			continue
		}
		seen[profile] = true
		result = append(result, profile)
	}
	return result
}
