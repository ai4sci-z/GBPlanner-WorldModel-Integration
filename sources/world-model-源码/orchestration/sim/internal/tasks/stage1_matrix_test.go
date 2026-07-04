package tasks

import (
	"reflect"
	"testing"
	"time"

	"navlab/orchestration-sim/internal/config"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func TestBuildStage1ProfileMatrixBlocksWhenRequiredProfileMissing(t *testing.T) {
	matrix := BuildStage1ProfileMatrix(
		"hover",
		[]string{"ideal", "realistic"},
		[]LiveRunSummary{stage1PassingSummary("hover", "ideal")},
		time.Unix(1, 0),
	)
	if matrix.OK || !matrix.Blocked {
		t.Fatalf("matrix status = ok:%v blocked:%v", matrix.OK, matrix.Blocked)
	}
	if !reflect.DeepEqual(matrix.MissingProfiles, []string{"realistic"}) {
		t.Fatalf("missing profiles = %#v", matrix.MissingProfiles)
	}
	if !blockersContainPrefix(matrix.Blockers, "stage1_profile_missing:realistic") {
		t.Fatalf("blockers = %#v", matrix.Blockers)
	}
}

func TestBuildStage1ProfileMatrixPassesWhenRequiredProfilesPass(t *testing.T) {
	matrix := BuildStage1ProfileMatrix(
		"exploration",
		[]string{"ideal", "realistic"},
		[]LiveRunSummary{
			stage1PassingSummary("exploration", "ideal"),
			stage1PassingSummary("exploration", "realistic"),
		},
		time.Unix(1, 0),
	)
	if !matrix.OK || matrix.Blocked {
		t.Fatalf("matrix status = ok:%v blocked:%v blockers=%#v", matrix.OK, matrix.Blocked, matrix.Blockers)
	}
	if len(matrix.Profiles) != 2 {
		t.Fatalf("profiles = %#v", matrix.Profiles)
	}
}

func TestRequiredStage1ProfilesUsesOnlyStage1SimulationProfiles(t *testing.T) {
	profiles := RequiredStage1Profiles("scan-robustness", config.TaskRuntimeConfig{
		AirframeDisturbanceGate: config.AirframeDisturbanceGateConfig{
			RequiredProfiles: []string{"ideal", "realistic", "motor_bias_component", "esc_lag_component", "vibration_component"},
		},
	})
	want := []string{"ideal", "realistic"}
	if !reflect.DeepEqual(profiles, want) {
		t.Fatalf("profiles = %#v, want %#v", profiles, want)
	}
}

func TestBuildStage1ProfileMatrixFailsWhenLandingNotAccepted(t *testing.T) {
	summary := stage1PassingSummary("scan-robustness", "realistic")
	summary.GateEvaluation.Landing.OK = false
	summary.GateEvaluation.Landing.LandingClaim = helpers.ClaimNotEvaluated
	summary.GateEvaluation.Landing.SimulationLandingClaim = helpers.ClaimNotEvaluated
	summary.GateEvaluation.Landing.SimulationLandingAcceptance.OK = false

	matrix := BuildStage1ProfileMatrix(
		"scan-robustness",
		[]string{"realistic"},
		[]LiveRunSummary{summary},
		time.Unix(1, 0),
	)
	if matrix.OK || len(matrix.FailedProfiles) != 1 || matrix.FailedProfiles[0] != "realistic" {
		t.Fatalf("matrix = %#v", matrix)
	}
}

func stage1PassingSummary(taskID string, profile string) LiveRunSummary {
	return LiveRunSummary{
		OK:                true,
		TaskID:            taskID,
		RunID:             taskID + "-" + profile,
		ArtifactDir:       "/tmp/" + taskID + "/" + profile,
		SummaryPath:       "/tmp/" + taskID + "/" + profile + "/summary.json",
		AcceptanceStage:   "simulation",
		SimulationProfile: profile,
		GateEvaluation: GateEvaluation{
			Landing: helpers.Acceptance{
				OK:                     true,
				LandingClaim:           helpers.ClaimEvaluated,
				SimulationLandingClaim: helpers.ClaimEvaluated,
				Landing: helpers.Landing{
					OK:     true,
					Claim:  helpers.ClaimEvaluated,
					Policy: helpers.PolicyLandInPlace,
				},
				SimulationLandingAcceptance: helpers.Gate{
					OK:          true,
					RuntimeMode: "simulation",
				},
			},
			Metrics: MetricSummary{
				MetricEvidenceSources: map[string]string{"landing": "/navlab/landing/status"},
			},
		},
	}
}
